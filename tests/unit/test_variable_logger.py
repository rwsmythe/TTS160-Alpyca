"""Read-only variable logger tests; no serial port is opened."""

import csv
import datetime as dt
import io
import logging
from pathlib import Path
import threading
import time
from unittest.mock import Mock, call, patch

import pytest

import variable_logger as vl


def test_default_list_is_valid_and_two_queries():
    assert vl.validate_variables(vl.DEFAULT_VARIABLES) == vl.DEFAULT_VARIABLES
    assert [len(c) for c in vl.chunk_variables(vl.DEFAULT_VARIABLES)] == [10, 10]


@pytest.mark.parametrize("bad", [[], ["T0"], ["T100"], ["Q1"], ["t1"], ["T1", "T1"],
                                 ["T31"], ["T32"], ["C17"], ["C18"], ["T1 "], ["T"],
                                 [f"T{i}" for i in range(1, 22)]])
def test_bad_lists_are_rejected(bad):
    with pytest.raises(vl.VariableListError):
        vl.validate_variables(bad)


def test_chunks_keep_order_and_cover_all():
    v = [f"T{i}" for i in range(1, 14)]
    assert vl.chunk_variables(v, 5) == [v[0:5], v[5:10], v[10:13]]


def test_row_formats_awkward_values_and_keeps_width():
    t = dt.datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=dt.timezone.utc)
    vars_ = ["T1", "T2", "T16", "X1", "C5"]
    row = vl.format_row(t, 12.3456, vars_,
                        {"T1": -5, "T2": float("nan"), "T16": float("inf"), "X1": (1, 2)}, "")
    assert row == ["2026-01-02T03:04:05.678Z", "12.346", "-5", "nan", "inf", "(1, 2)", "", ""]
    assert len(row) == len(vl.header_row(vars_))
    stream = io.StringIO()
    csv.writer(stream).writerow(row)
    assert '"(1, 2)"' in stream.getvalue()
    assert next(csv.reader(io.StringIO(stream.getvalue()))) == row
    assert vl.format_row(t, 0, ["C5"], {"C5": None})[2] == ""


def test_bool_is_written_as_0_or_1():
    t = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)
    assert vl.format_row(t, 0.0, ["T4"], {"T4": True})[2] == "1"
    assert vl.format_row(t, 0.0, ["T4"], {"T4": False})[2] == "0"


@pytest.fixture
def make(tmp_path):
    active = []

    def factory(query, variables=("T1", "T2"), interval_s=1.0, **kwargs):
        clock = kwargs.pop("clock", Mock(return_value=0.0))
        directory = kwargs.pop("directory", str(tmp_path))
        obj = vl.VariableLogger(query, variables, interval_s, directory, logging.getLogger("t"),
                                clock=clock, **kwargs)
        with patch("variable_logger.threading.Thread") as thread:
            thread.return_value.is_alive.return_value = False
            assert obj.start()
        active.append(obj)
        return obj, clock

    yield factory
    for obj in active:
        obj.stop()


def read_rows(obj):
    with open(obj.path, newline="", encoding="utf-8") as stream:
        return list(csv.reader(stream))


def test_writes_header_then_one_row_per_poll(make):
    obj, clock = make(lambda v: {"T1": 1, "T2": 2})
    obj.poll_once()
    clock.return_value = 1.0
    obj.poll_once()
    rows = read_rows(obj)
    assert rows[0] == ["utc", "elapsed_s", "T1", "T2", "error"]
    assert len(rows) == 3
    assert rows[1][1:] == ["0.000", "1", "2", ""]
    assert rows[2][1:] == ["1.000", "1", "2", ""]


def test_only_query_is_ever_called(make):
    query = Mock(spec=[], return_value={"T1": 1, "T2": 2})
    obj, clock = make(query)
    for i in range(3):
        clock.return_value = float(i)
        obj.poll_once()
    assert query.call_args_list == [call(["T1", "T2"])] * 3
    assert query.mock_calls == query.call_args_list


def test_failure_writes_blank_row_then_backs_off_30s(make):
    query = Mock(side_effect=TimeoutError("no response"))
    obj, clock = make(query)
    obj.poll_once()
    assert read_rows(obj)[1][2:] == ["", "", "TimeoutError: no response"]
    assert obj._next_due == 30.0
    clock.return_value = 29.999
    obj.poll_once()
    assert query.call_count == 1
    query.side_effect = None
    query.return_value = {"T1": 1, "T2": 2}
    clock.return_value = 30.0
    obj.poll_once()
    assert read_rows(obj)[2][2:] == ["1", "2", ""]
    assert obj._next_due == 31.0


def test_second_chunk_failure_keeps_first_chunk_values(make):
    variables = [f"T{i}" for i in range(1, 13)]
    query = Mock(side_effect=[dict.fromkeys(variables[:10], 7), TimeoutError("chunk 2")])
    obj, _ = make(query, variables=variables)
    obj.poll_once()
    assert query.call_args_list == [call(variables[:10]), call(variables[10:])]
    assert read_rows(obj)[1][2:] == ["7"] * 10 + ["", "", "TimeoutError: chunk 2"]


def test_off_grid_recovery_keeps_a_full_interval_before_next_poll(make):
    clock = Mock(return_value=0.0)

    def fail(variables):
        clock.return_value = 0.5
        raise TimeoutError("off grid")

    query = Mock(side_effect=fail)
    obj, _ = make(query, clock=clock)
    obj.poll_once()
    assert obj._next_due == 30.5
    query.side_effect = None
    query.return_value = {"T1": 1, "T2": 2}
    clock.return_value = 30.5
    obj.poll_once()
    assert obj._next_due == 32.0
    clock.return_value = 31.999
    obj.poll_once()
    assert query.call_count == 2


def test_on_grid_poll_with_short_read_keeps_next_grid_point(make):
    clock = Mock(return_value=0.0)

    def query(variables):
        clock.return_value = 5.3
        return {"T1": 1, "T2": 2}

    obj, _ = make(query, clock=clock)
    clock.return_value = 5.0
    obj.poll_once()
    assert obj._next_due == 6.0


def test_late_ordinary_poll_keeps_next_grid_point(make):
    obj, clock = make(Mock(return_value={"T1": 1}))
    obj._next_due = 5.0
    clock.return_value = 5.001
    obj.poll_once()
    assert obj._next_due == 6.0


@pytest.mark.parametrize("late", [False, True], ids=["exact_due", "late_1_to_16_ms"])
def test_non_dyadic_interval_with_large_start_never_skips_a_slot(make, late):
    start, interval = 98765.4321, 1.3
    clock = Mock(return_value=start)
    query = Mock(return_value={"T1": 1})
    obj, _ = make(query, clock=clock, interval_s=interval)
    for slot in range(50):
        delay = (slot % 16 + 1) / 1000 if late else 0.0
        clock.return_value = start + slot * interval + delay
        obj.poll_once()
        assert obj._next_due == start + (slot + 1) * interval, slot
        assert query.call_count == slot + 1


def test_ordinary_poll_after_recovery_keeps_next_grid_point(make):
    clock = Mock(return_value=0.0)

    def fail(variables):
        clock.return_value = 0.5
        raise TimeoutError("off grid")

    query = Mock(side_effect=fail)
    obj, _ = make(query, clock=clock)
    obj.poll_once()
    assert obj._next_due == 30.5
    query.side_effect = None
    query.return_value = {"T1": 1}
    clock.return_value = 30.5
    obj.poll_once()
    assert obj._next_due == 32.0
    clock.return_value = 32.004
    obj.poll_once()
    assert obj._next_due == 33.0


def test_real_thread_keeps_full_poll_rate(tmp_path, monkeypatch):
    # Scale only the validation threshold for this short real-clock rate test.
    monkeypatch.setattr(vl, "MIN_INTERVAL_S", 0.2)
    obj = vl.VariableLogger(lambda v: {"T1": 1}, ["T1"], 0.2, str(tmp_path), logging.getLogger("t"))
    try:
        assert obj.start()
        time.sleep(2.1)
    finally:
        obj.stop()
    assert len(read_rows(obj)) - 1 >= 9


@pytest.mark.parametrize("variables,interval,message", [
    (["T31"], 1.0, "T31"), (["T1"], 0.5, "1.0"),
    (["T1"], float("nan"), "1.0"), (["T1"], float("inf"), "1.0"),
])
def test_start_refuses_bad_list_and_bad_interval(tmp_path, caplog, variables, interval, message):
    obj = vl.VariableLogger(Mock(), variables, interval, str(tmp_path), logging.getLogger("t"))
    assert obj.start() is False
    assert not obj.running
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert message in caplog.text
    assert list(tmp_path.iterdir()) == []


def test_successful_start_logs_one_info_with_absolute_csv_path(make, tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "existing").mkdir()
    with caplog.at_level(logging.INFO, logger="t"):
        obj, _ = make(Mock(return_value={}), directory="existing")
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.INFO
    expected = tmp_path / "existing" / Path(obj.path).name
    assert obj.path == str(expected)
    assert caplog.records[0].getMessage() == f"Variable logger writing {expected}"


def test_unwritable_directory_refuses_start(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    obj = vl.VariableLogger(Mock(), ["T1"], 1.0, str(Path("missing") / "x"), logging.getLogger("t"))
    assert obj.start() is False
    assert not obj.running
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert str(tmp_path / "missing" / "x") in caplog.records[0].getMessage()
    assert "directory must already exist" in caplog.records[0].getMessage()
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("error_type", [FileNotFoundError, FileExistsError, PermissionError])
def test_start_refusal_distinguishes_missing_directory_from_other_open_errors(
        tmp_path, monkeypatch, caplog, error_type):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "logs"
    stamp = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)
    obj = vl.VariableLogger(Mock(), ["T1"], 1.0, "logs", logging.getLogger("t"), utcnow=lambda: stamp)
    with patch.object(Path, "open", side_effect=error_type("open refused")):
        assert obj.start() is False
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    message = caplog.records[0].getMessage()
    assert str(directory) in message
    assert "open refused" in message
    if error_type is FileNotFoundError:
        assert "directory must already exist" in message
    else:
        assert str(directory / "variables-20260102T000000Z.csv") in message
        assert "must already exist" not in message


def test_write_error_mid_run_stops_logger(make, caplog):
    query = Mock(return_value={"T1": 1})
    obj, clock = make(query)
    with patch.object(obj._file, "write", side_effect=OSError(28, "disk full")):
        # csv.writer captures write at construction, so bind the injected fault.
        obj._writer = csv.writer(obj._file)
        obj.poll_once()
    assert not obj.running
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    clock.return_value = 1.0
    obj.poll_once()
    assert query.call_count == 1


def test_slow_poll_skips_missed_slots_and_backoff_starts_after_failure(make):
    clock = Mock(return_value=0.0)

    def query(variables):
        clock.return_value = 3.5
        return {"T1": 1}

    obj, _ = make(query, clock=clock)
    obj.poll_once()
    assert obj._next_due == 4.0
    clock.return_value = 4.0

    def fail(variables):
        clock.return_value = 8.0
        raise TimeoutError("slow")

    obj._query = fail
    obj.poll_once()
    assert obj._next_due == 38.0


def test_stop_ends_thread_within_timeout_while_query_blocks(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def query(variables):
        entered.set()
        release.wait(10)
        return {"T1": 1}

    obj = vl.VariableLogger(query, ["T1"], 1.0, str(tmp_path), logging.getLogger("t"))
    try:
        assert obj.start()
        assert entered.wait(1)
        assert obj._thread.daemon and obj._thread.name == "variable-logger"
        before = time.monotonic()
        obj.stop(timeout=2.0)
        assert time.monotonic() - before < 2.5
        assert not obj.running
    finally:
        release.set()
        obj.stop()
    assert not obj._thread.is_alive()
    assert obj._file.closed
    assert all(len(row) == 4 for row in read_rows(obj))


def test_module_source_names_no_state_changing_call():
    src = Path(vl.__file__).read_text(encoding="utf-8")
    for name in ("execute_set_command", "send_command", "_send_set_command_bytes", "halt(", "set_tracking",
                 "pulse_guide", "slew_to", "set_target", "park(", "unpark(", "align_point",
                 "perform_alignment", "push_", "build_set_command"):
        assert name not in src, name

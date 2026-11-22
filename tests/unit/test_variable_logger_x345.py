"""X3, X4 and X5 in the variable logger (CHARC 232451Z); no serial port is opened.

The grounding tests drive the real SerialManager.query_variables parse path over a
byte-level fake wire built on the conftest ``mock_serial_port`` fixture (serial.Serial is
patched; connect() is never called).
"""

import csv
import logging
import struct
import threading
from unittest.mock import Mock, patch

import pytest

from tts160_serial import ResponseError, SerialManager
import tts160_types as tt
import variable_logger as vl

# The exact error query_variables raises for the firmware's "ERROR:PARSE_ERROR\n" text frame
# (grounded below on the fake wire).
PARSE_ERROR_MESSAGE = "Expected binary response for v357 query, got text: ERROR:PARSE_ERROR\n"
LOST_REPLY_MESSAGE = "Expected binary response for v357 query, got text: "


class FakeWire:
    """pyserial-like byte stream: each write loads the mount's reply; reads never block."""

    def __init__(self, port, replies):
        self.replies = dict(replies)
        self.written = []
        self.buffer = b""
        port.write.side_effect = self.write
        port.read.side_effect = self.read
        port.read_until.side_effect = self.read_until
        port.reset_input_buffer.side_effect = self.reset

    def write(self, data):
        self.written.append(data)
        reply = self.replies.get(data, b"")
        self.buffer = reply() if callable(reply) else reply
        return len(data)

    def reset(self):
        self.buffer = b""

    def read(self, size=1):
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def read_until(self, expected=b"\n", size=None):
        # At the read timeout pyserial returns whatever arrived, possibly nothing.
        index = self.buffer.find(expected)
        end = len(self.buffer) if index < 0 else index + len(expected)
        data, self.buffer = self.buffer[:end], self.buffer[end:]
        return data


@pytest.fixture
def manager(mock_serial_port, mock_logger):
    mgr = SerialManager(logger=mock_logger)
    mgr._serial = mock_serial_port  # never connect(): no port is opened
    mgr._retry_timeout = 0.0
    return mgr


# ---------------------------------------------------------------- grounding

def test_ground_parse_error_text_surfaces_as_response_error_carrying_it(manager, mock_serial_port):
    wire = FakeWire(mock_serial_port, {b":*!G X4#": b"ERROR:PARSE_ERROR\n"})
    with pytest.raises(ResponseError) as info:
        manager.query_variables(["X4"])
    assert str(info.value) == PARSE_ERROR_MESSAGE
    assert wire.written == [b":*!G X4#"]  # one attempt: a text reply is not retried


def test_ground_lost_reply_surfaces_differently(manager, mock_serial_port):
    wire = FakeWire(mock_serial_port, {})
    with pytest.raises(ResponseError) as info:
        manager.query_variables(["X4"])
    assert str(info.value) == LOST_REPLY_MESSAGE
    assert wire.written == [b":*!G X4#"]


def test_ground_binary_reply_for_x4(manager, mock_serial_port):
    FakeWire(mock_serial_port, {b":*!G X4#": b"BINARY:H\n" + struct.pack("<H", 1234)})
    assert manager.query_variables(["X4"]) == {"X4": 1234}


def test_ground_logger_over_real_query_path_classifies_parse_error(manager, mock_serial_port, tmp_path, caplog):
    """End to end: logger -> SerialManager.query_variables -> fake wire answering as the pin firmware."""
    wire = FakeWire(mock_serial_port, {
        b":*!G T1,X3#": b"BINARY:fH\n" + struct.pack("<fH", 1.5, 2000),
        b":*!G X4#": b"ERROR:PARSE_ERROR\n",
        b":*!G X5#": b"ERROR:PARSE_ERROR\n",
        b":*!G X6#": b"ERROR:PARSE_ERROR\n",
        b":*!G X7#": b"ERROR:PARSE_ERROR\n",
    })
    clock = Mock(return_value=0.0)
    obj = vl.VariableLogger(manager.query_variables, ["T1"], 1.0, str(tmp_path), logging.getLogger("t"),
                            clock=clock)
    with patch("variable_logger.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        assert obj.start()
    try:
        with caplog.at_level(logging.INFO, logger="t"):
            for second in range(3):
                clock.return_value = float(second)
                obj.poll_once()
    finally:
        obj.stop()
    assert wire.written == [b":*!G T1,X3#", b":*!G X4#", b":*!G X5#", b":*!G X6#", b":*!G X7#",
                            b":*!G T1,X3#", b":*!G X4#", b":*!G X5#", b":*!G X6#", b":*!G X7#",
                            b":*!G T1,X3#"]
    assert len(read_rows(obj)) == 4  # header + three data rows
    assert [row[2:] for row in read_rows(obj)[1:]] == [["1.5", "2000", "", "", "", "", q, "0", ""]
                                                       for q in ("5", "5", "1")]
    assert obj._consecutive_failures == 0


# ---------------------------------------------------------------- types

def test_types_gain_x4_and_x5_as_uint16():
    assert tt.ComputedVar.FREE_MEM == 3
    assert tt.ComputedVar.MIN_FREE_MEM == 4
    assert tt.ComputedVar.LOOP_MAX_TICKS == 5
    assert [m.value for m in tt.ComputedVar] == [1, 2, 3, 4, 5, 6, 7]
    assert tt.VARIABLE_TYPES[("X", 3)] == "H"
    assert tt.VARIABLE_TYPES[("X", 4)] == "H"
    assert tt.VARIABLE_TYPES[("X", 5)] == "H"
    assert ("X", 8) not in tt.VARIABLE_TYPES


# ---------------------------------------------------------------- list, header, columns

@pytest.mark.parametrize("fixed", ["X3", "X4", "X5"])
def test_configured_list_naming_a_fixed_column_is_refused(fixed):
    with pytest.raises(vl.VariableListError, match=fixed):
        vl.validate_variables(["T1", fixed])


def test_x1_x2_remain_configurable():
    assert vl.validate_variables(["X1", "X2"]) == ("X1", "X2")


def test_header_appends_x3_x4_x5_before_error():
    assert vl.header_row(vl.DEFAULT_VARIABLES) == ["utc", "elapsed_s", *vl.DEFAULT_VARIABLES,
                                                   "X3", "X4", "X5", "X6", "X7", "queries", "failed", "error"]
    assert vl.header_row(["C5", "T1"]) == ["utc", "elapsed_s", "C5", "T1", "X3", "X4", "X5", "X6", "X7",
                                           "queries", "failed", "error"]


# ---------------------------------------------------------------- poll behaviour

class Mount:
    """Injected query: chunks answer from ``values``; X4/X5 single-id queries follow per-id scripts."""

    def __init__(self, values=None, scripts=None):
        self.values = values or {}
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.calls = []

    def __call__(self, variables):
        self.calls.append(list(variables))
        if len(variables) == 1 and variables[0] in ("X4", "X5") and self.scripts.get(variables[0]):
            outcome = self.scripts[variables[0]].pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome if isinstance(outcome, dict) else {variables[0]: outcome}
        return {v: self.values.get(v, 7) for v in variables}


def parse_error():
    return ResponseError(PARSE_ERROR_MESSAGE)


@pytest.fixture
def make(tmp_path):
    active = []

    def factory(query, variables=("T1", "T2"), interval_s=1.0, **kwargs):
        clock = kwargs.pop("clock", Mock(return_value=0.0))
        obj = vl.VariableLogger(query, variables, interval_s, str(tmp_path), logging.getLogger("t"),
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


def run_polls(obj, clock, count, start=0):
    for second in range(start, start + count):
        clock.return_value = float(second)
        obj.poll_once()


def test_both_present_values_land_and_sequence_is_chunks_then_x4_then_x5(make):
    mount = Mount(values={"X3": 3000, "T1": 1, "O12": 12}, scripts={"X4": [400], "X5": [5]})
    obj, clock = make(mount, variables=vl.DEFAULT_VARIABLES)
    obj.poll_once()
    default = list(vl.DEFAULT_VARIABLES)
    assert mount.calls == [default[:10], default[10:], ["X3"], ["X4"], ["X5"], ["X6"], ["X7"]]
    rows = read_rows(obj)
    assert rows[0] == ["utc", "elapsed_s", *default, "X3", "X4", "X5", "X6", "X7", "queries", "failed", "error"]
    row = dict(zip(rows[0], rows[1]))
    assert (row["T1"], row["O12"], row["X3"], row["X4"], row["X5"], row["error"]) == \
        ("1", "12", "3000", "400", "5", "")
    assert len(rows[1]) == len(rows[0])


def test_small_list_puts_x3_in_the_same_chunk(make):
    mount = Mount(scripts={"X4": [1], "X5": [2]})
    obj, _ = make(mount)
    obj.poll_once()
    assert mount.calls == [["T1", "T2", "X3"], ["X4"], ["X5"], ["X6"], ["X7"]]
    assert read_rows(obj)[1][2:] == ["7", "7", "7", "1", "2", "7", "7", "5", "0", ""]


def test_both_absent_dropped_after_second_parse_error_never_asked_again(make, caplog):
    mount = Mount(scripts={"X4": [parse_error(), parse_error()], "X5": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    with caplog.at_level(logging.INFO, logger="t"):
        run_polls(obj, clock, 5)
    per_poll = [["T1", "T2", "X3"], ["X4"], ["X5"], ["X6"], ["X7"]]
    assert mount.calls == per_poll * 2 + [["T1", "T2", "X3"], ["X6"], ["X7"]] * 3
    rows = read_rows(obj)[1:]
    # Not found is not a failure: the error column stays empty (the chosen marker is none).
    assert [row[2:] for row in rows] == [["7", "7", "7", "", "", "7", "7", q, "0", ""]
                                         for q in ("5", "5", "3", "3", "3")]
    assert [float(row[1]) for row in rows] == [0.0, 1.0, 2.0, 3.0, 4.0]  # no back-off
    assert obj._consecutive_failures == 0
    assert not obj._after_backoff
    for variable in ("X4", "X5"):
        lines = [r.getMessage() for r in caplog.records if variable in r.getMessage()]
        assert len(lines) == 2, lines
        assert "may be absent" in lines[0]
        assert "absent" in lines[1] and "may be absent" not in lines[1]


def test_lost_x4_reply_once_is_an_ordinary_failure_and_x4_is_asked_again(make):
    mount = Mount(scripts={"X4": [ResponseError(LOST_REPLY_MESSAGE), 41, 42], "X5": [51, 52, 53]})
    obj, clock = make(mount)
    run_polls(obj, clock, 1)
    assert obj._consecutive_failures == 1
    assert obj._next_due == 1.0 and not obj._after_backoff  # one lost reply alone: no back-off
    run_polls(obj, clock, 2, start=1)
    assert mount.calls == [["T1", "T2", "X3"], ["X4"], ["X5"], ["X6"], ["X7"]] * 3
    rows = read_rows(obj)[1:]
    assert rows[0][2:6] == ["7", "7", "7", ""]
    assert rows[0][6] == "51"  # X5 still asked and logged in the same poll
    assert rows[0][-1] == f"X4 ResponseError: {LOST_REPLY_MESSAGE}"
    assert rows[1][2:] == ["7", "7", "7", "41", "52", "7", "7", "5", "0", ""]
    assert rows[2][2:] == ["7", "7", "7", "42", "53", "7", "7", "5", "0", ""]
    assert obj._consecutive_failures == 0


def test_x4_timeout_counts_toward_back_off_like_a_failed_chunk(make):
    mount = Mount(scripts={"X4": [TimeoutError("first"), TimeoutError("second"), 4]})
    obj, clock = make(mount)
    run_polls(obj, clock, 2)
    assert obj._consecutive_failures == 2
    assert obj._after_backoff and obj._next_due == 31.0
    rows = read_rows(obj)[1:]
    assert [row[-1] for row in rows] == ["X4 TimeoutError: first", "X4 TimeoutError: second"]


def test_both_single_id_failures_are_both_reported(make):
    mount = Mount(scripts={"X4": [TimeoutError("a")], "X5": [ResponseError("garbled")]})
    obj, _ = make(mount)
    obj.poll_once()
    assert read_rows(obj)[1][-1] == "X4 TimeoutError: a; X5 ResponseError: garbled"
    assert obj._consecutive_failures == 1


@pytest.mark.parametrize("text", ["ERROR:VAR_ERROR\n", "ERROR:PARSE_ERROR\nX", "ERROR:PARSE_ERROR", ""])
def test_other_text_answers_are_ordinary_failures(make, text):
    error = ResponseError(f"Expected binary response for v357 query, got text: {text}")
    mount = Mount(scripts={"X4": [error, error, error]})
    obj, clock = make(mount)
    for when in (0.0, 1.0, 31.0):  # two ordinary failures back off; the probe asks X4 again
        clock.return_value = when
        obj.poll_once()
    assert mount.calls.count(["X4"]) == 3  # never dropped
    assert obj._absent == set()
    assert all(row[-1].startswith("X4 ResponseError: ") for row in read_rows(obj)[1:])


def test_parse_error_once_then_values_keeps_the_id_and_resets_strikes(make, caplog):
    mount = Mount(scripts={"X4": [parse_error(), 41, 42, parse_error(), 43, parse_error(), parse_error()]})
    obj, clock = make(mount)
    with caplog.at_level(logging.INFO, logger="t"):
        run_polls(obj, clock, 3)
        assert obj._strikes["X4"] == 0
        assert "X4" not in obj._absent
        run_polls(obj, clock, 2, start=3)  # PARSE_ERROR, value: still kept
        assert "X4" not in obj._absent
        run_polls(obj, clock, 3, start=5)  # two consecutive: dropped on the second
    assert [row[5] for row in read_rows(obj)[1:]] == ["", "41", "42", "", "43", "", "", ""]
    assert mount.calls.count(["X4"]) == 7
    assert "X4" in obj._absent
    messages = [r.getMessage() for r in caplog.records if "X4" in r.getMessage()]
    assert sum("may be absent" in m for m in messages) == 3
    assert sum("absent" in m and "may be absent" not in m for m in messages) == 1


@pytest.mark.parametrize("empty", [{}, {"X4": None}], ids=["missing_key", "none"])
def test_an_answer_without_a_value_does_not_reset_the_strike(make, empty):
    mount = Mount(scripts={"X4": [parse_error(), empty, parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 3)
    assert "X4" in obj._absent  # the empty answer neither strikes nor resets
    assert [row[5] for row in read_rows(obj)[1:]] == ["", "", ""]
    assert all(row[-1] == "" for row in read_rows(obj)[1:])


def test_a_zero_value_resets_the_strike(make):
    mount = Mount(scripts={"X4": [parse_error(), 0, parse_error(), 5]})
    obj, clock = make(mount)
    run_polls(obj, clock, 4)
    assert "X4" not in obj._absent
    assert [row[5] for row in read_rows(obj)[1:]] == ["", "0", "", "5"]


def test_lost_reply_between_two_parse_errors_does_not_reset_the_strike(make):
    mount = Mount(scripts={"X4": [parse_error(), TimeoutError("lost"), parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 3)
    assert "X4" in obj._absent
    assert mount.calls.count(["X4"]) == 3


def test_parse_error_from_an_ordinary_chunk_is_an_ordinary_failure(make):
    query = Mock(side_effect=parse_error())
    obj, clock = make(query)
    run_polls(obj, clock, 2)
    assert query.call_args_list[0].args == (["T1", "T2", "X3"],)
    assert query.call_count == 2  # the chunk failure ends the poll: X4/X5 not asked
    rows = read_rows(obj)[1:]
    assert all(row[-1] == f"ResponseError: {PARSE_ERROR_MESSAGE}" for row in rows)
    assert obj._after_backoff and obj._next_due == 31.0
    assert obj._absent == set() and obj._strikes == {"X4": 0, "X5": 0, "X6": 0, "X7": 0}


def test_failed_ordinary_chunk_skips_x4_and_x5_in_that_poll(make):
    variables = [f"T{i}" for i in range(1, 13)]
    mount = Mock(side_effect=[dict.fromkeys(variables[:10], 7), TimeoutError("chunk 2")])
    obj, _ = make(mount, variables=variables)
    obj.poll_once()
    assert [c.args[0] for c in mount.call_args_list] == [variables[:10], variables[10:] + ["X3"]]
    assert read_rows(obj)[1][2:] == ["7"] * 10 + ["", "", "", "", "", "", "", "2", "1", "TimeoutError: chunk 2"]


def test_stop_during_a_single_id_query_writes_no_row(make):
    obj = None

    def query(variables):
        if variables == ["X4"]:
            obj.stop()
        return dict.fromkeys(variables, 1)

    obj, _ = make(query)
    obj.poll_once()
    assert read_rows(obj) == [vl.header_row(["T1", "T2"])]


def test_stop_while_blocked_in_x5_query_on_a_real_thread(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def query(variables):
        if variables == ["X5"]:
            entered.set()
            release.wait(10)
        return dict.fromkeys(variables, 1)

    obj = vl.VariableLogger(query, ["T1"], 1.0, str(tmp_path), logging.getLogger("t"))
    try:
        assert obj.start()
        assert entered.wait(1)
        obj.stop(timeout=2.0)
        assert not obj.running
    finally:
        release.set()
        obj.stop()
    assert not obj._thread.is_alive()
    assert obj._file.closed
    assert read_rows(obj) == [vl.header_row(["T1"])]


def test_restart_begins_a_new_session_with_fresh_strikes(make):
    mount = Mount(scripts={"X4": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 2)
    assert "X4" in obj._absent
    obj.stop()
    with patch("variable_logger.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        with patch.object(obj, "_utcnow", return_value=obj._utcnow().replace(year=2030)):
            assert obj.start()
    assert obj._absent == set() and obj._strikes == {"X4": 0, "X5": 0, "X6": 0, "X7": 0}


def test_module_sends_no_new_command_kind():
    src = open(vl.__file__, encoding="utf-8").read()
    for name in ("execute_set_command", "send_command", "build_set_command", ":*!S", ":*!G"):
        assert name not in src, name

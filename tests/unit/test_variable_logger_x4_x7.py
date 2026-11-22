"""X6 / X7 and the logger's X3..X7 polling (build 2 Task 9 part A; CHARC 181842Z, ruling 182323Z).

No serial port is opened: the wire tests drive the real SerialManager.query_variables parse path
over a byte-level fake wire built on the conftest ``mock_serial_port`` fixture.
"""

import csv
from dataclasses import FrozenInstanceError
import logging
import struct
import threading
import time
from unittest.mock import Mock, patch

import pytest
import serial

import tts160_serial as ts
from tts160_serial import ResponseError, SerialManager, V357Protocol
import tts160_types as tt
import variable_logger as vl

PARSE_ERROR_MESSAGE = "Expected binary response for v357 query, got text: ERROR:PARSE_ERROR\n"
SINGLES = ["X4", "X5", "X6", "X7"]


class FakeWire:
    """pyserial-like byte stream: each write loads the mount's reply; reads never block."""

    def __init__(self, port, replies):
        self.replies = {k: list(v) if isinstance(v, list) else v for k, v in replies.items()}
        self.written = []
        self.buffer = b""
        port.write.side_effect = self.write
        port.read.side_effect = self.read
        port.read_until.side_effect = self.read_until
        port.reset_input_buffer.side_effect = self.reset

    def write(self, data):
        self.written.append(data)
        reply = self.replies.get(data, b"")
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        self.buffer = reply
        return len(data)

    def reset(self):
        self.buffer = b""

    def read(self, size=1):
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def read_until(self, expected=b"\n", size=None):
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


def parse_error():
    return ResponseError(PARSE_ERROR_MESSAGE)


class Mount:
    """Injected query: chunks answer from ``values``; single ids follow per-id scripts, else 7.

    Every call and every spacing wait is appended to ``events`` in order.
    """

    def __init__(self, values=None, scripts=None):
        self.values = values or {}
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.calls = []
        self.events = []

    def __call__(self, variables):
        self.calls.append(list(variables))
        self.events.append(list(variables))
        if len(variables) == 1 and self.scripts.get(variables[0]):
            outcome = self.scripts[variables[0]].pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome if isinstance(outcome, dict) else {variables[0]: outcome}
        return {v: self.values.get(v, 7) for v in variables}

    def wait(self, seconds):
        self.events.append(("wait", seconds))
        return False


@pytest.fixture
def make(tmp_path):
    active = []

    def factory(query, variables=("T1", "T2"), interval_s=1.0, **kwargs):
        clock = kwargs.pop("clock", Mock(return_value=0.0))
        if "wait" not in kwargs and isinstance(query, Mount):
            kwargs["wait"] = query.wait
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


def read_dicts(obj):
    rows = read_rows(obj)
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def run_polls(obj, clock, count, start=0):
    for second in range(start, start + count):
        clock.return_value = float(second)
        obj.poll_once()


GAP = ("wait", 0.02)


# ---------------------------------------------------------------- types (the contract copy)

def test_types_gain_x6_as_int32_and_x7_as_uint8():
    assert tt.ComputedVar.CABLE_REF_TICKS == 6
    assert tt.ComputedVar.CLOCK_VALID == 7
    assert [m.value for m in tt.ComputedVar] == [1, 2, 3, 4, 5, 6, 7]
    assert tt.VARIABLE_TYPES[("X", 6)] == "i"
    assert tt.VARIABLE_TYPES[("X", 7)] == "B"
    assert ("X", 8) not in tt.VARIABLE_TYPES


def test_static_format_path_decodes_a_negative_x6():
    """V357Protocol's table-driven path (VARIABLE_TYPES) must also read X6 as signed 32-bit."""
    fmt = V357Protocol.build_format_string(["X6", "X7"])
    assert fmt == "iB"
    data = struct.pack("<iB", -123456, 1)
    assert V357Protocol.parse_response(["X6", "X7"], fmt, data) == {"X6": -123456, "X7": 1}


# ---------------------------------------------------------------- the wire decode

@pytest.mark.parametrize("ticks", [-1, -123456, -(2 ** 31), 0, 987654, 2 ** 31 - 1])
def test_wire_decodes_x6_as_signed_32_bit_ticks(manager, mock_serial_port, ticks):
    """The firmware answers X6 with "BINARY:1i" and the int32's four little-endian bytes."""
    FakeWire(mock_serial_port, {b":*!G X6#": b"BINARY:1i\n" + struct.pack("<i", ticks)})
    assert manager.query_variables(["X6"]) == {"X6": ticks}


@pytest.mark.parametrize("valid", [0, 1])
def test_wire_decodes_x7_as_uint8(manager, mock_serial_port, valid):
    FakeWire(mock_serial_port, {b":*!G X7#": b"BINARY:1B\n" + bytes([valid])})
    assert manager.query_variables(["X7"]) == {"X7": valid}


def test_logger_over_the_wire_writes_a_negative_x6_and_x7(manager, mock_serial_port, tmp_path):
    wire = FakeWire(mock_serial_port, {
        b":*!G T1,X3#": b"BINARY:1f1H\n" + struct.pack("<fH", 1.5, 2000),
        b":*!G X4#": b"BINARY:1H\n" + struct.pack("<H", 1400),
        b":*!G X5#": b"BINARY:1H\n" + struct.pack("<H", 90),
        b":*!G X6#": b"BINARY:1i\n" + struct.pack("<i", -123456),
        b":*!G X7#": b"BINARY:1B\n" + b"\x01",
    })
    obj = vl.VariableLogger(manager.query_variables, ["T1"], 1.0, str(tmp_path), logging.getLogger("t"),
                            clock=Mock(return_value=0.0), wait=Mock(return_value=False))
    with patch("variable_logger.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        assert obj.start()
    try:
        obj.poll_once()
    finally:
        obj.stop()
    assert wire.written == [b":*!G T1,X3#", b":*!G X4#", b":*!G X5#", b":*!G X6#", b":*!G X7#"]
    row = read_dicts(obj)[0]
    assert (row["T1"], row["X3"], row["X4"], row["X5"], row["X6"], row["X7"]) == \
        ("1.5", "2000", "1400", "90", "-123456", "1")
    assert (row["queries"], row["failed"], row["error"]) == ("5", "0", "")


# ---------------------------------------------------------------- header, list, order

def test_header_is_exact():
    assert vl.header_row(["T1", "T2"]) == ["utc", "elapsed_s", "T1", "T2", "X3", "X4", "X5", "X6", "X7",
                                           "queries", "failed", "error"]


@pytest.mark.parametrize("fixed", ["X6", "X7"])
def test_configured_list_naming_x6_or_x7_is_refused(fixed):
    with pytest.raises(vl.VariableListError, match=fixed):
        vl.validate_variables(["T1", fixed])


def test_x3_stays_in_the_chunk_and_x4_to_x7_are_one_id_per_query(make):
    mount = Mount()
    obj, _ = make(mount)
    obj.poll_once()
    assert mount.calls == [["T1", "T2", "X3"], ["X4"], ["X5"], ["X6"], ["X7"]]
    rows = read_rows(obj)
    assert len(rows[1]) == len(rows[0])


# ---------------------------------------------------------------- the >= 20 ms after X4

def test_x4_query_is_followed_by_the_gap_before_the_next_query(make):
    mount = Mount()
    obj, _ = make(mount)
    obj.poll_once()
    assert mount.events == [["T1", "T2", "X3"], ["X4"], GAP, ["X5"], ["X6"], ["X7"]]


@pytest.mark.parametrize("outcome", [400, parse_error(), TimeoutError("lost"), ResponseError("garbled")],
                         ids=["value", "not_found", "timeout", "other_failure"])
def test_x4_gap_follows_valid_answers_and_failures_stop_the_poll(make, outcome):
    mount = Mount(scripts={"X4": [outcome]})
    obj, _ = make(mount)
    obj.poll_once()
    if isinstance(outcome, Exception) and not vl.is_not_found(outcome):
        assert mount.events == [["T1", "T2", "X3"], ["X4"]]
    else:
        assert mount.events == [["T1", "T2", "X3"], ["X4"], GAP, ["X5"], ["X6"], ["X7"]]


def test_the_gap_follows_x4_when_x5_to_x7_are_absent(make):
    """With nothing after X4 in the poll, the next query is the next poll's chunk: the gap still holds."""
    mount = Mount(scripts={v: [parse_error(), parse_error()] for v in ("X5", "X6", "X7")})
    obj, clock = make(mount)
    run_polls(obj, clock, 4)
    assert mount.events[-6:] == [["T1", "T2", "X3"], ["X4"], GAP, ["T1", "T2", "X3"], ["X4"], GAP]


def test_the_gap_follows_x4_on_the_back_off_path(make):
    mount = Mount(scripts={"X4": [TimeoutError("a"), TimeoutError("b"), 4]})
    obj, clock = make(mount)
    run_polls(obj, clock, 2)
    assert obj._after_backoff
    clock.return_value = obj._next_due
    obj.poll_once()  # second X4 failure: immediately back off again
    clock.return_value = obj._next_due
    obj.poll_once()  # successful probe
    per_poll = [["T1", "T2", "X3"], ["X4"], GAP, ["X5"], ["X6"], ["X7"]]
    assert mount.events == [["T1", "T2", "X3"], ["X4"]] * 2 + per_poll


def test_no_gap_when_x4_is_absent(make):
    mount = Mount(scripts={"X4": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 3)
    assert mount.events[-4:] == [["T1", "T2", "X3"], ["X5"], ["X6"], ["X7"]]


def test_the_gap_is_at_least_20_ms_on_the_real_clock(tmp_path):
    """The default wait (the stop event): measure X4's return to the next query's start."""
    stamps = []

    def query(variables):
        stamps.append(("in", variables[0], time.perf_counter()))
        values = dict.fromkeys(variables, 1)
        stamps.append(("out", variables[0], time.perf_counter()))
        return values

    clock = Mock(return_value=0.0)
    obj = vl.VariableLogger(query, ["T1"], 1.0, str(tmp_path), logging.getLogger("t"), clock=clock)
    with patch("variable_logger.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        assert obj.start()
    try:
        obj.poll_once()
        obj._absent.update({"X5", "X6", "X7"})  # the next query is now the next poll's chunk
        for when in (1.0, 2.0):
            clock.return_value = when
            obj.poll_once()
    finally:
        obj.stop()
    gaps = [stamps[i + 1][2] - stamps[i][2] for i in range(len(stamps) - 1)
            if stamps[i][:2] == ("out", "X4")]
    assert len(gaps) == 2
    assert all(gap >= 0.020 for gap in gaps), gaps


def test_stop_during_the_gap_writes_no_row_and_asks_nothing_more(make):
    mount = Mount()
    obj, _ = make(mount, wait=Mock(return_value=True))  # the stop event was set
    obj.poll_once()
    assert mount.calls == [["T1", "T2", "X3"], ["X4"]]
    assert read_rows(obj) == [vl.header_row(["T1", "T2"])]


# ---------------------------------------------------------------- build 1: no X6 / X7

def test_build_1_drops_x6_and_x7_and_keeps_polling_x3_to_x5(make, caplog):
    mount = Mount(values={"X3": 3000},
                  scripts={"X4": [401, 402, 403, 404], "X5": [51, 52, 53, 54],
                           "X6": [parse_error(), parse_error()], "X7": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    with caplog.at_level(logging.INFO, logger="t"):
        run_polls(obj, clock, 4)
    assert mount.calls == ([["T1", "T2", "X3"], ["X4"], ["X5"], ["X6"], ["X7"]] * 2
                           + [["T1", "T2", "X3"], ["X4"], ["X5"]] * 2)
    assert obj._absent == {"X6", "X7"}
    rows = read_dicts(obj)
    assert [(r["X3"], r["X4"], r["X5"], r["X6"], r["X7"]) for r in rows] == \
        [("3000", f"40{i}", f"5{i}", "absent", "absent") for i in range(1, 5)]
    assert [(r["queries"], r["failed"], r["error"]) for r in rows] == \
        [("5", "0", "")] * 2 + [("3", "0", "")] * 2
    assert [float(r["elapsed_s"]) for r in rows] == [0.0, 1.0, 2.0, 3.0]  # no back-off
    assert obj._consecutive_failures == 0
    for variable in ("X6", "X7"):
        lines = [r.getMessage() for r in caplog.records if variable in r.getMessage()]
        assert len(lines) == 2 and "may be absent" in lines[0] and "may be absent" not in lines[1]


def test_x6_not_found_does_not_stop_x7_in_the_same_poll(make):
    mount = Mount(scripts={"X6": [parse_error()], "X7": [1]})
    obj, _ = make(mount)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["X6"], row["X7"], row["error"]) == ("absent", "1", "")


def test_restart_gives_x6_and_x7_fresh_strikes(make):
    mount = Mount(scripts={"X6": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 2)
    assert "X6" in obj._absent
    obj.stop()
    with patch("variable_logger.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        with patch.object(obj, "_utcnow", return_value=obj._utcnow().replace(year=2030)):
            assert obj.start()
    assert obj._absent == set() and obj._strikes == dict.fromkeys(SINGLES, 0)


# ---------------------------------------------------------------- queries / failed (ruling 182323Z)

def test_queries_and_failed_on_a_clean_row(make):
    obj, _ = make(Mount())
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("5", "0", "")


def test_queries_and_failed_on_a_failed_chunk(make):
    variables = [f"T{i}" for i in range(1, 13)]
    query = Mock(side_effect=[dict.fromkeys(variables[:10], 7), TimeoutError("chunk 2")])
    obj, _ = make(query, variables=variables)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("2", "1", "TimeoutError: chunk 2")


def test_queries_and_failed_on_a_failed_single_id(make):
    obj, _ = make(Mount(scripts={"X5": [TimeoutError("lost")]}))
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("5", "1", "X5 TimeoutError: lost")


def test_queries_and_failed_on_an_absent_id(make):
    """A not-found answer is sent and is an answer (not failed); a dropped id is not counted."""
    obj, clock = make(Mount(scripts={"X7": [parse_error(), parse_error()]}))
    run_polls(obj, clock, 3)
    assert [(r["queries"], r["failed"]) for r in read_dicts(obj)] == [("5", "0"), ("5", "0"), ("4", "0")]


def test_format_row_places_queries_and_failed_before_error():
    from datetime import datetime, timezone
    t = datetime(2026, 1, 2, tzinfo=timezone.utc)
    row = vl.format_row(t, 0.0, ["T1"], {"T1": 1, "X6": -5, "X7": 0}, "e", queries=5, failed=1)
    assert row == ["2026-01-02T00:00:00.000Z", "0.000", "1", "", "", "", "-5", "0", "5", "1", "e"]
    assert len(row) == len(vl.header_row(["T1"]))


# ---------------------------------------------------------------- "absent" cells (ruling 183326Z)

def test_a_not_found_x6_and_x7_write_absent(make):
    mount = Mount(scripts={"X6": [parse_error()], "X7": [parse_error()]})
    obj, _ = make(mount)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["X4"], row["X5"], row["X6"], row["X7"]) == ("7", "7", "absent", "absent")
    assert (row["queries"], row["failed"], row["error"]) == ("5", "0", "")
    assert obj._strikes["X6"] == 1 and obj._absent == set()  # one strike: still asked


def test_an_id_after_two_strikes_writes_absent_without_being_asked(make):
    mount = Mount(scripts={"X6": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 3)
    assert mount.calls.count(["X6"]) == 2
    assert [r["X6"] for r in read_dicts(obj)] == ["absent"] * 3
    assert [r["queries"] for r in read_dicts(obj)] == ["5", "5", "4"]


def test_a_failed_single_id_query_leaves_its_cell_blank(make):
    mount = Mount(scripts={"X6": [TimeoutError("lost")], "X4": [ResponseError("garbled")]})
    obj, _ = make(mount)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["X4"], row["X5"], row["X6"], row["X7"]) == ("", "", "", "")
    assert (row["queries"], row["failed"]) == ("2", "1")  # X6 was never attempted
    assert mount.calls == [["T1", "T2", "X3"], ["X4"]]


def test_ids_not_sent_after_a_failed_chunk_are_blank_and_a_dropped_id_stays_absent(make):
    query = Mount(scripts={"X7": [parse_error(), parse_error()]})
    obj, clock = make(query)
    run_polls(obj, clock, 2)  # X7 dropped
    obj._query = Mock(side_effect=TimeoutError("chunk"))
    clock.return_value = 2.0
    obj.poll_once()
    row = read_dicts(obj)[-1]
    assert (row["X3"], row["X4"], row["X5"], row["X6"], row["X7"]) == ("", "", "", "", "absent")
    assert (row["queries"], row["failed"], row["error"]) == ("1", "1", "TimeoutError: chunk")


# ---------------------------------------------------------------- T9A-FIX: wire attempts, per caller, and failed X4

def fail_writes(port, wire, failures):
    """Fail a specified number of writes per command before serving the fake reply."""
    remaining = dict(failures)

    def write(data):
        if remaining.get(data, 0):
            remaining[data] -= 1
            raise serial.SerialException("injected failed write")
        return wire.write(data)

    port.write.side_effect = write


@pytest.mark.parametrize("queued", [False, True], ids=["direct", "queued"])
@pytest.mark.parametrize("failures", [0, 2, 5, 6])
def test_attempt_record_counts_each_write_attempt(manager, mock_serial_port, queued, failures):
    wire = FakeWire(mock_serial_port, {b":*!G X6#": b"BINARY:i\n" + struct.pack("<i", -7)})
    fail_writes(mock_serial_port, wire, {b":*!G X6#": failures})
    if queued:
        manager._start_worker()
    try:
        if failures == 6:
            with pytest.raises(ts.ConnectionError, match="6 attempts"):
                manager.query_variables(["X6"])
        else:
            assert manager.query_variables(["X6"]) == {"X6": -7}
        record = ts.get_last_command_attempts()
        assert (record.attempts, record.failed) == (min(failures + 1, 6), failures)
        assert mock_serial_port.write.call_count == min(failures + 1, 6)
    finally:
        manager._stop_worker()


def test_reviewer_probe_five_failed_writes_then_success_has_empty_error(manager, mock_serial_port, make):
    wire = FakeWire(mock_serial_port, {b":*!G T1,T2,X3#": b"BINARY:2fH\n" + struct.pack("<2fH", 1, 2, 3)})
    fail_writes(mock_serial_port, wire, {b":*!G T1,T2,X3#": 5})
    obj, _ = make(lambda variables: manager.query_variables(variables))  # same indirection as the device
    obj._absent.update(SINGLES)  # isolate the probe's one call
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("6", "5", "")
    assert (row["T1"], row["T2"], row["X3"]) == ("1.0", "2.0", "3")
    assert mock_serial_port.write.call_count == 6


def test_disconnected_port_counts_six_failed_attempts(manager, mock_serial_port, make):
    mock_serial_port.is_open = False
    obj, _ = make(manager.query_variables)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"]) == ("6", "6")
    assert row["error"] == "ConnectionError: Command failed after 6 attempts"
    record = ts.get_last_command_attempts()
    assert (record.attempts, record.failed) == (6, 6)
    mock_serial_port.write.assert_not_called()


@pytest.mark.parametrize("not_found", [False, True], ids=["clean", "not_found"])
def test_wire_answers_count_one_without_failure(manager, mock_serial_port, make, not_found):
    replies = {b":*!G T1,T2,X3#": b"BINARY:2fH\n" + struct.pack("<2fH", 1, 2, 3)}
    replies.update({f":*!G {v}#".encode(): b"BINARY:H\n" + struct.pack("<H", 7) for v in SINGLES})
    if not_found:
        replies[b":*!G X4#"] = b"ERROR:PARSE_ERROR\n"
    wire = FakeWire(mock_serial_port, replies)
    records = []

    def query(variables):
        try:
            return manager.query_variables(variables)
        finally:
            records.append(ts.get_last_command_attempts())

    obj, _ = make(query)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("5", "0", "")
    assert [(r.attempts, r.failed) for r in records] == [(1, 0)] * 5
    assert row["X4"] == ("absent" if not_found else "7")
    assert wire.written == [b":*!G T1,T2,X3#", *[f":*!G {v}#".encode() for v in SINGLES]]


def test_row_sums_attempts_across_all_chunks_and_single_ids(manager, mock_serial_port, make):
    chunks = vl.chunk_variables((*vl.DEFAULT_VARIABLES, "X3"))
    groups = [*chunks, *[[v] for v in SINGLES]]
    commands = [V357Protocol.build_query(group).encode() for group in groups]
    replies = {command: b"BINARY:" + f"{len(group)}H\n".encode() + struct.pack(f"<{len(group)}H", *([7] * len(group)))
               for command, group in zip(commands, groups)}
    failures = [2, 1, 3, 1, 2, 0, 4]
    wire = FakeWire(mock_serial_port, replies)
    fail_writes(mock_serial_port, wire, dict(zip(commands, failures)))
    manager._start_worker()
    try:
        obj, _ = make(lambda variables: manager.query_variables(variables, priority=ts.CommandPriority.LOW),
                      variables=vl.DEFAULT_VARIABLES)
        obj.poll_once()
    finally:
        manager._stop_worker()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("20", "13", "")
    assert wire.written == commands
    assert mock_serial_port.write.call_count == 20


@pytest.mark.parametrize("queued", [False, True], ids=["direct", "queued"])
def test_other_callers_cannot_replace_this_threads_attempt_record(manager, mock_serial_port, queued):
    wire = FakeWire(mock_serial_port, {
        b":*!G X6#": b"BINARY:i\n" + struct.pack("<i", -7), b":*!G X7#": b"BINARY:B\n\x01",
    })
    fail_writes(mock_serial_port, wire, {b":*!G X6#": 5})
    if queued:
        manager._start_worker()
    results = []
    errors = []

    def other_caller():
        try:
            manager.query_variables(["X7"])
            record = ts.get_last_command_attempts()
            results.append((record.attempts, record.failed))
        except Exception as ex:
            errors.append(ex)

    try:
        manager.query_variables(["X6"])
        other = threading.Thread(target=other_caller)
        other.start()
        other.join(timeout=2)
        assert not other.is_alive()
        assert not errors
        assert results == [(1, 0)]
        record = ts.get_last_command_attempts()
        assert (record.attempts, record.failed) == (6, 5)
    finally:
        manager._stop_worker()


def test_timeout_record_is_fresh_and_abandoned_execution_cannot_replace_later_call(manager, mock_serial_port):
    wire = FakeWire(mock_serial_port, {
        b":*!G X6#": b"BINARY:i\n" + struct.pack("<i", -7), b":*!G X7#": b"BINARY:B\n\x01",
    })
    fail_writes(mock_serial_port, wire, {b":*!G X6#": 5})
    manager.query_variables(["X6"])  # prior record must not survive the timeout
    manager._worker_thread = Mock()  # queued request cannot execute yet
    try:
        with pytest.raises(TimeoutError, match="waiting for execution"):
            manager.send_command(":*!G X6#", timeout=0.0)
    finally:
        manager._worker_thread = None
    timed_out = ts.get_last_command_attempts()
    assert (timed_out.attempts, timed_out.failed) == (1, 1)
    manager.query_variables(["X7"])  # later call on the SAME caller thread
    later = ts.get_last_command_attempts()
    assert (later.attempts, later.failed) == (1, 0)
    fail_writes(mock_serial_port, wire, {b":*!G X6#": 5})
    manager._start_worker()
    try:
        manager._command_queue.join()  # abandoned command really runs (six attempts)
        assert wire.written == [b":*!G X6#", b":*!G X7#", b":*!G X6#"]
        assert mock_serial_port.write.call_count == 13
        assert ts.get_last_command_attempts() is later
        assert (timed_out.attempts, timed_out.failed) == (1, 1)
    finally:
        manager._stop_worker()


def test_attempt_record_resets_between_calls_and_is_read_only(manager, mock_serial_port):
    wire = FakeWire(mock_serial_port, {
        b":*!G X6#": b"BINARY:i\n" + struct.pack("<i", -7), b":*!G X7#": b"BINARY:B\n\x01",
    })
    fail_writes(mock_serial_port, wire, {b":*!G X6#": 5})
    manager.query_variables(["X6"])
    first = ts.get_last_command_attempts()
    manager.query_variables(["X7"])
    second = ts.get_last_command_attempts()
    assert (first.attempts, first.failed) == (6, 5)
    assert (second.attempts, second.failed) == (1, 0)
    with pytest.raises(FrozenInstanceError):
        second.failed = 99
    manager.query_variables(["X7"])
    assert ts.get_last_command_attempts() is not second  # fresh even when counts are equal


def test_injected_query_does_not_reuse_an_earlier_transport_record(manager, mock_serial_port, make):
    wire = FakeWire(mock_serial_port, {b":*!G X6#": b"BINARY:i\n" + struct.pack("<i", -7)})
    fail_writes(mock_serial_port, wire, {b":*!G X6#": 5})
    manager.query_variables(["X6"])
    obj, _ = make(Mount())
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert (row["queries"], row["failed"], row["error"]) == ("5", "0", "")


@pytest.mark.parametrize("failure", [TimeoutError("lost"), ResponseError("garbled"), ConnectionError("offline")])
def test_failed_x4_writes_row_skips_remaining_ids_and_backs_off_immediately(make, failure):
    mount = Mount(scripts={"X4": [failure, 4]})
    obj, clock = make(mount)
    obj.poll_once()
    assert mount.calls == [["T1", "T2", "X3"], ["X4"]]
    row = read_dicts(obj)[0]
    assert [row[v] for v in SINGLES] == [""] * 4
    assert (row["queries"], row["failed"]) == ("2", "1")
    assert row["error"] == f"X4 {type(failure).__name__}: {failure}"
    assert obj._after_backoff and obj._next_due == vl.BACKOFF_S
    for when in (1.0, vl.BACKOFF_S - 0.001):
        clock.return_value = when
        obj.poll_once()
        assert len(mount.calls) == 2
        assert len(read_dicts(obj)) == 1
    clock.return_value = vl.BACKOFF_S
    obj.poll_once()
    assert mount.calls[2:] == [["T1", "T2", "X3"], *[[v] for v in SINGLES]]
    assert len(read_dicts(obj)) == 2


def test_failed_x4_keeps_dropped_ids_absent_and_unasked_live_ids_blank(make):
    mount = Mount(scripts={"X4": [4, 4, TimeoutError("lost")], "X6": [parse_error(), parse_error()]})
    obj, clock = make(mount)
    run_polls(obj, clock, 3)
    row = read_dicts(obj)[-1]
    assert [row[v] for v in SINGLES] == ["", "", "absent", ""]
    assert mount.calls[-2:] == [["T1", "T2", "X3"], ["X4"]]
    assert mount.calls.count(["X6"]) == 2
    assert obj._absent == {"X6"}  # retain session state


# ---------------------------------------------------------------- review r1: caller verdict and retained coverage

@pytest.mark.parametrize("case,wire_failures", [
    ("x4_invalid_text", 0), ("chunk_parse_error", 0),
    ("x4_invalid_text", 2), ("x4_corrupt_binary", 0),
])
def test_invalid_wire_answer_counts_final_attempt_as_failed(manager, mock_serial_port, make, case, wire_failures):
    command = b":*!G T1,T2,X3#" if case == "chunk_parse_error" else b":*!G X4#"
    reply = {
        "x4_invalid_text": b"ERROR:VAR_ERROR\n",
        "chunk_parse_error": b"ERROR:PARSE_ERROR\n",
        "x4_corrupt_binary": b"BINARY:H\n\x01",  # truncated value falls back to text
    }[case]
    wire = FakeWire(mock_serial_port, {
        b":*!G T1,T2,X3#": b"BINARY:2fH\n" + struct.pack("<2fH", 1, 2, 3), command: reply,
    })
    fail_writes(mock_serial_port, wire, {command: wire_failures})
    obj, _ = make(manager.query_variables)
    if case != "chunk_parse_error":
        # Read the ordinary chunk before counting only the rejected single-id call.
        ordinary_chunk_attempts = 1
    else:
        ordinary_chunk_attempts = 0
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert row["error"].startswith("ResponseError:" if case == "chunk_parse_error" else "X4 ResponseError:")
    assert int(row["failed"]) == wire_failures + 1
    assert int(row["queries"]) == ordinary_chunk_attempts + wire_failures + 1
    record = ts.get_last_command_attempts()
    assert (record.attempts, record.failed) == (wire_failures + 1, wire_failures)  # wire outcome is unchanged
    assert mock_serial_port.write.call_count == int(row["queries"])


def test_two_non_x4_failures_are_joined_and_both_cells_blank(make):
    mount = Mount(scripts={"X5": [TimeoutError("lost")], "X6": [ResponseError("garbled")]})
    obj, _ = make(mount)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert row["error"] == "X5 TimeoutError: lost; X6 ResponseError: garbled"
    assert (row["X5"], row["X6"], row["X7"]) == ("", "", "7")
    assert (row["queries"], row["failed"]) == ("5", "2")


@pytest.mark.parametrize("variable", ["X5", "X6", "X7"])
def test_failed_non_x4_single_id_leaves_own_cell_blank(make, variable):
    mount = Mount(scripts={variable: [TimeoutError("lost")]})
    obj, _ = make(mount)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert row[variable] == ""
    assert row["error"] == f"{variable} TimeoutError: lost"
    assert row["failed"] == "1"
    assert mount.calls == [["T1", "T2", "X3"], *[[v] for v in SINGLES]]


@pytest.mark.parametrize("where,outcome,has_error", [
    ("chunk", parse_error(), True), ("chunk", TimeoutError("lost"), True),
    ("X4", ResponseError("garbled"), True), ("X5", TimeoutError("lost"), True),
    ("X4", parse_error(), False), ("X6", 7, False),
])
def test_every_nonempty_error_has_at_least_one_failed_attempt(make, where, outcome, has_error):
    mount = Mount(scripts={where: [outcome]})

    def query(variables):
        if where == "chunk":
            raise outcome
        return mount(variables)

    obj, _ = make(query)
    obj.poll_once()
    row = read_dicts(obj)[0]
    assert bool(row["error"]) is has_error
    assert 0 <= int(row["failed"]) <= int(row["queries"])
    if row["error"]:
        assert int(row["failed"]) >= 1
    else:
        assert row["failed"] == "0"

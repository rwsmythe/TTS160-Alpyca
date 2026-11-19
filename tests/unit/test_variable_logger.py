"""Read-only variable logger tests; no serial port is opened."""

import csv
import datetime as dt
import io

import pytest

import variable_logger as vl


def test_default_list_is_valid_and_two_queries():
    assert vl.validate_variables(vl.DEFAULT_VARIABLES) == vl.DEFAULT_VARIABLES
    assert [len(c) for c in vl.chunk_variables(vl.DEFAULT_VARIABLES)] == [10, 10]


@pytest.mark.parametrize("bad", [[], ["T0"], ["T100"], ["Q1"], ["t1"], ["T1", "T1"],
                                 ["T31"], ["T32"], ["T1 "], ["T"], [f"T{i}" for i in range(1, 22)]])
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

"""The FS-lines record kept with an assembled event (D30 follow-up): a round trip, and the
shapes an older or incomplete event may carry, which yield no record rather than an error."""

from __future__ import annotations

import uuid

from oak_binder.services import fs_lines
from oak_binder.services.spine_client import SpineLine

VERSION_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _lines() -> fs_lines.FsLines:
    cash = SpineLine(
        "BS.A.1", "Cash and cash equivalents", "assets", 2, None, "1250000.00", None, True
    )
    revenue = SpineLine(
        "PL.R.1", "Revenue from operations", "income", 1, "I", "9800000.00", "9100000.00", True
    )
    return fs_lines.FsLines(True, None, True, {cash.head_id: cash, revenue.head_id: revenue})


def test_lines_round_trip_through_the_event_record() -> None:
    record = fs_lines.to_record(_lines(), VERSION_ID)
    assert record["record_version"] == 1
    assert record["version_id"] == str(VERSION_ID) and record["version_locked"] is True
    assert [line["head_id"] for line in record["lines"]] == ["BS.A.1", "PL.R.1"]
    back = fs_lines.from_record(record)
    assert back is not None and back.available and back.reason is None and back.version_locked
    assert back.lines == _lines().lines
    assert back.label("PL.R.1") == "Revenue from operations" and back.label("BS.X") is None


def test_records_an_older_event_may_carry_yield_no_lines() -> None:
    assert fs_lines.from_record(None) is None  # the key was never written
    assert fs_lines.from_record({}) is None
    assert fs_lines.from_record({"lines": "not a list"}) is None
    assert fs_lines.from_record({"lines": [{"label": "no head id"}]}) is None
    assert fs_lines.from_record("BS.A.1") is None


def test_a_record_is_read_defensively() -> None:
    sparse = {"version_locked": "yes", "lines": [{"head_id": "BS.A.1"}]}
    back = fs_lines.from_record(sparse)
    assert back is not None and back.version_locked is True
    assert back.lines["BS.A.1"] == SpineLine(
        "BS.A.1", "BS.A.1", None, None, None, None, None, False
    )

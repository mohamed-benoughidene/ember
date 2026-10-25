"""Unit tests for the shared Phase-4 report formatter."""

from __future__ import annotations

from ember.maintain.report import format_report
from ember.maintain.rows import StatusChange


def _change(
    item_id: int,
    old_status: str,
    new_status: str,
    close_reason: str | None = None,
) -> StatusChange:
    return StatusChange(
        item_id=item_id,
        old_status=old_status,
        new_status=new_status,
        close_reason=close_reason,
        trigger_cause="test_cause",
        link_id=None,
    )


def test_close_line_carries_reason() -> None:
    lines = format_report([_change(3, "Active", "Closed", "superseded")], 10)

    assert lines[0] == "item 3: Active -> Closed (superseded)"
    assert lines[-1] == "closed: 1, challenged: 0, reopened: 0, unchanged: 9"


def test_challenge_line_has_no_reason() -> None:
    lines = format_report([_change(5, "Active", "Challenged")], 1)

    assert lines[0] == "item 5: Active -> Challenged"


def test_close_without_reason_has_no_parens() -> None:
    lines = format_report([_change(7, "Active", "Closed")], 1)

    assert lines[0] == "item 7: Active -> Closed"


def test_lines_ordered_by_item_id_and_summary_last() -> None:
    lines = format_report(
        [
            _change(9, "Active", "Challenged"),
            _change(2, "Active", "Closed", "answered"),
            _change(5, "Active", "Challenged"),
        ],
        10,
    )

    assert lines[:3] == [
        "item 2: Active -> Closed (answered)",
        "item 5: Active -> Challenged",
        "item 9: Active -> Challenged",
    ]
    assert lines[3] == "closed: 1, challenged: 2, reopened: 0, unchanged: 7"


def test_summary_buckets_cover_close_challenge_and_reopen() -> None:
    lines = format_report(
        [
            _change(1, "Active", "Closed", "superseded"),
            _change(2, "Active", "Challenged"),
            _change(3, "Closed", "Active"),
        ],
        10,
    )

    assert lines[-1] == "closed: 1, challenged: 1, reopened: 1, unchanged: 7"


def test_empty_changes_reports_all_unchanged() -> None:
    lines = format_report([], 4)

    assert lines == ["closed: 0, challenged: 0, reopened: 0, unchanged: 4"]

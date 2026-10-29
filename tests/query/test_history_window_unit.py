"""Unit tests for the history window: since cut, then offset, then limit.

Pure-core tests on plain rows (T3, no I/O). Timestamps are fixed strings so
the window is deterministic on every machine.
"""

from __future__ import annotations

import pytest

from ember.query.errors import QueryFilterInvalid, QuerySinceInvalid
from ember.query.history import history
from ember.query.query_gatekeeper import validate_history_page
from ember.query.rows import HistoryPage
from tests.query.fakes import make_change_row, make_link


def _five_rows(item_id: int | None = 1):
    """Five rows on item 1 (or NULL subjects when `item_id` is None)."""
    rows = []
    for day in range(1, 6):
        rows.append(
            make_change_row(
                day,
                item_id=item_id,
                timestamp=f"2026-01-0{day}T00:00:00+00:00",
            )
        )
    return rows


def test_history_page_windows_within_the_union_rule() -> None:
    # Row 2 matches item 1 by subject AND by its link (link 10 joins 1 -> 2),
    # so it is the both-branches row and must still appear exactly once.
    row_subject = make_change_row(
        1, item_id=1, timestamp="2026-01-01T00:00:00+00:00"
    )
    row_both = make_change_row(
        2, item_id=1, link_id=10, timestamp="2026-01-02T00:00:00+00:00"
    )
    row_null = make_change_row(
        3, item_id=None, timestamp="2026-01-03T00:00:00+00:00"
    )
    rows = [row_subject, row_both, row_null]
    links = [make_link(10, 1, 2)]

    # The window applies AFTER the union rule and the sort, on both views.
    full = history(rows, links, 1)
    assert [event.item_id for event in full] == [1, 1]

    # Union first, then sort, then the crop: offset 1 skips the earlier row.
    item_page = history(
        rows, links, 1, HistoryPage(offset=1, limit=1)
    )
    assert len(item_page) == 1
    assert item_page[0].item_id == 1
    assert item_page[0].old_value == row_both.old_value

    # The NULL-subject row stays global-only, behind the same window rule.
    global_page = history(
        rows, links, None, HistoryPage(offset=1, limit=10)
    )
    assert [event.item_id for event in global_page] == [1, None]


def test_since_drops_older_rows() -> None:
    rows = [
        make_change_row(1, timestamp="2026-01-14T00:00:00+00:00"),
        # The boundary row: kept, the comparison is `>=` on ISO text.
        make_change_row(2, timestamp="2026-01-15T00:00:00+00:00"),
        make_change_row(3, timestamp="2026-01-16T00:00:00+00:00"),
    ]

    page = validate_history_page(HistoryPage(since="2026-01-15T00:00:00+00:00"))
    events = history(rows, [], None, page)
    assert [event.timestamp for event in events] == [
        "2026-01-15T00:00:00+00:00",
        "2026-01-16T00:00:00+00:00",
    ]

    # The same view scoped to one item drops the same older rows (all three
    # rows carry item_id 1, so the item view holds all of them).
    page_item = validate_history_page(
        HistoryPage(since="2026-01-15T00:00:00+00:00")
    )
    kept = history(rows, [], 1, page_item)
    assert [event.timestamp for event in kept] == [
        "2026-01-15T00:00:00+00:00",
        "2026-01-16T00:00:00+00:00",
    ]

    # The TZ case: the row is stamped tz-aware UTC and the since is a
    # different offset spelling of the same instant. Normalisation lands the
    # boundary on the same nominal UTC instant, so the boundary row is not
    # lost to a spelling.
    tz_page = validate_history_page(HistoryPage(since="2026-01-15T02:00:00+02:00"))
    assert tz_page.since == "2026-01-15T00:00:00+00:00"
    assert [event.timestamp for event in history(rows, [], None, tz_page)] == [
        "2026-01-15T00:00:00+00:00",
        "2026-01-16T00:00:00+00:00",
    ]

    # Spellings `fromisoformat` accepts, pinned here (G.2): a space
    # separator and fractional seconds, both with an offset.
    space_page = validate_history_page(
        HistoryPage(since="2026-01-15 00:00:00+00:00")
    )
    assert space_page.since == "2026-01-15T00:00:00+00:00"
    fraction_page = validate_history_page(
        HistoryPage(since="2026-01-15T00:00:00.500000+00:00")
    )
    assert fraction_page.since == "2026-01-15T00:00:00.500000+00:00"
    # A date-only spelling parses as a naive datetime, so it is QUERY-007.
    with pytest.raises(QuerySinceInvalid):
        validate_history_page(HistoryPage(since="2026-01-15"))


def test_offset_skips_then_limit_caps() -> None:
    rows = _five_rows()

    # Defaulted page behaves exactly like the no-argument call.
    assert history(rows, [], None) == history(rows, [], None, HistoryPage())

    # Offset skips after the sort, limit caps after the skip.
    assert [
        event.item_id for event in history(rows, [], None, HistoryPage(offset=4))
    ] == [1, 1, 1, 1, 1][4:]
    assert [
        event.item_id
        for event in history(rows, [], None, HistoryPage(offset=2, limit=2))
    ] == [1, 1]

    # The ledger order still runs timestamp then id behind the crop.
    assert [
        event.timestamp for event in history(rows, [], None, HistoryPage(limit=3))
    ] == [
        "2026-01-01T00:00:00+00:00",
        "2026-01-02T00:00:00+00:00",
        "2026-01-03T00:00:00+00:00",
    ]

    # limit 0 is an explicit empty list, offset past the end is [] too.
    assert history(rows, [], None, HistoryPage(limit=0)) == []
    assert history(rows, [], None, HistoryPage(offset=99)) == []

    # Both edges on the item view as well.
    assert history(rows, [], 1, HistoryPage(limit=0)) == []
    assert history(rows, [], 1, HistoryPage(offset=99)) == []
    assert [
        event.item_id
        for event in history(rows, [], 1, HistoryPage(offset=4, limit=1))
    ] == [1]


def test_validate_history_page_raises_query_007() -> None:
    # Unparseable text: the context carries the length, never the raw text.
    with pytest.raises(QuerySinceInvalid) as yesterday:
        validate_history_page(HistoryPage(since="yesterday"))
    assert yesterday.value.context == {"since_length": 9}

    with pytest.raises(QuerySinceInvalid) as empty:
        validate_history_page(HistoryPage(since=""))
    assert empty.value.context == {"since_length": 0}

    # A parseable but naive spelling names no offset, so it is rejected
    # (astimezone on naive input would assume the local machine clock).
    with pytest.raises(QuerySinceInvalid) as naive:
        validate_history_page(HistoryPage(since="2026-10-01T00:00:00"))
    assert naive.value.context == {"since_length": 19}

    # A valid aware spelling comes back normalised to UTC.
    page = validate_history_page(HistoryPage(since="2026-01-15T02:00:00+02:00"))
    assert page.since == "2026-01-15T00:00:00+00:00"


def test_validate_history_page_raises_query_006_through_the_shared_helper() -> None:
    with pytest.raises(QueryFilterInvalid) as limit:
        validate_history_page(HistoryPage(limit=-1))
    assert limit.value.context == {"field": "limit"}

    with pytest.raises(QueryFilterInvalid) as offset:
        validate_history_page(HistoryPage(offset=-1))
    assert offset.value.context == {"field": "offset"}

"""Unit tests for the pure `current_state` core."""

from __future__ import annotations

from ember.query.current_state import current_state
from tests.query.fakes import make_item


def test_keeps_active_and_challenged_and_drops_closed() -> None:
    items = [
        make_item(1, status="Active"),
        make_item(2, status="Challenged"),
        make_item(3, status="Closed", close_reason="expired"),
    ]

    rows = current_state(items)

    assert [row.id for row in rows] == [1, 2]


def test_challenged_flag_is_true_only_for_challenged() -> None:
    rows = current_state(
        [make_item(1, status="Active"), make_item(2, status="Challenged")]
    )

    assert [(row.id, row.challenged) for row in rows] == [(1, False), (2, True)]


def test_output_row_drops_close_reason_and_rationale() -> None:
    items = [
        make_item(
            1,
            status="Active",
            close_reason="expired",
            rationale="a private note",
        )
    ]

    fields = current_state(items)[0].model_dump()

    assert "close_reason" not in fields
    assert "rationale" not in fields


def test_core_returns_the_input_order() -> None:
    items = [
        make_item(9, status="Active"),
        make_item(3, status="Challenged"),
        make_item(7, status="Active"),
        make_item(1, status="Challenged"),
    ]

    rows = current_state(items)

    assert [row.id for row in rows] == [9, 3, 7, 1]


def test_empty_input_returns_an_empty_list() -> None:
    assert current_state([]) == []

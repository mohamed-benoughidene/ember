"""Unit tests for relate phase 1 (load + filter), no DB."""

from __future__ import annotations

import pytest

from ember.relate.errors import ItemIdNotFound
from ember.relate.load_filter import load_and_filter
from ember.relate.rows import Link, NewItem
from tests.relate.fakes import FakeLinkLookup

FIXED_TIME = "2026-01-01T00:00:00+00:00"
DB_PATH = "/tmp/ember-relate-test.db"


def _item(item_id: int, item_type: str) -> NewItem:
    return NewItem(
        id=item_id,
        type=item_type,
        statement=f"statement {item_id}",
        created_at=FIXED_TIME,
    )


def _link(
    link_id: int,
    source_id: int,
    target_id: int,
    link_type: str,
    status: str = "Confirmed",
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_id,
        target_item_id=target_id,
        link_type=link_type,
        status=status,
        created_at=FIXED_TIME,
    )


def test_item_happy_path_keeps_only_type_compatible_candidates() -> None:
    lookup = FakeLinkLookup(
        items=[
            _item(1, "Question"),
            _item(2, "Decision"),
            _item(3, "Assumption"),
            _item(4, "Finding"),
            _item(5, "Question"),
        ]
    )

    result = load_and_filter(lookup, item_id=1, db_path=DB_PATH)

    assert result is not None
    assert result.new_item.id == 1
    assert [item.id for item in result.universe.items] == [5]


def test_missing_item_raises_item_id_not_found() -> None:
    lookup = FakeLinkLookup(items=[_item(1, "Question")])

    with pytest.raises(ItemIdNotFound) as excinfo:
        load_and_filter(lookup, item_id=999, db_path=DB_PATH)

    assert excinfo.value.code == "RELATE-001"
    assert "999" in str(excinfo.value)
    assert DB_PATH in excinfo.value.message


def test_latest_with_no_eligible_item_returns_none() -> None:
    lookup = FakeLinkLookup(items=[_item(1, "Question")], latest=None)

    assert load_and_filter(lookup, latest=True, db_path=DB_PATH) is None


def test_filter_one_keeps_candidate_when_another_type_remains() -> None:
    lookup = FakeLinkLookup(
        items=[_item(1, "Finding"), _item(2, "Decision"), _item(3, "Decision")],
        links=[
            _link(101, 1, 2, "supports"),
            _link(102, 1, 3, "supports"),
            _link(103, 1, 3, "contradicts"),
        ],
    )

    result = load_and_filter(lookup, item_id=1, db_path=DB_PATH)

    assert result is not None
    assert [item.id for item in result.universe.items] == [2]


def test_filter_two_drops_incompatible_and_keeps_compatible() -> None:
    lookup = FakeLinkLookup(
        items=[_item(1, "Question"), _item(2, "Question"), _item(3, "Decision")]
    )

    result = load_and_filter(lookup, item_id=1, db_path=DB_PATH)

    assert result is not None
    assert [item.id for item in result.universe.items] == [2]

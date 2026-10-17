"""Integration tests for `SqliteLinkContext.neighbors_of` on a real SQLite DB.

The graph signal of relate phase 2 is 1-hop only: every Confirmed link that
touches the item, from either side, deduplicated and sorted. Rejected links
never count, and a read failure surfaces as RELATE-021 (plan step 2 section 4
step 4 and section 5).
"""

from __future__ import annotations

import sqlite3

import pytest

from ember.adapters.sqlite import SqliteLinkContext, open_database
from ember.relate.errors import GraphReadFailed
from tests.fakes import FIXED_TIME, insert_item, insert_source


class BrokenConnection:
    """A connection whose every statement fails, to drive the RELATE-021 path."""

    def execute(self, *args: object, **kwargs: object) -> object:
        raise sqlite3.OperationalError("boom")


def _insert_link(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    link_type: str,
    status: str,
) -> None:
    conn.execute(
        "INSERT INTO links (source_item_id, target_item_id, link_type, status,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (source_id, target_id, link_type, status, FIXED_TIME),
    )


def _seed_items(conn: sqlite3.Connection, count: int) -> None:
    source_id = insert_source(conn)
    for item_id in range(1, count + 1):
        insert_item(conn, source_id=source_id, item_id=item_id)
    conn.commit()


def test_confirmed_links_count_from_either_side(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 3)
    _insert_link(conn, 1, 2, "supports", "Confirmed")
    _insert_link(conn, 3, 1, "answers", "Confirmed")

    assert SqliteLinkContext(conn).neighbors_of(1) == [2, 3]


def test_rejected_links_are_excluded(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 4)
    _insert_link(conn, 1, 2, "supports", "Confirmed")
    _insert_link(conn, 1, 3, "supports", "Rejected")
    _insert_link(conn, 4, 1, "supports", "Rejected")

    assert SqliteLinkContext(conn).neighbors_of(1) == [2]


def test_an_item_with_only_rejected_links_has_no_neighbors(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 2)
    _insert_link(conn, 1, 2, "contradicts", "Rejected")

    assert SqliteLinkContext(conn).neighbors_of(1) == []


def test_no_links_at_all_returns_an_empty_list(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 2)

    assert SqliteLinkContext(conn).neighbors_of(1) == []


def test_neighbors_are_sorted_and_deduplicated(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 4)
    _insert_link(conn, 1, 3, "supports", "Confirmed")
    _insert_link(conn, 3, 1, "supports", "Confirmed")
    _insert_link(conn, 1, 3, "depends_on", "Confirmed")
    _insert_link(conn, 1, 2, "answers", "Confirmed")
    _insert_link(conn, 1, 4, "answers", "Confirmed")

    assert SqliteLinkContext(conn).neighbors_of(1) == [2, 3, 4]


def test_the_item_itself_is_never_a_neighbor(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 3)
    _insert_link(conn, 1, 3, "supports", "Confirmed")
    lookup = SqliteLinkContext(conn)

    assert lookup.neighbors_of(1) == [3]
    assert lookup.neighbors_of(3) == [1]
    assert 1 not in lookup.neighbors_of(1)
    assert 3 not in lookup.neighbors_of(3)


def test_neighbors_stop_after_one_hop(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 3)
    _insert_link(conn, 1, 2, "supports", "Confirmed")
    _insert_link(conn, 2, 3, "supports", "Confirmed")

    assert SqliteLinkContext(conn).neighbors_of(1) == [2]


def test_an_unknown_item_has_no_neighbors(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 2)

    assert SqliteLinkContext(conn).neighbors_of(999) == []


def test_read_failure_raises_relate_021() -> None:
    lookup = SqliteLinkContext(BrokenConnection())

    with pytest.raises(GraphReadFailed) as exc:
        lookup.neighbors_of(1)

    assert exc.value.code == "RELATE-021"
    assert exc.value.context["item_id"] == 1

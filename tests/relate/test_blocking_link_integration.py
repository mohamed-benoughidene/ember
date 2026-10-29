"""Integration tests for `SqliteLinkContext.supersedes_blocking_link` on SQLite.

The method exists so a `RELATE-028` rejection can name the link that blocked
the proposal. It walks the same live Confirmed supersedes edges the cycle
check walks (reversed and non-Confirmed rows never count), and a read failure
surfaces as RELATE-021 like `neighbors_of`.
"""

from __future__ import annotations

import sqlite3

import pytest

from ember.adapters.sqlite import SqliteLinkContext, open_database
from ember.relate.errors import GraphReadFailed
from tests.fakes import insert_item, insert_link, insert_source


class BrokenConnection:
    """A connection whose every statement fails, to drive the RELATE-021 path."""

    def execute(self, *args: object, **kwargs: object) -> object:
        raise sqlite3.OperationalError("boom")


def _seed_items(conn: sqlite3.Connection, count: int) -> None:
    source_id = insert_source(conn)
    for item_id in range(1, count + 1):
        insert_item(conn, source_id=source_id, item_id=item_id)
    conn.commit()


def test_the_first_connecting_edge_wins_in_id_order(db_path) -> None:
    conn = open_database(db_path)
    try:
        _seed_items(conn, 4)
        # A diamond: both 2 -> 4 and 3 -> 4 reach the goal, so the lower edge
        # id must be the one reported.
        insert_link(conn, 1, 2, "supersedes")
        insert_link(conn, 1, 3, "supersedes")
        lower = insert_link(conn, 2, 4, "supersedes")
        insert_link(conn, 3, 4, "supersedes")
        conn.commit()

        blocker = SqliteLinkContext(conn).supersedes_blocking_link(4, 1)

        assert blocker is not None
        assert blocker.id == lower
        assert (blocker.source_item_id, blocker.target_item_id) == (2, 4)
    finally:
        conn.close()


def test_a_live_edge_blocking_the_direct_direction_is_found(db_path) -> None:
    conn = open_database(db_path)
    try:
        _seed_items(conn, 2)
        edge = insert_link(conn, 1, 2, "supersedes")
        conn.commit()

        blocker = SqliteLinkContext(conn).supersedes_blocking_link(1, 2)

        assert blocker is not None
        assert blocker.id == edge
    finally:
        conn.close()


def test_reversed_and_rejected_rows_never_block(db_path) -> None:
    conn = open_database(db_path)
    try:
        _seed_items(conn, 2)
        insert_link(conn, 1, 2, "supersedes")
        conn.execute("UPDATE links SET reversed_at = '2026-01-01T00:00:00+00:00'")
        insert_link(conn, 2, 1, "supersedes", status="Rejected")
        conn.commit()

        assert SqliteLinkContext(conn).supersedes_blocking_link(1, 2) is None
    finally:
        conn.close()


def test_no_path_returns_none(db_path) -> None:
    conn = open_database(db_path)
    try:
        _seed_items(conn, 3)
        insert_link(conn, 1, 2, "depends_on", status="Confirmed")
        conn.commit()

        assert SqliteLinkContext(conn).supersedes_blocking_link(1, 3) is None
    finally:
        conn.close()


def test_read_failure_raises_relate_021() -> None:
    context = SqliteLinkContext(BrokenConnection())

    with pytest.raises(GraphReadFailed) as exc:
        context.supersedes_blocking_link(1, 2)

    assert exc.value.code == "RELATE-021"
    assert exc.value.context["source_id"] == 1
    assert exc.value.context["target_id"] == 2

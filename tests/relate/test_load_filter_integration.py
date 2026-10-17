"""Integration tests for relate phase 1 (load + filter) on a real SQLite DB."""

from __future__ import annotations

import sqlite3

import pytest

from ember.adapters.sqlite import SqliteLinkContext, open_database
from ember.relate.errors import ItemIdNotFound
from ember.relate.load_filter import load_and_filter
from tests.fakes import FIXED_TIME, insert_item, insert_source


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


def test_item_one_drops_two_full_questions_and_keeps_three(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
    insert_item(conn, source_id=source_id, item_id=2, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=3, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=4, item_type="Decision")
    insert_item(conn, source_id=source_id, item_id=5, item_type="Assumption")
    insert_item(conn, source_id=source_id, item_id=6, item_type="Finding")
    _insert_link(conn, 1, 2, "answers", "Confirmed")
    _insert_link(conn, 1, 3, "answers", "Rejected")
    conn.commit()

    result = load_and_filter(SqliteLinkContext(conn), item_id=1, db_path=db_path)

    assert result is not None
    assert [item.id for item in result.universe.items] == [4, 5, 6]


def test_type_filter_drops_incompatible_types(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=2, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=3, item_type="Decision")
    insert_item(conn, source_id=source_id, item_id=4, item_type="Assumption")
    insert_item(conn, source_id=source_id, item_id=5, item_type="Finding")
    conn.commit()

    result = load_and_filter(SqliteLinkContext(conn), item_id=1, db_path=db_path)

    assert result is not None
    assert [item.id for item in result.universe.items] == [2]


def test_latest_returns_newest_active_with_no_outgoing_link(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)
    insert_item(conn, source_id=source_id, item_id=2)
    insert_item(conn, source_id=source_id, item_id=3)
    lookup = SqliteLinkContext(conn)

    assert lookup.find_latest_unlinked_active().id == 3

    _insert_link(conn, 3, 1, "supports", "Confirmed")
    assert lookup.find_latest_unlinked_active().id == 2

    _insert_link(conn, 2, 1, "supports", "Confirmed")
    assert lookup.find_latest_unlinked_active().id == 1

    _insert_link(conn, 1, 2, "supports", "Confirmed")
    assert lookup.find_latest_unlinked_active() is None


def test_missing_item_reports_id_and_db_path(db_path) -> None:
    conn = open_database(db_path)
    insert_source(conn)
    conn.commit()

    with pytest.raises(ItemIdNotFound) as excinfo:
        load_and_filter(SqliteLinkContext(conn), item_id=999, db_path=db_path)

    assert excinfo.value.code == "RELATE-001"
    assert "999" in str(excinfo.value)
    assert db_path in excinfo.value.message


def test_existing_link_of_any_status_is_dropped(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=2, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=3, item_type="Question")
    _insert_link(conn, 1, 2, "supersedes", "Confirmed")
    _insert_link(conn, 1, 3, "supersedes", "Rejected")
    conn.commit()

    result = load_and_filter(SqliteLinkContext(conn), item_id=1, db_path=db_path)

    assert result is not None
    assert result.universe.items == []

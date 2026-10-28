"""Integration: `history` over a ledger written by the real engine writers."""

from __future__ import annotations

import json

from ember.adapters.sqlite import (
    SqliteLinkStore,
    SqliteMaintainStore,
    SqliteQueryContext,
    open_database,
    open_query_database,
)
from ember.maintain.rows import StatusChange
from ember.query.run_query import run_history
from ember.relate.rows import ChangeLogEntry, Link
from tests.fakes import FIXED_TIME, insert_item, insert_source
from tests.query.fakes import make_v10


def _seed_ledger(db_path: str) -> int:
    """Write one confirmed link and one machine close through the real writers.

    Returns the link id. Item 2 supersedes item 1 (Decision -> Decision is
    compat-legal), so the ledger holds Engine B's `link_confirmed` row and
    Engine C's `status` row.
    """
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="Old decision")
        insert_item(conn, source_id=source_id, item_id=2, statement="New decision")
        link_store = SqliteLinkStore(conn)
        link_id = link_store.insert_link_with_log(
            _link(2, 1), _link_row(2, "supersedes")
        )
        SqliteMaintainStore(conn).apply_status_changes(
            [
                StatusChange(
                    item_id=1,
                    old_status="Active",
                    new_status="Closed",
                    close_reason="superseded",
                    old_close_reason=None,
                    trigger_cause="supersedes_confirmed",
                    link_id=link_id,
                )
            ]
        )
        conn.commit()
    finally:
        conn.close()
    return link_id


def _link(source: int, target: int) -> Link:
    return Link(
        id=None,
        source_item_id=source,
        target_item_id=target,
        link_type="supersedes",
        status="Confirmed",
        created_at=FIXED_TIME,
    )


def _link_row(item_id: int, link_type: str) -> ChangeLogEntry:
    return ChangeLogEntry(
        id=None,
        item_id=item_id,
        link_id=None,
        field_changed="link_confirmed",
        old_value=None,
        new_value=link_type,
        timestamp=FIXED_TIME,
        trigger_cause="user_confirmed",
    )


def test_item_history_shows_the_link_and_status_events(db_path) -> None:
    link_id = _seed_ledger(db_path)
    conn = open_query_database(db_path)
    try:
        document = json.loads(run_history(SqliteQueryContext(conn), 1))
    finally:
        conn.close()

    assert document["mode"] == "history"
    assert document["item_id"] == 1
    assert [event["kind"] for event in document["events"]] == [
        "link_confirmed",
        "status_changed",
    ]
    assert document["events"][0]["link_id"] == link_id
    assert document["events"][1]["close_reason"] == "superseded"


def test_global_history_returns_every_row(db_path) -> None:
    _seed_ledger(db_path)
    conn = open_query_database(db_path)
    try:
        item_scoped = json.loads(run_history(SqliteQueryContext(conn), 1))
        global_view = json.loads(run_history(SqliteQueryContext(conn), None))
    finally:
        conn.close()

    assert global_view["item_id"] is None
    assert global_view["count"] >= item_scoped["count"]


def test_history_for_an_item_with_no_events_is_not_an_error(db_path) -> None:
    _seed_ledger(db_path)
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn, "another body")
        insert_item(conn, source_id=source_id, item_id=3, statement="Quiet item")
        conn.commit()
    finally:
        conn.close()

    conn = open_query_database(db_path)
    try:
        document = json.loads(run_history(SqliteQueryContext(conn), 3))
    finally:
        conn.close()

    assert document["count"] == 0

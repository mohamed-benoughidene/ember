"""Integration: a real v10 DB, `_load` + `derive_status_changes` end to end."""

from __future__ import annotations

from pathlib import Path

from ember.adapters.sqlite import SqliteMaintainContext, open_maintain_database
from ember.maintain.derive import derive_status_changes
from ember.maintain.rows import StatusChange
from ember.maintain.run_maintain import _load
from tests.fakes import insert_item, insert_link, insert_link_reversed, insert_source


def _open_v10(db_path: str):
    Path(db_path).touch()
    return open_maintain_database(db_path)


def test_seeded_sweep_returns_the_exact_change_list(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
    insert_item(conn, source_id=source_id, item_id=2, item_type="Decision")
    insert_item(conn, source_id=source_id, item_id=3, item_type="Question")
    insert_item(conn, source_id=source_id, item_id=4, item_type="Finding")
    supersedes = insert_link(conn, 2, 1, "supersedes")
    contradicts = insert_link(conn, 4, 1, "contradicts")
    answers = insert_link(conn, 1, 3, "answers")
    depends_on = insert_link(conn, 2, 1, "depends_on")
    conn.commit()

    try:
        snapshot = _load(SqliteMaintainContext(conn))
    finally:
        conn.close()

    changes = derive_status_changes(snapshot)
    assert changes == [
        StatusChange(
            item_id=1,
            old_status="Active",
            new_status="Closed",
            close_reason="superseded",
            old_close_reason=None,
            trigger_cause="supersedes_confirmed",
            link_id=supersedes,
        ),
        StatusChange(
            item_id=2,
            old_status="Active",
            new_status="Challenged",
            close_reason=None,
            old_close_reason=None,
            trigger_cause="dependency_closed",
            link_id=depends_on,
        ),
        StatusChange(
            item_id=3,
            old_status="Active",
            new_status="Closed",
            close_reason="answered",
            old_close_reason=None,
            trigger_cause="answers_confirmed",
            link_id=answers,
        ),
    ]
    # `contradicts` loses the precedence tie for item 1 (Closed > Challenged):
    # item 1 gets its single change from the `supersedes` link, not `contradicts`.
    item_1_changes = [change for change in changes if change.item_id == 1]
    assert len(item_1_changes) == 1
    only_item_1_change = item_1_changes[0]
    assert only_item_1_change.new_status == "Closed"
    assert only_item_1_change.close_reason == "superseded"
    assert only_item_1_change.link_id == supersedes
    assert only_item_1_change.link_id != contradicts


def test_empty_database_yields_no_changes(db_path) -> None:
    conn = _open_v10(db_path)
    try:
        snapshot = _load(SqliteMaintainContext(conn))
    finally:
        conn.close()

    assert snapshot.items == []
    assert snapshot.links == []
    assert snapshot.reversed_link_ids == set()
    assert derive_status_changes(snapshot) == []


def test_reversed_supersedes_is_not_a_live_close(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
    insert_item(conn, source_id=source_id, item_id=2, item_type="Decision")
    link_id = insert_link(conn, 2, 1, "supersedes")
    insert_link_reversed(conn, link_id, 1)
    conn.commit()

    try:
        snapshot = _load(SqliteMaintainContext(conn))
    finally:
        conn.close()

    assert snapshot.reversed_link_ids == {link_id}
    assert derive_status_changes(snapshot) == []

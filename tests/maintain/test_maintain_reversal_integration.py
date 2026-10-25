"""Integration: `SqliteMaintainStore.apply_reversal`, the one-transaction restore.

These tests need foreign keys ON (the atomicity test depends on the
`change_log.link_id` FK from migration 008), so every case opens the DB through
`open_maintain_database`, never a bare `sqlite3.connect` (Constitution T10).

The `StatusChange` and the `ChangeLogEntry` marker are built here directly, so
these tests depend on neither the validator nor `human_actions.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ember.adapters.sqlite import SqliteMaintainStore, open_maintain_database
from ember.maintain.errors import (
    ChangeLogWriteFailed as MaintainChangeLogWriteFailed,
)
from ember.maintain.rows import StatusChange
from ember.relate.rows import ChangeLogEntry
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source


def _open_v10(db_path: str):
    Path(db_path).touch()
    return open_maintain_database(db_path)


def test_apply_reversal_restores_item_and_marks_link(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Closed",
                close_reason="superseded")
    insert_item(conn, source_id=source_id, item_id=2, status="Active")
    link_id = insert_link(conn, 2, 1, "supersedes")
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    change = StatusChange(
        item_id=1,
        old_status="Closed",
        new_status="Active",
        close_reason=None,
        old_close_reason="superseded",
        trigger_cause="reversal",
        link_id=link_id,
    )
    marker = ChangeLogEntry(
        item_id=1,
        link_id=link_id,
        field_changed="link_reversed",
        old_value="Confirmed",
        new_value="Reversed",
        timestamp="",
        trigger_cause="reversal",
    )

    result = store.apply_reversal(change, marker)

    assert result == 1
    item = conn.execute(
        "SELECT status, close_reason FROM items WHERE id = 1"
    ).fetchone()
    assert item["status"] == "Active"
    assert item["close_reason"] is None

    log = conn.execute("SELECT * FROM change_log ORDER BY id").fetchall()
    assert len(log) == 2
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 2

    status_row = log[0]
    assert status_row["item_id"] == 1
    assert status_row["link_id"] == link_id
    assert status_row["field_changed"] == "status"
    assert status_row["old_value"] == "Closed:superseded"
    assert status_row["new_value"] == "Active"
    assert status_row["trigger_cause"] == "reversal"
    assert status_row["timestamp"] == FIXED_TIME

    marker_row = log[1]
    assert marker_row["item_id"] == 1
    assert marker_row["link_id"] == link_id
    assert marker_row["field_changed"] == "link_reversed"
    assert marker_row["old_value"] == "Confirmed"
    assert marker_row["new_value"] == "Reversed"
    assert marker_row["trigger_cause"] == "reversal"
    assert marker_row["timestamp"] == FIXED_TIME

    link = conn.execute(
        "SELECT status FROM links WHERE id = ?", (link_id,)
    ).fetchone()
    assert link["status"] == "Confirmed"
    conn.close()


def test_apply_reversal_rolls_back_on_marker_fk_violation(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    change = StatusChange(
        item_id=1,
        old_status="Active",
        new_status="Challenged",
        close_reason=None,
        old_close_reason=None,
        trigger_cause="reversal",
        link_id=None,
    )
    marker = ChangeLogEntry(
        item_id=1,
        link_id=99999,
        field_changed="link_reversed",
        old_value="Confirmed",
        new_value="Reversed",
        timestamp="",
        trigger_cause="reversal",
    )

    with pytest.raises(MaintainChangeLogWriteFailed) as exc:
        store.apply_reversal(change, marker)

    assert exc.value.code == "MAINTAIN-012"
    assert (
        conn.execute("SELECT status FROM items WHERE id = 1").fetchone()[0]
        == "Active"
    )
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
    conn.close()

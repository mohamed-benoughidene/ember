"""Fix G1: a close that re-arms a shielded dependent must be undoable.

Before the fix, `ember undo` refused with MAINTAIN-027 on the sweep's
`sweep_rearm` ledger row (`field_changed='status_origin'`, written by
`apply_status_changes` with the close's group id): "unknown row shape in
grouped ledger". All undo stayed blocked until another human action
landed. The fix (founder decision G1-B): the re-arm row is a known
passenger of a close group — undo inverts it (`derived` -> `manual`
restores the manual shield), redo re-arms again, and undo of that redo
restores the shield once more. A group that carries ONLY `sweep_rearm`
rows stays corrupt (MAINTAIN-027, fail closed).

All tests run on throwaway temp databases built by the repo's own
helpers — never the maintainer's files.
"""

from __future__ import annotations

import importlib.resources
import sqlite3

import pytest
from click.testing import CliRunner

from ember.cli import main
from ember.maintain.errors import GroupRecordInvalid
from ember.maintain.undo import derive_undo
from ember.maintain.rows import LedgerGroup, UndoSnapshot
from tests.fakes import FIXED_TIME, insert_item, insert_link_with_confirmation, insert_source

_MIGRATIONS = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
    "006_create_links.sql",
    "007_create_item_embeddings.sql",
    "008_add_change_log_link_fk.sql",
    "009_drop_source_id_not_null_and_add_item_id.sql",
    "010_add_item_close_reason.sql",
    "011_add_links_reversed_at_and_enforcement_triggers.sql",
    "012_add_items_metadata.sql",
    "013_add_change_log_group_id.sql",
)


def _build_scenario(db_path: str) -> None:
    """The reproduction: B cleared by hand, depends_on B->A confirmed
    afterwards, everything else untouched."""
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (13)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    src = insert_source(conn)
    insert_item(conn, source_id=src, item_id=1, item_type="Finding", statement="A")
    # B: cleared BY HAND (Active + status_origin='manual') and its ledger clear.
    insert_item(
        conn, source_id=src, item_id=2, item_type="Assumption", statement="B",
        status="Active", status_origin="manual",
    )
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause, group_id)"
        " VALUES (2, NULL, 'status_origin', 'derived', 'manual', ?,"
        " 'user_set_status', NULL)",
        (FIXED_TIME,),
    )
    # The depends_on link from B(2) to A(1), confirmed AFTER the clear.
    insert_link_with_confirmation(
        conn, 2, 1, "depends_on", created_at="2026-02-01T00:00:00+00:00"
    )
    conn.commit()
    conn.close()


def _row_state(db_path: str, item_id: int) -> tuple[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT status, status_origin FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()


def _run(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(main, list(args))
    return result.exit_code, result.output


def _groups(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(
            conn.execute("SELECT MAX(group_id) FROM change_log").fetchone()[0]
        )
    finally:
        conn.close()


def test_undo_of_close_that_rearms_shielded_dependent(db_path, tmp_path) -> None:
    db = str(db_path)
    _build_scenario(db)
    close_ec, close_out = _run("close-item", "--item", "1", "--reason", "invalidated", "--db", db)
    assert close_ec == 0, close_out
    assert _row_state(db, 2) == ("Challenged", "derived"), "the close re-armed B"

    undo_ec, undo_out = _run("undo", "--db", db)
    assert undo_ec == 0, f"undo must succeed now: {undo_out}"
    assert _row_state(db, 1) == ("Active", "derived"), "A is back"
    # The dependent's manual shield is RESTORED: the inverse of the
    # sweep_rearm row (derived -> manual) rides with the inverse of the
    # dependency close (Challenged -> Active).
    assert _row_state(db, 2) == ("Active", "manual")


def test_redo_rearms_again_and_undo_of_redo_restores(db_path) -> None:
    db = str(db_path)
    _build_scenario(db)
    _run("close-item", "--item", "1", "--reason", "invalidated", "--db", db)
    undo_ec, undo_out = _run("undo", "--db", db)
    assert undo_ec == 0, undo_out
    groups_after_undo = _groups(db)

    redo_ec, redo_out = _run("redo", "--db", db)
    assert redo_ec == 0, f"redo must succeed: {redo_out}"
    assert _row_state(db, 1) == ("Closed", "derived"), "the redo re-applies the close"
    status, origin = _row_state(db, 2)
    assert status == "Challenged" and origin == "derived", "the redo re-arms B"
    assert _groups(db) > groups_after_undo

    # Undo of the redo: the shield comes back once more.
    undo2_ec, undo2_out = _run("undo", "--db", db)
    assert undo2_ec == 0, f"undo of the redo must succeed: {undo2_out}"
    assert _row_state(db, 2) == ("Active", "manual"), "the shield is restored again"


def test_group_with_only_sweep_rearm_rows_stays_corrupt() -> None:
    """A sweep_rearm row never travels alone: a group made only of them
    is a corrupt ledger and stays MAINTAIN-027 (fail closed)."""
    from ember.maintain.rows import ChangeLogEntry

    def rearm_row(item_id: int) -> ChangeLogEntry:
        return ChangeLogEntry(
            item_id=item_id,
            link_id=None,
            field_changed="status_origin",
            old_value="manual",
            new_value="derived",
            timestamp=FIXED_TIME,
            trigger_cause="sweep_rearm",
        )

    snapshot = UndoSnapshot(
        groups=[LedgerGroup(group_id=4, rows=[rearm_row(2)])],
        items=[],
        links=[],
        ungrouped_rows_exist=False,
    )
    with pytest.raises(GroupRecordInvalid):
        derive_undo(snapshot)

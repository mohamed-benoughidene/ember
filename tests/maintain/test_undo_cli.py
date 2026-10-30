"""CLI tests for `ember undo` and `ember redo` (undo step 04, step file §2).

Every case drives the real Click commands against a freshly created SQLite
temp DB (`open_maintain_database`, foreign keys ON) and seeds the undoable
action through the real commands, so the pinned report lines, the exit codes
and the byte-identity of `--dry-run` (file hash) are all proven end to end.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from tests.fakes import insert_item, insert_link, insert_link_with_confirmation, insert_source


def _open(db_path: str) -> sqlite3.Connection:
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _invoke(args: list[str]) -> Any:
    return CliRunner().invoke(main, args)


def _error_text(result: Any) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def _sha(db_path: str) -> str:
    return hashlib.sha256(Path(db_path).read_bytes()).hexdigest()


def _count(db_path: str, sql: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(sql).fetchone()[0])
    finally:
        conn.close()


def _item_status(db_path: str, item_id: int) -> tuple[str, str | None]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT status, close_reason FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()
    return row[0], row[1]


def _seed_plain(db_path: str) -> None:
    """One Active Decision on an empty database."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        conn.commit()
    finally:
        conn.close()


def _seed_closed(db_path: str) -> str:
    """Seed item 1, then close it by hand (the ledger's undo group 1)."""
    _seed_plain(db_path)
    result = _invoke(
        ["close-item", "--item", "1", "--reason", "expired", "--db", db_path]
    )
    assert result.exit_code == 0, _error_text(result)
    return db_path


# ---------------------------------------------------------------------------
# S1 sample 1: undo --dry-run -- DB hash unchanged.
# ---------------------------------------------------------------------------


def test_undo_dry_run_exit_0_line_pinned_and_db_byte_identical(db_path) -> None:
    db = _seed_closed(db_path)
    before = _sha(db)

    result = _invoke(["undo", "--dry-run", "--db", db])

    assert result.exit_code == 0
    assert result.output == (
        "undo group 1 (close-item, item 1):"
        " item 1: Closed -> Active (dry-run)\n"
    )
    assert _sha(db) == before
    assert _count(db, "SELECT COUNT(*) FROM change_log") == 1
    assert _item_status(db, 1) == ("Closed", "expired")


def test_redo_dry_run_exit_0_line_pinned_and_db_byte_identical(db_path) -> None:
    db = _seed_closed(db_path)
    assert _invoke(["undo", "--db", db]).exit_code == 0
    before = _sha(db)

    result = _invoke(["redo", "--dry-run", "--db", db])

    assert result.exit_code == 0
    assert result.output == (
        "redo group 2 (close-item, item 1):"
        " item 1: Active -> Closed (expired) (dry-run)\n"
    )
    assert _sha(db) == before
    assert _item_status(db, 1)[0] == "Active"


# ---------------------------------------------------------------------------
# S1 samples 2 and 3: undo then redo, pinned lines and real state.
# ---------------------------------------------------------------------------


def test_undo_success_exits_0_pinned_line_and_restores_state(db_path) -> None:
    db = _seed_closed(db_path)

    result = _invoke(["undo", "--db", db])

    assert result.exit_code == 0
    assert result.output == (
        "undone group 1 as group 2 (close-item, item 1):"
        " item 1: Closed -> Active\n"
    )
    assert _item_status(db, 1) == ("Active", None)
    # Ledger only grows: the close row + the inverse row + the marker.
    assert _count(db, "SELECT COUNT(*) FROM change_log") == 3


def test_redo_success_exits_0_pinned_line_and_restores_state(db_path) -> None:
    db = _seed_closed(db_path)
    assert _invoke(["undo", "--db", db]).exit_code == 0

    result = _invoke(["redo", "--db", db])

    assert result.exit_code == 0
    assert result.output == (
        "redone group 2 as group 3 (close-item, item 1):"
        " item 1: Active -> Closed (expired)\n"
    )
    assert _item_status(db, 1) == ("Closed", "expired")
    assert _count(db, "SELECT COUNT(*) FROM change_log") == 5


def test_undo_report_names_every_changed_item_in_one_line(db_path) -> None:
    """A close with a dependent: the report counts BOTH changed items."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        insert_item(conn, source_id=source_id, item_id=2)
        insert_link(conn, 2, 1, "depends_on")
        conn.commit()
    finally:
        conn.close()
    result = _invoke(
        ["close-item", "--item", "1", "--reason", "invalidated", "--db", db_path]
    )
    assert result.exit_code == 0, _error_text(result)

    result = _invoke(["undo", "--db", db_path])

    assert result.exit_code == 0
    assert result.output == (
        "undone group 1 as group 2 (close-item, item 1):"
        " item 1: Closed -> Active; item 2: Challenged -> Active\n"
    )
    assert _item_status(db_path, 1) == ("Active", None)
    assert _item_status(db_path, 2) == ("Active", None)


def test_undo_a_removed_link_reports_the_link_segment(db_path) -> None:
    """The binding step-03 deviation U3-3, through the CLI: the undo
    snapshot must see a REJECTED link (any status) or the refusal rule
    cannot verify and would refuse the legitimate undo."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        insert_item(conn, source_id=source_id, item_id=2)
        insert_link_with_confirmation(conn, 1, 2, "supersedes")
        conn.commit()
    finally:
        conn.close()
    result = _invoke(["remove-link", "--link", "1", "--db", db_path])
    assert result.exit_code == 0, _error_text(result)

    result = _invoke(["undo", "--db", db_path])

    assert result.exit_code == 0
    assert result.output == (
        "undone group 1 as group 2 (remove-link, link 1):"
        " link 1: Rejected -> Confirmed\n"
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT status FROM links WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "Confirmed"


# ---------------------------------------------------------------------------
# S1 sample 4 plus the note variants: MAINTAIN-023 and MAINTAIN-024.
# ---------------------------------------------------------------------------


def test_undo_empty_db_exits_1_maintain_023(db_path) -> None:
    conn = _open(db_path)
    conn.close()

    result = _invoke(["undo", "--db", db_path])

    assert result.exit_code == 1
    assert "MAINTAIN-023" in _error_text(result)
    assert "nothing to undo" in _error_text(result)


def test_undo_with_only_ungrouped_rows_says_older_changes_exist(db_path) -> None:
    """Story 123: pre-013 rows exist but are invisible to undo - the
    refusal message must say so."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        conn.execute(
            "INSERT INTO change_log (item_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause)"
            " VALUES (1, 'status', 'Active', 'Challenged',"
            " '2026-01-01T00:00:00+00:00', 'sweep')"
        )
        conn.commit()
    finally:
        conn.close()

    result = _invoke(["undo", "--db", db_path])

    assert result.exit_code == 1
    assert "MAINTAIN-023" in _error_text(result)
    assert "older ledger rows carry no undo group" in _error_text(result)


def test_redo_after_newer_change_exits_1_maintain_024(db_path) -> None:
    db = _seed_closed(db_path)
    assert _invoke(["undo", "--db", db]).exit_code == 0
    result = _invoke(
        ["edit-item", "--item", "1", "--field", "rationale",
         "--value", "new why", "--db", db]
    )
    assert result.exit_code == 0, _error_text(result)

    result = _invoke(["redo", "--db", db])

    assert result.exit_code == 1
    assert "MAINTAIN-024" in _error_text(result)
    assert "nothing to redo: a newer change cleared it" in _error_text(result)


def test_redo_on_fresh_db_exits_1_maintain_024(db_path) -> None:
    _seed_closed(db_path)  # group 1 stands, nothing undone

    result = _invoke(["redo", "--db", db_path])

    assert result.exit_code == 1
    assert "MAINTAIN-024" in _error_text(result)


# ---------------------------------------------------------------------------
# The refusal rule through the CLI: a sweep changed a touched item.
# ---------------------------------------------------------------------------


def test_undo_after_sweep_changed_touched_item_exits_1_maintain_025(
    db_path,
) -> None:
    """`set-status` to Active shields item 5 (group 1); a later contradicts
    link (evidence NEWER than the clear) lets the sweep un-shield and
    challenge item 5 again; the undo must refuse and write nothing."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Finding")
        insert_item(
            conn,
            source_id=source_id,
            item_id=5,
            item_type="Decision",
            status="Challenged",
        )
        conn.commit()
    finally:
        conn.close()
    result = _invoke(["set-status", "--item", "5", "--to", "Active", "--db", db_path])
    assert result.exit_code == 0, _error_text(result)
    # Relate-shaped confirmation with evidence AFTER the shield clear.
    conn = sqlite3.connect(db_path)
    try:
        insert_link_with_confirmation(
            conn, 1, 5, "contradicts", created_at="2999-01-01T00:00:00+00:00"
        )
        conn.commit()
    finally:
        conn.close()
    result = _invoke(["maintain", "--db", db_path])
    assert result.exit_code == 0, _error_text(result)
    assert _item_status(db_path, 5) == ("Challenged", None)
    before = _sha(db_path)

    result = _invoke(["undo", "--db", db_path])

    assert result.exit_code == 1
    assert "MAINTAIN-025" in _error_text(result)
    assert "UndoRefused" in _error_text(result)
    assert _sha(db_path) == before, "a refusal must write zero rows"
    assert _item_status(db_path, 5) == ("Challenged", None)


# ---------------------------------------------------------------------------
# Unknown flags: Click usage errors exit 2.
# ---------------------------------------------------------------------------


def test_undo_unknown_flag_exits_2(db_path) -> None:
    conn = _open(db_path)
    conn.close()

    result = _invoke(["undo", "--bogus", "--db", db_path])

    assert result.exit_code == 2


def test_redo_unknown_flag_exits_2(db_path) -> None:
    conn = _open(db_path)
    conn.close()

    result = _invoke(["redo", "--bogus", "--db", db_path])

    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Missing database: the unchanged boot code (MAINTAIN-007) at the edge.
# ---------------------------------------------------------------------------


def test_undo_missing_db_exits_1_maintain_007(tmp_path) -> None:
    result = _invoke(["undo", "--db", str(tmp_path / "nope.db")])

    assert result.exit_code == 1
    assert "MAINTAIN-007" in _error_text(result)

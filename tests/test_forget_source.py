"""`ember forget-source` command tests (Batch 6 chunk 11, D-07 / D-26).

The forget rule: a raw note that produced NO items can be forgotten
permanently — the source row and its raw AI answers are deleted and ONE
textless ledger line names the source (migration 014's `source_id`,
`group_id` NULL so undo never sees it). A note that still has items is
refused with a dedicated new code (next free CAPTURE number, CAPTURE-023).
A missing id is delete-nothing = success (I8). `ember history` classifies
the new `(field, cause)` pair as a NEW kind, carrying `source_id` and no
note text.
"""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner

from ember.adapters.sqlite import SqliteAiResponseStore, open_database
from ember.cli import main
from tests.fakes import insert_item, insert_source

NOTE_TEXT = "We decided to use SQLite and only SQLite."


def _raw(db_path: str) -> sqlite3.Connection:
    """A bare sqlite3 connection for reading the file back after a run."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_note_with_items(db_path: str) -> int:
    """One source with a confirmed item and a raw AI answer; returns its id."""
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn, NOTE_TEXT)
        insert_item(conn, source_id=source_id, item_id=1)
        SqliteAiResponseStore(conn).save(source_id=source_id, raw_response="{}")
        conn.commit()
    finally:
        conn.close()
    return source_id


def _seed_note_without_items(db_path: str) -> int:
    """One source with a raw AI answer and NO items; returns its id."""
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn, NOTE_TEXT)
        SqliteAiResponseStore(conn).save(source_id=source_id, raw_response="{}")
        conn.commit()
    finally:
        conn.close()
    return source_id


def test_forget_source_on_a_note_with_items_is_refused(db_path) -> None:
    """(a) A note that still has items is refused, one house line, exit 1,
    and NOTHING is written — the source, its AI answers and the ledger stay
    byte-for-byte in place."""
    source_id = _seed_note_with_items(db_path)

    result = CliRunner().invoke(
        main, ["forget-source", "--source", str(source_id), "--db", db_path]
    )

    assert result.exit_code == 1
    assert "CAPTURE-023" in result.output
    conn = _raw(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_responses").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
    finally:
        conn.close()


def test_forget_source_on_a_note_without_items(db_path) -> None:
    """(b) A note with NO items is forgotten: the source row is gone, its
    `ai_responses` rows are gone, and the ledger gained exactly ONE row —
    it names the source id, carries a timestamp, has `group_id` NULL
    (invisible to undo, migration 013's own rule), the NEW field/cause
    pair, and NO text (old/new values stay NULL)."""
    source_id = _seed_note_without_items(db_path)

    result = CliRunner().invoke(
        main, ["forget-source", "--source", str(source_id), "--db", db_path]
    )

    assert result.exit_code == 0
    conn = _raw(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM ai_responses WHERE source_id = ?",
                (source_id,),
            ).fetchone()[0]
            == 0
        )
        rows = conn.execute(
            "SELECT id, item_id, link_id, field_changed, old_value, new_value,"
            " timestamp, trigger_cause, group_id, source_id"
            " FROM change_log ORDER BY id"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["source_id"] == source_id
        assert row["timestamp"] is not None and row["timestamp"] != ""
        assert row["group_id"] is None
        assert row["item_id"] is None and row["link_id"] is None
        assert row["field_changed"] == "source_forgotten"
        assert row["trigger_cause"] == "user_forget_source"
        assert row["old_value"] is None and row["new_value"] is None
    finally:
        conn.close()


def test_forget_source_on_a_missing_id_succeeds_with_nothing_written(
    db_path,
) -> None:
    """(c) I8: deleting a missing thing is success — exit 0, no ledger row."""
    _seed_note_without_items(db_path)  # keeps other data intact

    result = CliRunner().invoke(
        main, ["forget-source", "--source", "999", "--db", db_path]
    )

    assert result.exit_code == 0
    conn = _raw(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
    finally:
        conn.close()


def test_history_classifies_the_forgotten_line(db_path) -> None:
    """(d) `ember history` classifies the new (field, cause) pair as the NEW
    `source_forgotten` kind, and the event carries `source_id` with NO note
    text anywhere in it."""
    source_id = _seed_note_without_items(db_path)
    runner = CliRunner()

    forgotten = runner.invoke(
        main, ["forget-source", "--source", str(source_id), "--db", db_path]
    )
    assert forgotten.exit_code == 0

    listing = runner.invoke(main, ["history", "--db", db_path])
    assert listing.exit_code == 0
    document = json.loads(listing.output)
    events = [e for e in document["events"] if e["kind"] == "source_forgotten"]
    assert len(events) == 1
    event = events[0]
    assert event["field_changed"] == "source_forgotten"
    assert event["cause"] == "user_forget_source"
    assert event["source_id"] == source_id
    assert event["old_value"] is None and event["new_value"] is None
    # No note text anywhere in the rendered event.
    assert NOTE_TEXT not in json.dumps(event)

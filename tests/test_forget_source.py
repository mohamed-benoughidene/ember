"""`ember forget-source` command tests (Batch 6 chunk 11, D-07 / D-26).

The forget rule: a raw note that produced NO items can be forgotten
permanently — the source row and its raw AI answers are deleted and ONE
textless ledger line names the source (migration 014's `source_id`,
`group_id` NULL so undo never sees it). A note that still has items is
refused with a dedicated new code (next free CAPTURE number, CAPTURE-023).
A missing id is delete-nothing = success (I8). `ember history` classifies
the new `(field, cause)` pair as a NEW kind, carrying `source_id` and no
note text.

Chunk 12 adds the Cleanup list's READ (D-09): `ember
list-sources-without-items` prints one JSON document (reads always do)
listing every source with ZERO items — `id`, `created_at`, the first
words of its text — an empty list instead of null (I4), and a read-only
run (byte-identical file).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.adapters.sqlite import SqliteAiResponseStore, open_database
from ember.cli import main
from tests.fakes import FIXED_TIME, insert_item, insert_source

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


def _seed_two_notes_only_one_has_items(db_path: str) -> tuple[int, int]:
    """Source 1 keeps one confirmed item; source 2 has no items at all.

    The two texts differ because a source's `content_hash` is UNIQUE.
    Returns (with_items_id, without_items_id).
    """
    conn = open_database(db_path)
    try:
        with_items = insert_source(conn, NOTE_TEXT)
        without_items = insert_source(
            conn,
            "We decided to use Postgres instead of SQLite for the second note body.",
        )
        insert_item(conn, source_id=with_items, item_id=1)
        conn.commit()
    finally:
        conn.close()
    return with_items, without_items


def test_list_sources_without_items_lists_only_itemless_notes(db_path) -> None:
    """(e) The Cleanup list's read (Chunk 12, D-09): `ember
    list-sources-without-items` prints ONE JSON document (reads always do)
    whose `sources` rows carry `id`, `created_at` and the FIRST WORDS of
    the note text; the note that still has an item is NOT listed — listing
    it would only invite the CAPTURE-023 refusal; and the run is read-only,
    the file byte-identical after it."""
    with_items, without_items = _seed_two_notes_only_one_has_items(db_path)
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()

    result = CliRunner().invoke(
        main, ["list-sources-without-items", "--db", db_path]
    )

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert set(document) == {"count", "sources"}
    rows = document["sources"]
    assert [row["id"] for row in rows] == [without_items]
    listed = rows[0]
    assert listed["created_at"] == FIXED_TIME
    assert listed["preview"] == "We decided to use Postgres instead of SQLite"
    # The tail words and the item-bearing note's text stay unread.
    assert "second note body" not in result.output
    assert NOTE_TEXT not in result.output
    assert document["count"] == 1
    # Read-only proof: the database file is byte-identical after the run.
    after = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    assert after == before


def test_list_sources_without_items_on_an_empty_base_is_an_empty_list(
    db_path,
) -> None:
    """(f) I4: an empty base prints an empty list, never null."""
    open_database(db_path).close()

    result = CliRunner().invoke(
        main, ["list-sources-without-items", "--db", db_path]
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"count": 0, "sources": []}

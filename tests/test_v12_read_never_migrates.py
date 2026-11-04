"""v12 read paths: `ember history`, `export` and `db-check` never migrate.

Undo step 01 §2: an untouched v12 file (scripts 001-012 applied, version
stamped 12, no group_id column) must stay at v12 — the query boot is
read-only and db-check never migrates. `history`, `export` and `db-check` succeed on
it (the db-check floors name what the walk reads; migration 015's tag column
is not among them, so a v12 file passes the check)
floor gap as drift on the untouched file — reading it, never migrating it.
"""

from __future__ import annotations

import importlib.resources
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.cli import main
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source

_MIGRATIONS_TO_12 = (
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
)


def _build_v12_db(db_path: str) -> None:
    """Build a real untouched v12 file with one source, 2 items, 1 link."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (12)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_12:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, statement="older")
    insert_item(conn, source_id=source_id, item_id=2, statement="newer")
    insert_link(conn, 2, 1, "supersedes")
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (1, NULL, 'created', NULL, 'Active', ?, 'user_confirmed')",
        (FIXED_TIME,),
    )
    conn.commit()
    conn.close()


def _version_and_hash(db_path: str) -> tuple[int, str]:
    import hashlib

    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]
    finally:
        conn.close()
    digest = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    return int(version), digest


def test_history_on_a_v12_file_succeeds_and_never_migrates(db_path) -> None:
    _build_v12_db(db_path)
    version_before, digest_before = _version_and_hash(db_path)

    result = CliRunner().invoke(main, ["history", "--db", db_path])

    assert result.exit_code == 0, result.output
    version_after, digest_after = _version_and_hash(db_path)
    assert version_before == 12
    assert version_after == 12
    # Never migrated, never backed up, never rewritten.
    assert digest_after == digest_before
    assert not Path(f"{db_path}.bak-v12").exists()


def test_export_on_a_v12_file_succeeds_and_never_migrates(db_path, tmp_path) -> None:
    _build_v12_db(db_path)
    version_before, digest_before = _version_and_hash(db_path)

    result = CliRunner().invoke(main, ["export", "--db", db_path])

    assert result.exit_code == 0, result.output
    assert "# schema version: 12" in result.output
    version_after, digest_after = _version_and_hash(db_path)
    assert version_before == 12
    assert version_after == 12
    assert digest_after == digest_before
    assert not Path(f"{db_path}.bak-v12").exists()


def test_db_check_on_a_v12_file_succeeds_and_never_migrates(db_path) -> None:
    _build_v12_db(db_path)
    version_before, digest_before = _version_and_hash(db_path)

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    assert result.exit_code == 0, result.output
    assert "version: 12" in result.output
    assert "result: OK" in result.output
    version_after, digest_after = _version_and_hash(db_path)
    assert version_before == 12
    assert version_after == 12
    assert digest_after == digest_before
    assert not Path(f"{db_path}.bak-v12").exists()


def test_maintain_dry_run_on_v12_never_migrates(db_path) -> None:
    """G2-B: the app's Home pending-count and Clean up preview run
    `maintain --dry-run` — a read. On a v12 file it must succeed
    WITHOUT migrating, without a backup copy, byte-identical."""
    _build_v12_db(db_path)
    version_before, digest_before = _version_and_hash(db_path)

    result = CliRunner().invoke(
        main,
        ["maintain", "--dry-run", "--format", "json", "--confirm", "json", "--db", db_path],
    )

    assert result.exit_code == 0, result.output
    version_after, digest_after = _version_and_hash(db_path)
    assert version_before == 12
    assert version_after == 12
    assert digest_after == digest_before, "a dry-run rewrote the v12 file"
    assert not Path(f"{db_path}.bak-v12").exists()


def test_undo_and_redo_dry_run_on_v12_never_migrate(db_path) -> None:
    """G2-B + B4-19: `undo --dry-run` / `redo --dry-run` on a v12 file
    refuse loudly and honestly — the undo groups are the `group_id` rows
    (migration 013), so the read-only open demands floor 13 and answers
    SchemaOutdated (MAINTAIN-009, `required=13`), never a misleading
    nothing-to-undo — and leave the file byte-identical, version 12, no
    backup copy."""
    _build_v12_db(db_path)
    version_before, digest_before = _version_and_hash(db_path)

    undo_result = CliRunner().invoke(main, ["undo", "--dry-run", "--db", db_path])
    redo_result = CliRunner().invoke(main, ["redo", "--dry-run", "--db", db_path])

    assert undo_result.exit_code == 1, undo_result.output
    assert "MAINTAIN-009" in undo_result.output, undo_result.output
    assert "required=13" in undo_result.output, undo_result.output
    assert redo_result.exit_code == 1, redo_result.output
    assert "MAINTAIN-009" in redo_result.output, redo_result.output
    version_after, digest_after = _version_and_hash(db_path)
    assert version_before == 12
    assert version_after == 12
    assert digest_after == digest_before, "a dry-run rewrote the v12 file"
    assert not Path(f"{db_path}.bak-v12").exists()

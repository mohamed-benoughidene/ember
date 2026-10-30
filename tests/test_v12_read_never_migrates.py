"""v12 read paths: `ember history`, `export` and `db-check` never migrate.

Undo step 01 §2: an untouched v12 file (scripts 001-012 applied, version
stamped 12, no group_id column) must stay at v12 — the query boot is
read-only and db-check never migrates — and all three commands must
succeed on it.
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

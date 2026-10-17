"""Tests for the relate database open path in the SQLite adapter."""

from __future__ import annotations

import sqlite3

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import ensure_relate_schema, open_relate_database
from ember.relate.errors import DbMigrationFailed, DbOpenFailed, SchemaOutdated


def test_open_relate_database_directory_path_raises_db_open_failed(tmp_path) -> None:
    with pytest.raises(DbOpenFailed) as exc:
        open_relate_database(str(tmp_path))

    assert exc.value.code == "RELATE-012"


def test_open_relate_database_migration_failure_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [(1, "CREATE TABLE ok (id INTEGER);"), (6, "THIS IS NOT SQL;")],
    )

    with pytest.raises(DbMigrationFailed) as exc:
        open_relate_database(str(tmp_path / "test.db"))

    assert exc.value.code == "RELATE-013"


def test_ensure_relate_schema_rejects_old_version(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "raw.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")

    with pytest.raises(SchemaOutdated) as exc:
        ensure_relate_schema(conn)

    assert exc.value.code == "RELATE-014"


def test_open_relate_database_applies_all_migrations(db_path) -> None:
    conn = open_relate_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    assert version == 9

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"links", "item_embeddings"} <= tables

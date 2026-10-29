"""Tests for the relate database open path in the SQLite adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import ensure_relate_schema, open_relate_database
from ember.relate.errors import DbMigrationFailed, DbOpenFailed, SchemaOutdated


def test_open_relate_database_directory_path_raises_db_open_failed(tmp_path) -> None:
    with pytest.raises(DbOpenFailed) as exc:
        open_relate_database(str(tmp_path))

    assert exc.value.code == "RELATE-012"


def test_open_relate_database_missing_file_raises_db_open_failed(tmp_path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(DbOpenFailed) as exc:
        open_relate_database(str(missing))

    assert exc.value.code == "RELATE-012"
    assert not missing.exists()


def test_open_relate_database_corrupt_file_raises_db_open_failed(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(DbOpenFailed) as exc:
        open_relate_database(str(corrupt))

    assert exc.value.code == "RELATE-012"


def test_open_relate_database_migration_failure_raises(tmp_path, monkeypatch) -> None:
    target = tmp_path / "test.db"
    Path(target).touch()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [(1, "CREATE TABLE ok (id INTEGER);"), (6, "THIS IS NOT SQL;")],
    )

    with pytest.raises(DbMigrationFailed) as exc:
        open_relate_database(str(target))

    assert exc.value.code == "RELATE-013"


def test_ensure_relate_schema_rejects_old_version(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "raw.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")

    with pytest.raises(SchemaOutdated) as exc:
        ensure_relate_schema(conn)

    assert exc.value.code == "RELATE-014"


def test_ensure_relate_schema_rejects_version_8(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "raw.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (8)")

    with pytest.raises(SchemaOutdated) as exc:
        ensure_relate_schema(conn)

    assert exc.value.code == "RELATE-014"
    assert exc.value.context["required"] == 11


def test_ensure_relate_schema_accepts_version_11(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "raw.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (11)")

    ensure_relate_schema(conn)


def test_open_relate_database_old_schema_exits_with_relate_014(db_path, monkeypatch) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (8)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(sqlite_adapter, "_apply_migrations", lambda conn: None)

    with pytest.raises(SchemaOutdated) as exc:
        open_relate_database(db_path)

    assert exc.value.code == "RELATE-014"


def test_open_relate_database_applies_all_migrations(db_path) -> None:
    Path(db_path).touch()
    conn = open_relate_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    assert version == 12

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"links", "item_embeddings"} <= tables

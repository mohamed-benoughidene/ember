"""Tests for the transactional migration runner."""

from __future__ import annotations

import sqlite3

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import _apply_migrations, open_database


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def test_failed_migration_rolls_back_schema_and_version(
    db_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [(1, "CREATE TABLE half (id INTEGER);\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(sqlite3.Error):
        open_database(db_path)

    conn = sqlite3.connect(db_path)
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 0
    assert "half" not in _table_names(conn)
    conn.close()


def test_later_migration_failure_keeps_earlier_migration(
    db_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [
            (1, "CREATE TABLE first (id INTEGER);"),
            (2, "CREATE TABLE second (id INTEGER);\nTHIS IS NOT SQL;"),
        ],
    )

    with pytest.raises(sqlite3.Error):
        open_database(db_path)

    conn = sqlite3.connect(db_path)
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    tables = _table_names(conn)
    assert version == 1
    assert "first" in tables
    assert "second" not in tables
    conn.close()


def test_foreign_keys_restored_after_failed_migration(
    db_path, monkeypatch
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [(1, "THIS IS NOT SQL;")],
    )

    with pytest.raises(sqlite3.Error):
        _apply_migrations(conn)

    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_successful_runner_commits_version_with_schema(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 10
    assert {"links", "item_embeddings"} <= _table_names(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()

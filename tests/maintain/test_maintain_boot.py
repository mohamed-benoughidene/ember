"""Boot errors for the maintain DB open path: MAINTAIN-007/008/009."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import ensure_maintain_schema, open_maintain_database
from ember.maintain.errors import (
    DbMigrationFailed as MaintainDbMigrationFailed,
    DbOpenFailed as MaintainDbOpenFailed,
    SchemaOutdated as MaintainSchemaOutdated,
)


def test_open_maintain_database_missing_file_raises_007(tmp_path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(MaintainDbOpenFailed) as exc:
        open_maintain_database(str(missing))

    assert exc.value.code == "MAINTAIN-007"
    assert not missing.exists()


def test_open_maintain_database_corrupt_file_raises_007(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(MaintainDbOpenFailed) as exc:
        open_maintain_database(str(corrupt))

    assert exc.value.code == "MAINTAIN-007"


def test_open_maintain_database_migration_failure_raises_008(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "test.db"
    Path(target).touch()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [(1, "CREATE TABLE ok (id INTEGER);"), (6, "THIS IS NOT SQL;")],
    )

    with pytest.raises(MaintainDbMigrationFailed) as exc:
        open_maintain_database(str(target))

    assert exc.value.code == "MAINTAIN-008"


def test_open_maintain_database_old_schema_raises_009(db_path, monkeypatch) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (9)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(sqlite_adapter, "_apply_migrations", lambda conn: None)

    with pytest.raises(MaintainSchemaOutdated) as exc:
        open_maintain_database(db_path)

    assert exc.value.code == "MAINTAIN-009"


def test_open_maintain_database_schema_version_read_failure_raises_007(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "test.db"
    Path(target).touch()

    class SchemaVersionReadError(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if "FROM schema_version" in sql:
                raise sqlite3.Error("schema version read fail")
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(
        sqlite_adapter,
        "_connect",
        lambda db_path: SchemaVersionReadError(str(target)),
    )
    monkeypatch.setattr(sqlite_adapter, "_apply_migrations", lambda conn: None)

    with pytest.raises(MaintainDbOpenFailed) as exc:
        open_maintain_database(str(target))

    assert exc.value.code == "MAINTAIN-007"


def test_ensure_maintain_schema_rejects_version_9(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "raw.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (9)")

    with pytest.raises(MaintainSchemaOutdated) as exc:
        ensure_maintain_schema(conn)

    assert exc.value.code == "MAINTAIN-009"
    assert exc.value.context["required"] == 11


def test_ensure_maintain_schema_accepts_version_11(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "raw.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (11)")

    ensure_maintain_schema(conn)


def test_open_maintain_database_applies_all_migrations(db_path) -> None:
    Path(db_path).touch()
    conn = open_maintain_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    assert version == 13

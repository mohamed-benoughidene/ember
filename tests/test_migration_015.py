"""Migration 015 tests: the vector-cache format tag, preservation, fresh, failure.

Every test builds a real v14 database by hand (scripts 001-014 applied, version
stamped 14 — the current latest before this batch) and then lets the runner
apply 015, per the 012 test pattern.

The new column `item_embeddings.vector_format` is OPTIONAL (nullable, no
default, no rebuild, no backfill — constitution D5): a missing column (a
pre-015 file) and NULL and `float32` all mean the ONE format
`ember.relate.vector_format` defines — little-endian float32, the on-disk
format of the `vector` blob ever since migration 007 created the table.
"""

from __future__ import annotations

import importlib.resources
import sqlite3
import struct
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.migrations import LATEST_VERSION
from ember.adapters.sqlite import SqliteEmbedderStore, open_database
from ember.capture.errors import DbOpenFailed as CaptureDbOpenFailed
from tests.fakes import FIXED_TIME, insert_item, insert_source

_MIGRATIONS_TO_14 = (
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
    "014_add_change_log_source_id.sql",
)

_VECTOR_A = [0.25, -1.5, 2.0]
_VECTOR_A_BLOB = struct.pack("<3f", *_VECTOR_A)
_MODEL_A = "bge-base-en-v1.5"

_EMBEDDING_COLUMNS = "item_id, model_name, embedded_at, hex(vector)"


def _build_v14_db(db_path: str) -> None:
    """Build a real v14 database by hand with an item and a cached vector."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (14)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_14:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn, "old note")
    insert_item(conn, source_id=source_id, item_id=1, statement="use SQLite")
    insert_item(
        conn,
        source_id=source_id,
        item_id=2,
        item_type="Question",
        statement="which db",
        created_at="2026-02-01T00:00:00+00:00",
        validated=False,
    )
    # One real cache row written by the pre-015 build: no format tag exists
    # yet, so the row cannot carry one.
    conn.execute(
        "INSERT INTO item_embeddings (item_id, vector, model_name, embedded_at)"
        " VALUES (1, ?, ?, ?)",
        (_VECTOR_A_BLOB, _MODEL_A, FIXED_TIME),
    )
    conn.commit()
    conn.close()


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _pre_migration_snapshot(db_path: str) -> Path:
    """The one timestamped `.bak-<UTC stamp>-<hex>` pre-migration snapshot.

    Since B4-16 the runner names the copy `<db>.bak-<stamp>-<6hex>`, never
    again the reusable `.bak-v<version>`, so a repeated run leaves its own
    snapshot instead of overwriting one file.
    """
    directory = Path(db_path).parent
    name = Path(db_path).name
    snapshots = sorted(
        p
        for p in directory.glob(f"{name}.bak-*")
        if not p.name.startswith(f"{name}.bak-v")  # the legacy family
    )
    assert len(snapshots) == 1, f"expected one snapshot, got {snapshots}"
    return snapshots[0]


def test_migration_015_adds_nullable_vector_format_column(db_path) -> None:
    _build_v14_db(db_path)

    conn = open_database(db_path)
    info = {
        row["name"]: tuple(row)
        for row in conn.execute("PRAGMA table_info(item_embeddings)")
    }
    conn.close()

    assert "vector_format" in info
    _, name, column_type, notnull, default, pk = info["vector_format"]
    assert name == "vector_format"
    assert column_type == "TEXT"
    assert notnull == 0
    assert default is None
    assert pk == 0


def test_migration_015_preserves_all_rows_and_values(db_path) -> None:
    _build_v14_db(db_path)
    raw = sqlite3.connect(db_path)
    embeddings_before = _rows(
        raw,
        "SELECT item_id, vector, model_name, embedded_at"
        " FROM item_embeddings ORDER BY item_id",
    )
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    embeddings_after = _rows(
        raw,
        "SELECT item_id, vector, model_name, embedded_at"
        " FROM item_embeddings ORDER BY item_id",
    )
    assert embeddings_after == embeddings_before
    assert embeddings_before == [(1, _VECTOR_A_BLOB, _MODEL_A, FIXED_TIME)]
    # The new column reads as NULL on every pre-existing row: the missing tag
    # and NULL both mean today's float32 format.
    star = _rows(
        raw, "SELECT item_id, vector, model_name, embedded_at, vector_format"
        " FROM item_embeddings ORDER BY item_id"
    )
    assert star == [row + (None,) for row in embeddings_before]
    raw.close()


def test_migration_015_missing_and_null_format_read_as_float32(db_path) -> None:
    """A pre-015 row (no tag at all) still decodes as float32 after 015."""
    _build_v14_db(db_path)

    conn = open_database(db_path)

    assert SqliteEmbedderStore(conn).get(1) == _VECTOR_A
    conn.close()


def test_migration_015_preserves_existing_schema(db_path) -> None:
    _build_v14_db(db_path)
    raw = sqlite3.connect(db_path)
    objects_before = {
        name: sql
        for name, sql in raw.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        ).fetchall()
    }
    tables = [
        name
        for (name,) in raw.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    columns_before = {
        table: _rows(raw, f"PRAGMA table_info({table})") for table in tables
    }
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    objects_after = {
        name: sql
        for name, sql in raw.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        ).fetchall()
    }
    columns_after = {
        table: _rows(raw, f"PRAGMA table_info({table})") for table in tables
    }
    raw.close()

    # No object was renamed, rebuilt or dropped. ADD COLUMN rewrites the
    # stored CREATE text of `item_embeddings`, so its truth comes from the
    # column diff below.
    for name, sql in objects_before.items():
        if name != "item_embeddings":
            assert objects_after[name] == sql
    for table in tables:
        if table == "item_embeddings":
            continue
        assert columns_after[table] == columns_before[table], table
    # item_embeddings gains exactly one trailing nullable column.
    vector_format_row = (4, "vector_format", "TEXT", 0, None, 0)
    assert columns_after["item_embeddings"] == (
        columns_before["item_embeddings"] + [vector_format_row]
    )


def test_fresh_install_applies_all_migrations_through_015(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    # Fresh installs land at the derived latest — 15 with this batch, from
    # the migrations directory listing alone (issue #45).
    assert version == LATEST_VERSION
    assert version >= 15
    info = {
        row["name"]: tuple(row)
        for row in conn.execute("PRAGMA table_info(item_embeddings)")
    }
    assert "vector_format" in info
    conn.close()


def test_failed_migration_leaves_intact_prior_database_015(
    db_path, monkeypatch
) -> None:
    _build_v14_db(db_path)
    raw = sqlite3.connect(db_path)
    embeddings_before = _rows(
        raw, f"SELECT {_EMBEDDING_COLUMNS} FROM item_embeddings ORDER BY item_id"
    )
    raw.close()

    real_scripts = sqlite_adapter._migration_scripts()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: real_scripts[:14] + [(15, "CREATE TABLE half;\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(CaptureDbOpenFailed):
        open_database(db_path)

    # The prior database file is intact at v14, and the pre-migration backup
    # was taken before the failing script ran — its own timestamped
    # snapshot (B4-16), a healthy copy at the pre-migration version.
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    assert (
        _rows(raw, f"SELECT {_EMBEDDING_COLUMNS} FROM item_embeddings ORDER BY item_id")
        == embeddings_before
    )
    raw.close()

    backup = sqlite3.connect(str(_pre_migration_snapshot(db_path)))
    assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    assert (
        _rows(
            backup,
            f"SELECT {_EMBEDDING_COLUMNS} FROM item_embeddings ORDER BY item_id",
        )
        == embeddings_before
    )
    backup.close()

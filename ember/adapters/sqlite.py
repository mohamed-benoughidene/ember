"""SQLite adapter: connection, numbered migrations, and the sources store."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from importlib import resources
from typing import Callable

from ember.capture.errors import ItemDbReadError, SourceDbReadError, SourceDbWriteError
from ember.capture.item_proposal import ContextItem
from ember.capture.source_storage import SourceRecord

_MIGRATIONS_MODULE = "ember.adapters.migrations"


def open_database(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection, enforce foreign keys, apply migrations."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_migrations(conn)
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    if conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    current = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    for number, script in _migration_scripts():
        if number > current:
            conn.executescript(script)
            conn.execute("UPDATE schema_version SET version = ?", (number,))
            conn.commit()


def _migration_scripts() -> list[tuple[int, str]]:
    package = resources.files(_MIGRATIONS_MODULE)
    scripts: list[tuple[int, str]] = []
    for entry in package.iterdir():
        if entry.name.endswith(".sql"):
            number = int(entry.name.split("_", 1)[0])
            scripts.append((number, entry.read_text(encoding="utf-8")))
    return sorted(scripts)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteSourceStore:
    """`SourceStorePort` implemented on SQLite. Write is the gatekeeper boundary."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._conn = conn
        self._clock = clock or _utc_now

    def find_by_hash(self, content_hash: str) -> SourceRecord | None:
        try:
            row = self._conn.execute(
                "SELECT id, full_text FROM sources WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise SourceDbReadError("db read fail", content_hash=content_hash) from exc
        if row is None:
            return None
        return SourceRecord(
            id=row["id"],
            full_text=row["full_text"],
            content_hash=content_hash,
        )

    def insert_source(self, *, title: str, full_text: str, content_hash: str) -> int:
        timestamp = self._clock()
        try:
            cursor = self._conn.execute(
                "INSERT INTO sources (title, full_text, timestamp, content_hash)"
                " VALUES (?, ?, ?, ?)",
                (title, full_text, timestamp, content_hash),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise SourceDbWriteError("db write fail", content_hash=content_hash) from exc
        return int(cursor.lastrowid)


class SqliteItemContext:
    """`ItemContextPort` on SQLite. Read-only: newest items first."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def recent_items(self, limit: int) -> list[ContextItem]:
        try:
            rows = self._conn.execute(
                "SELECT id, type, statement FROM items"
                " ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise ItemDbReadError("item read fail") from exc
        return [
            ContextItem(id=row["id"], type=row["type"], statement=row["statement"])
            for row in rows
        ]


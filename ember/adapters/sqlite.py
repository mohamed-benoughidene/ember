"""SQLite adapter: connection, numbered migrations, and the sources store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from importlib import resources
from typing import Callable

from ember.capture.errors import (
    ItemDbReadError,
    ItemDbWriteError,
    SourceDbReadError,
    SourceDbWriteError,
)
from ember.capture.item_gatekeeper import ValidatedItem
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

    def full_text_for(self, source_id: int) -> str | None:
        try:
            row = self._conn.execute(
                "SELECT full_text FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise SourceDbReadError("db read fail", source_id=source_id) from exc
        return None if row is None else row["full_text"]


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


class SqliteItemGatekeeper:
    """Gatekeeper boundary for `items` and `change_log`, plus item reads.

    The id source is a monotonic counter read once from the table, so every
    item in one run gets a fresh id before anything is written.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._conn = conn
        self._clock = clock or _utc_now
        self._next_id: int | None = None

    def statements(self) -> list[tuple[int, str]]:
        try:
            rows = self._conn.execute("SELECT id, statement FROM items").fetchall()
        except sqlite3.Error as exc:
            raise ItemDbReadError("item read fail") from exc
        return [(int(row["id"]), row["statement"]) for row in rows]

    def next_item_id(self) -> int:
        try:
            if self._next_id is None:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(id), 0) FROM items"
                ).fetchone()
                self._next_id = int(row[0]) + 1
        except sqlite3.Error as exc:
            raise ItemDbReadError("item read fail") from exc
        value = self._next_id
        self._next_id += 1
        return value

    def insert_item(self, item: ValidatedItem, *, validated: bool | None) -> None:
        try:
            self._conn.execute(
                "INSERT INTO items"
                " (id, type, statement, source_id, status, created_at, validated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.type,
                    item.statement,
                    item.source_id,
                    item.status,
                    item.created_at,
                    validated,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ItemDbWriteError("db write fail", item_id=item.id) from exc

    def log_created(self, item: ValidatedItem) -> None:
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
                " trigger_cause)"
                " VALUES (?, NULL, 'created', NULL, ?, ?, 'user_confirmed')",
                (item.id, item.statement, self._clock()),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ItemDbWriteError("db write fail", item_id=item.id) from exc

    def log_rejected(self, item: ValidatedItem) -> None:
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
                " trigger_cause)"
                " VALUES (NULL, NULL, 'proposed', NULL, ?, ?, 'rejected')",
                (_proposal_text(item), self._clock()),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ItemDbWriteError("db write fail") from exc


def _proposal_text(item: ValidatedItem) -> str:
    return json.dumps(
        {
            "type": item.type,
            "statement": item.statement,
            "source_quote": item.source_quote,
            "confidence": item.confidence,
        },
        ensure_ascii=False,
    )


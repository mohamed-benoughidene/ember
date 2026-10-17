"""SQLite adapter: connection, numbered migrations, and the sources store."""

from __future__ import annotations

import json
import os
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
from ember.capture.item_gatekeeper import ExistingItem, StoredItem, ValidatedItem
from ember.capture.item_proposal import ContextItem
from ember.capture.source_storage import SourceRecord
from ember.errors import EmberError
from ember.relate.errors import (
    DbMigrationFailed,
    DbOpenFailed,
    ItemsReadFailed,
    SchemaOutdated,
)
from ember.relate.rows import Link, NewItem

_MIGRATIONS_MODULE = "ember.adapters.migrations"


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a raw SQLite connection with row access by name and foreign keys on."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_database(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection, enforce foreign keys, apply migrations."""
    conn = _connect(db_path)
    _apply_migrations(conn)
    return conn


def open_relate_database(db_path: str) -> sqlite3.Connection:
    """Open an existing relate DB, apply migrations, check the schema.

    Raise `DbOpenFailed` (RELATE-012) when the file is missing or is not a
    readable SQLite database, and `DbMigrationFailed` (RELATE-013) when a
    migration fails.
    """
    if not os.path.exists(db_path):
        raise DbOpenFailed("db file missing", db_path=db_path)
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path)
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise DbOpenFailed("db open fail", db_path=db_path) from exc
    try:
        _apply_migrations(conn)
    except (sqlite3.Error, ValueError) as exc:
        conn.close()
        raise DbMigrationFailed("migration fail", db_path=db_path) from exc
    try:
        ensure_relate_schema(conn)
    except EmberError:
        conn.close()
        raise
    return conn


def ensure_relate_schema(conn: sqlite3.Connection) -> None:
    """Check the applied schema version is new enough for the relate engine.

    Raise `DbOpenFailed` (RELATE-012) if the version cannot be read, and
    `SchemaOutdated` (RELATE-014) if the version is below the required 9.
    """
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = 0 if row is None else int(row["version"])
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise DbOpenFailed("schema version read fail") from exc
    if version < 9:
        raise SchemaOutdated("schema version too old", version=version, required=9)


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    if conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    conn.commit()
    current = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for number, script in _migration_scripts():
            if number > current:
                _apply_migration(conn, number, script)
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _apply_migration(conn: sqlite3.Connection, number: int, script: str) -> None:
    """Apply one migration and its version bump in one transaction.

    Scripts must contain plain statements only. The runner owns the
    transaction and the foreign-key switch, so a script with its own
    `BEGIN` / `COMMIT` would nest transactions.
    """
    wrapped = (
        "BEGIN;\n"
        f"{script}\n"
        f"UPDATE schema_version SET version = {int(number)};\n"
        "COMMIT;"
    )
    try:
        conn.executescript(wrapped)
    except sqlite3.Error:
        conn.rollback()
        raise


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
        """Return the stored source with this hash, or None.

        Raise `SourceDbReadError` (CAPTURE-005) on a read failure.
        """
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
        """Insert one source, return the new id.

        Raise `SourceDbWriteError` (CAPTURE-006) on a write failure.
        """
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
        """Return `sources.full_text` for `source_id`, or None.

        Raise `SourceDbReadError` (CAPTURE-005) on a read failure.
        """
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
        """Return the newest items first, at most `limit` of them.

        Raise `ItemDbReadError` (CAPTURE-011) on a read failure.
        """
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


class SqliteLinkContext:
    """`LinkLookupPort` on SQLite. Read-only item and link lookups for relate.

    Every method raises `ItemsReadFailed` (RELATE-016) on a read failure.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def item_exists(self, item_id: int) -> bool:
        """Return whether an item with this id exists."""
        try:
            row = self._conn.execute(
                "SELECT 1 FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail", item_id=item_id) from exc
        return row is not None

    def item_type(self, item_id: int) -> str | None:
        """Return the item's type, or None if the item is missing."""
        try:
            row = self._conn.execute(
                "SELECT type FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail", item_id=item_id) from exc
        return None if row is None else row["type"]

    def item_statement(self, item_id: int) -> str | None:
        """Return the item's statement, or None if the item is missing."""
        try:
            row = self._conn.execute(
                "SELECT statement FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail", item_id=item_id) from exc
        return None if row is None else row["statement"]

    def item_created_at(self, item_id: int) -> str | None:
        """Return the item's created_at text, or None if the item is missing."""
        try:
            row = self._conn.execute(
                "SELECT created_at FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail", item_id=item_id) from exc
        return None if row is None else row["created_at"]

    def find_existing(
        self,
        source_id: int,
        target_id: int,
        link_type: str,
    ) -> Link | None:
        """Return the link row for this triple of any status, or None."""
        try:
            row = self._conn.execute(
                "SELECT id, source_item_id, target_item_id, link_type, status,"
                " created_at FROM links"
                " WHERE source_item_id = ? AND target_item_id = ? AND link_type = ?",
                (source_id, target_id, link_type),
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed(
                "link read fail",
                source_id=source_id,
                target_id=target_id,
                link_type=link_type,
            ) from exc
        if row is None:
            return None
        return Link(
            id=row["id"],
            source_item_id=row["source_item_id"],
            target_item_id=row["target_item_id"],
            link_type=row["link_type"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def existing_link_types(self, source_item_id: int) -> dict[int, set[str]]:
        """Return the link types already present from this source, by target id."""
        try:
            rows = self._conn.execute(
                "SELECT target_item_id, link_type FROM links"
                " WHERE source_item_id = ?",
                (source_item_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("link read fail", source_id=source_item_id) from exc
        existing: dict[int, set[str]] = {}
        for row in rows:
            existing.setdefault(int(row["target_item_id"]), set()).add(
                str(row["link_type"])
            )
        return existing

    def list_other_items(self, new_item_id: int) -> list[NewItem]:
        """Return every item except `new_item_id`, ordered by id."""
        try:
            rows = self._conn.execute(
                "SELECT id, type, statement, created_at FROM items"
                " WHERE id != ? ORDER BY id",
                (new_item_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail", item_id=new_item_id) from exc
        return [
            NewItem(
                id=row["id"],
                type=row["type"],
                statement=row["statement"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def find_latest_unlinked_active(self) -> NewItem | None:
        """Return the newest Active item with no link from it, or None."""
        try:
            row = self._conn.execute(
                "SELECT id, type, statement, created_at FROM items"
                " WHERE status = 'Active'"
                " AND id NOT IN (SELECT source_item_id FROM links)"
                " ORDER BY id DESC LIMIT 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail") from exc
        if row is None:
            return None
        return NewItem(
            id=row["id"],
            type=row["type"],
            statement=row["statement"],
            created_at=row["created_at"],
        )


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

    def statements(self) -> list[ExistingItem]:
        """Return every stored item's id and statement.

        Raise `ItemDbReadError` (CAPTURE-011) on a read failure.
        """
        try:
            rows = self._conn.execute("SELECT id, statement FROM items").fetchall()
        except sqlite3.Error as exc:
            raise ItemDbReadError("item read fail") from exc
        return [
            ExistingItem(item_id=int(row["id"]), statement=row["statement"])
            for row in rows
        ]

    def find_item(self, item_id: int) -> StoredItem | None:
        """Return one stored item's type and current flag, or None.

        Raise `ItemDbReadError` (CAPTURE-011) on a read failure.
        """
        try:
            row = self._conn.execute(
                "SELECT id, type, validated FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemDbReadError("item read fail", item_id=item_id) from exc
        if row is None:
            return None
        return StoredItem(
            id=int(row["id"]),
            type=row["type"],
            validated=None if row["validated"] is None else bool(row["validated"]),
        )

    def now(self) -> str:
        """The generated timestamp for a new item (Phase 3)."""
        return self._clock()

    def next_item_id(self) -> int:
        """Return a fresh item id, counting up from the highest stored id.

        Raise `ItemDbReadError` (CAPTURE-011) on a read failure.
        """
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
        """Insert one accepted item, with `validated` set only for Assumptions.

        Raise `ItemDbWriteError` (CAPTURE-013) on a write failure.
        """
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
        """Append the `created` change_log row for an accepted item.

        Raise `ItemDbWriteError` (CAPTURE-013) on a write failure.
        """
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
        """Append the `proposed` change_log row, with a null item_id.

        Raise `ItemDbWriteError` (CAPTURE-013) on a write failure.
        """
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

    def save_validated_flag(self, item: StoredItem, *, validated: bool) -> None:
        """Write the `validated` flag and append a `validated` change_log row.

        Raise `ItemDbWriteError` (CAPTURE-013) on a write failure.
        """
        try:
            self._conn.execute(
                "UPDATE items SET validated = ? WHERE id = ?",
                (validated, item.id),
            )
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
                " trigger_cause)"
                " VALUES (?, NULL, 'validated', ?, ?, ?, 'user_set_validated')",
                (
                    item.id,
                    _flag_text(item.validated),
                    _flag_text(validated),
                    self._clock(),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ItemDbWriteError("db write fail", item_id=item.id) from exc


def _flag_text(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


class SqliteAiResponseStore:
    """Write boundary for the raw AI answers (Constitution D8, spec 3.7 I16)."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._conn = conn
        self._clock = clock or _utc_now

    def save(
        self,
        *,
        source_id: int | None = None,
        item_id: int | None = None,
        raw_response: str,
    ) -> None:
        """Store one raw provider answer verbatim against exactly one owner.

        Raise `ValueError` when neither or both of `source_id` and `item_id`
        are set, and `ItemDbWriteError` (CAPTURE-013) on a write failure.
        """
        if (source_id is None) == (item_id is None):
            raise ValueError("save requires exactly one of source_id, item_id")
        try:
            self._conn.execute(
                "INSERT INTO ai_responses (source_id, item_id, response_text, timestamp)"
                " VALUES (?, ?, ?, ?)",
                (source_id, item_id, raw_response, self._clock()),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ItemDbWriteError(
                "db write fail", source_id=source_id, item_id=item_id
            ) from exc


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

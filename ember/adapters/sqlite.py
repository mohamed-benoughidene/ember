"""SQLite adapter: connection, numbered migrations, and the sources store."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import urllib.parse
from array import array
from collections import deque
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
from ember.maintain.errors import (
    ChangeLogWriteFailed as MaintainChangeLogWriteFailed,
    DbMigrationFailed as MaintainDbMigrationFailed,
    DbOpenFailed as MaintainDbOpenFailed,
    ItemEditWriteFailed as MaintainItemEditWriteFailed,
    ItemsReadFailed as MaintainItemsReadFailed,
    RemoveLinkWriteFailed as MaintainRemoveLinkWriteFailed,
    SchemaOutdated as MaintainSchemaOutdated,
    StatusWriteFailed as MaintainStatusWriteFailed,
)
from ember.maintain.rows import EditChange, ItemState, LinkChange, StatusChange
from ember.query.errors import (
    DbOpenFailed as QueryDbOpenFailed,
    ItemsReadFailed as QueryItemsReadFailed,
    SchemaOutdated as QuerySchemaOutdated,
)
from ember.query.rows import ChangeRow, QueryItem
from ember.relate.embedding_store import EmbeddingStorePort
from ember.relate.errors import (
    ChangeLogWriteFailed,
    DbMigrationFailed,
    DbOpenFailed,
    EmbeddingReadFailed,
    EmbeddingWriteFailed,
    GraphReadFailed,
    ItemsReadFailed,
    LinkWriteFailed,
    SchemaOutdated,
)
from ember.relate.rows import ChangeLogEntry, Link, NewItem

_MIGRATIONS_MODULE = "ember.adapters.migrations"

_BACKUPS_TO_KEEP = 3

# One definition for "a supersedes edge the cycle rules walk" (rule 8/9): the
# row is Confirmed and was never reversed. Shared by supersedes_ancestors and
# supersedes_blocking_link so the two walks can never diverge.
LIVE_SUPERSEDES_EDGE = "status = 'Confirmed' AND reversed_at IS NULL"


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a raw SQLite connection with row access by name and foreign keys on."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    """Open a connection that cannot write, even by accident.

    The path is URI-quoted because SQLite parses `?`, `#` and `%` as URI
    syntax, and `uri=True` is required for the `mode=ro` parameter to be read
    at all.
    """
    conn = sqlite3.connect(
        f"file:{urllib.parse.quote(str(db_path))}?mode=ro", uri=True
    )
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
    except (sqlite3.Error, ValueError, OSError) as exc:
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
    `SchemaOutdated` (RELATE-014) if the version is below the required 11.
    """
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = 0 if row is None else int(row["version"])
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise DbOpenFailed("schema version read fail") from exc
    if version < 11:
        raise SchemaOutdated("schema version too old", version=version, required=11)


def open_maintain_database(db_path: str) -> sqlite3.Connection:
    """Open an existing maintain DB, apply migrations, check the schema.

    Raise `DbOpenFailed` (MAINTAIN-007) when the file is missing or is not a
    readable SQLite database, `DbMigrationFailed` (MAINTAIN-008) when a
    migration fails, and `SchemaOutdated` (MAINTAIN-009) when the applied
    version is below the required 10.
    """
    if not os.path.exists(db_path):
        raise MaintainDbOpenFailed("db file missing", db_path=db_path)
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path)
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise MaintainDbOpenFailed("db open fail", db_path=db_path) from exc
    try:
        _apply_migrations(conn)
    except (sqlite3.Error, ValueError, OSError) as exc:
        conn.close()
        raise MaintainDbMigrationFailed("migration fail", db_path=db_path) from exc
    try:
        ensure_maintain_schema(conn)
    except EmberError:
        conn.close()
        raise
    return conn


def ensure_maintain_schema(conn: sqlite3.Connection) -> None:
    """Check the applied schema version is new enough for the maintain engine.

    Raise `DbOpenFailed` (MAINTAIN-007) if the version cannot be read, and
    `SchemaOutdated` (MAINTAIN-009) if the version is below the required 11.
    """
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = 0 if row is None else int(row["version"])
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise MaintainDbOpenFailed("schema version read fail") from exc
    if version < 11:
        raise MaintainSchemaOutdated(
            "schema version too old", version=version, required=11
        )


def open_query_database(db_path: str) -> sqlite3.Connection:
    """Open an existing query DB **read-only**, check the schema, never migrate.

    Raise `DbOpenFailed` (QUERY-003) when the file is missing or is not a
    readable SQLite database, and `SchemaOutdated` (QUERY-004) when the applied
    version is below the required 10.

    Unlike every other engine's boot path this one applies no migration: a read
    command that rewrites the ledger is not a read, and `query` is the one
    command an AI may run against the user's database.
    """
    if not os.path.exists(db_path):
        raise QueryDbOpenFailed("db file missing", db_path=db_path)
    try:
        conn = _connect_readonly(db_path)
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    except sqlite3.Error as exc:
        raise QueryDbOpenFailed("db open fail", db_path=db_path) from exc
    try:
        ensure_query_schema(conn, db_path)
    except EmberError:
        conn.close()
        raise
    return conn


def ensure_query_schema(
    conn: sqlite3.Connection, db_path: str | None = None
) -> None:
    """Check the applied schema version is new enough for the query engine.

    Raise `DbOpenFailed` (QUERY-003) if the version cannot be read, and
    `SchemaOutdated` (QUERY-004) if the version is below the required 10.
    `db_path` is carried as context when the caller has it.
    """
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = 0 if row is None else int(row["version"])
    except (sqlite3.Error, ValueError, TypeError) as exc:
        context = {"db_path": db_path} if db_path is not None else {}
        raise QueryDbOpenFailed("schema version read fail", **context) from exc
    if version < 10:
        raise QuerySchemaOutdated(
            "schema version too old", version=version, required=10
        )


def _database_file(conn: sqlite3.Connection) -> str | None:
    """Return the on-disk path of the connection's main database, or None.

    An in-memory or temporary database has no file, so there is nothing to
    back up.
    """
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        if row[1] == "main" and row[2]:
            return str(row[2])
    return None


def _backup_database(conn: sqlite3.Connection, current: int) -> None:
    """Copy the database file once before any above-version script runs.

    The copy is `<db>.bak-v<current>` (D7), taken with `copy2` so metadata
    survives. Retention: keep the newest 3 `<db>.bak-v*` files, delete older.
    Raise the raw `OSError` on failure. Per-engine boot call sites wrap it.
    """
    db_path = _database_file(conn)
    if db_path is None:
        return
    shutil.copy2(db_path, f"{db_path}.bak-v{current}")
    _prune_backups(db_path)


def _prune_backups(db_path: str) -> None:
    """Keep the newest 3 `<db>.bak-v*` files next to `db_path`, delete older."""
    directory = os.path.dirname(os.path.abspath(db_path))
    prefix = os.path.basename(os.path.abspath(db_path)) + ".bak-v"
    backups: list[tuple[int, str]] = []
    for name in os.listdir(directory):
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix):]
        if suffix.isdigit():
            backups.append((int(suffix), name))
    backups.sort(reverse=True)
    for _, name in backups[_BACKUPS_TO_KEEP:]:
        os.remove(os.path.join(directory, name))


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    if conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    conn.commit()
    current = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    pending = [
        (number, script) for number, script in _migration_scripts() if number > current
    ]
    # One backup per run, before the first above-version script: a no-op open
    # must not churn the retention window (L2 §5.0).
    if pending:
        _backup_database(conn, int(current))
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for number, script in pending:
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

    Every item and link read raises `ItemsReadFailed` (RELATE-016) on a read
    failure, except `neighbors_of` and `supersedes_blocking_link`, which raise
    `GraphReadFailed` (RELATE-021).
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
                " created_at, reversed_at FROM links"
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
            reversed_at=row["reversed_at"],
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

    def neighbors_of(self, item_id: int) -> list[int]:
        """Return the 1-hop neighbors reached through Confirmed links.

        Either side of a link counts, so a Confirmed row pointing at `item_id`
        is a neighbor just like a row pointing away from it. The result is
        sorted and deduplicated; `item_id` itself is never in it. Depth is 1:
        this call does not recurse (plan step 2 section 4 step 4).

        Raise `GraphReadFailed` (RELATE-021) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT source_item_id, target_item_id FROM links"
                " WHERE status = 'Confirmed'"
                " AND (source_item_id = ? OR target_item_id = ?)",
                (item_id, item_id),
            ).fetchall()
        except sqlite3.Error as exc:
            raise GraphReadFailed("graph read fail", item_id=item_id) from exc
        neighbors: set[int] = set()
        for row in rows:
            for other_id in (row["source_item_id"], row["target_item_id"]):
                if other_id != item_id:
                    neighbors.add(int(other_id))
        return sorted(neighbors)

    def item_status(self, item_id: int) -> str | None:
        """Return the item's status, or None if the item is missing."""
        try:
            row = self._conn.execute(
                "SELECT status FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise ItemsReadFailed("item read fail", item_id=item_id) from exc
        return None if row is None else row["status"]

    def supersedes_ancestors(self, item_id: int) -> set[int]:
        """Return every item reachable upstream via live Confirmed supersedes links.

        Breadth-first over `links` rows where `source_item_id` is the current
        node and `link_type = 'supersedes'`. Only live rows are walked
        (`status = 'Confirmed' AND reversed_at IS NULL`), so a reversed
        supersedes no longer closes a cycle for the corrective inverse
        (L2 hardening §9, rule 8). The seed is not included unless a cycle
        walks back to it (cycles are forbidden at write time).
        """
        ancestors: set[int] = set()
        frontier: list[int] = [item_id]
        try:
            while frontier:
                current = frontier.pop()
                rows = self._conn.execute(
                    "SELECT target_item_id FROM links"
                    " WHERE source_item_id = ? AND link_type = 'supersedes'"
                    f" AND {LIVE_SUPERSEDES_EDGE}",
                    (current,),
                ).fetchall()
                for row in rows:
                    target = int(row["target_item_id"])
                    if target not in ancestors:
                        ancestors.add(target)
                        frontier.append(target)
        except sqlite3.Error as exc:
            raise ItemsReadFailed("link read fail", item_id=item_id) from exc
        return ancestors

    def supersedes_blocking_link(self, source_id: int, target_id: int) -> Link | None:
        """Return the live Confirmed supersedes link joining the two items.

        Walks the same edges `supersedes_ancestors` walks (`status =
        'Confirmed' AND reversed_at IS NULL`), tried in link-id order (the
        L2 §14 tie-break: first edge in id order). Walk 1 starts at
        `target_id` and looks for a path to `source_id`. Walk 2 starts at
        `source_id` and looks for a path to `target_id` (the two rule-8
        directions). Returns the first edge that reaches the goal, else None.
        Used only for cycle-rejection detail text, never the decision (the
        cycle decision stays `supersedes_ancestors`).

        Raise `GraphReadFailed` (RELATE-021) on a read failure.
        """
        by_source: dict[int, list[Link]] = {}
        try:
            rows = self._conn.execute(
                "SELECT id, source_item_id, target_item_id, link_type, status,"
                " created_at, reversed_at FROM links"
                " WHERE link_type = 'supersedes'"
                f" AND {LIVE_SUPERSEDES_EDGE}"
                " ORDER BY id"
            ).fetchall()
        except sqlite3.Error as exc:
            raise GraphReadFailed(
                "graph read fail", source_id=source_id, target_id=target_id
            ) from exc
        for row in rows:
            link = Link(
                id=row["id"],
                source_item_id=row["source_item_id"],
                target_item_id=row["target_item_id"],
                link_type=row["link_type"],
                status=row["status"],
                created_at=row["created_at"],
                reversed_at=row["reversed_at"],
            )
            by_source.setdefault(int(row["source_item_id"]), []).append(link)
        for start, goal in ((target_id, source_id), (source_id, target_id)):
            seen = {start}
            frontier: deque[int] = deque([start])
            while frontier:
                current = frontier.popleft()
                for link in by_source.get(current, []):
                    nxt = link.target_item_id
                    if nxt == goal:
                        return link
                    if nxt not in seen:
                        seen.add(nxt)
                        frontier.append(nxt)
        return None


class SqliteMaintainContext:
    """`MaintainLookupPort` on SQLite. Read-only item, link and marker looks.

    Every read raises `ItemsReadFailed` (MAINTAIN-010) on a read failure.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_items(self) -> list[ItemState]:
        """Return every item: id, type, status, close_reason, status_origin,
        plus the two authorial columns `rationale` / `source` (migration 004)
        that `edit-item` reads its observed old values from.

        Raise `ItemsReadFailed` (MAINTAIN-010) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT id, type, status, close_reason, status_origin,"
                " rationale, source FROM items"
            ).fetchall()
        except sqlite3.Error as exc:
            raise MaintainItemsReadFailed("item read fail") from exc
        return [
            ItemState(
                id=row["id"],
                type=row["type"],
                status=row["status"],
                close_reason=row["close_reason"],
                status_origin=row["status_origin"],
                rationale=row["rationale"],
                source=row["source"],
            )
            for row in rows
        ]

    def list_confirmed_links(self) -> list[Link]:
        """Return every `links` row whose status is `Confirmed`.

        Raise `ItemsReadFailed` (MAINTAIN-010) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT id, source_item_id, target_item_id, link_type, status,"
                " created_at FROM links WHERE status = 'Confirmed'"
            ).fetchall()
        except sqlite3.Error as exc:
            raise MaintainItemsReadFailed("link read fail") from exc
        return [
            Link(
                id=row["id"],
                source_item_id=row["source_item_id"],
                target_item_id=row["target_item_id"],
                link_type=row["link_type"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_reversed_link_ids(self) -> set[int]:
        """Return the link ids carrying a `link_reversed` change_log row.

        Raise `ItemsReadFailed` (MAINTAIN-010) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT DISTINCT link_id FROM change_log"
                " WHERE field_changed = 'link_reversed' AND link_id IS NOT NULL"
            ).fetchall()
        except sqlite3.Error as exc:
            raise MaintainItemsReadFailed("change_log read fail") from exc
        return {int(row["link_id"]) for row in rows}


class SqliteQueryContext:
    """`QueryLookupPort` on SQLite: the whole world Engine D may read.

    Every read raises `ItemsReadFailed` (QUERY-005) on a read failure. Reads
    cover `items`, `links` and `change_log` only, never `sources` or
    `ai_responses`, the two tables holding the most sensitive bytes.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_items(self) -> list[QueryItem]:
        """Return every item, ordered by id ascending.

        Raise `ItemsReadFailed` (QUERY-005) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT id, type, statement, status, close_reason,"
                " status_origin, rationale, created_at, source_id"
                " FROM items ORDER BY id"
            ).fetchall()
        except sqlite3.Error as exc:
            raise QueryItemsReadFailed("item read fail", table="items") from exc
        return [
            QueryItem(
                id=row["id"],
                type=row["type"],
                statement=row["statement"],
                status=row["status"],
                close_reason=row["close_reason"],
                status_origin=row["status_origin"],
                rationale=row["rationale"],
                created_at=row["created_at"],
                source_id=row["source_id"],
            )
            for row in rows
        ]

    def list_links(self) -> list[Link]:
        """Return every link, ordered by id ascending.

        Raise `ItemsReadFailed` (QUERY-005) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT id, source_item_id, target_item_id, link_type, status,"
                " created_at FROM links ORDER BY id"
            ).fetchall()
        except sqlite3.Error as exc:
            raise QueryItemsReadFailed("link read fail", table="links") from exc
        return [
            Link(
                id=row["id"],
                source_item_id=row["source_item_id"],
                target_item_id=row["target_item_id"],
                link_type=row["link_type"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_change_log(self) -> list[ChangeRow]:
        """Return every `change_log` row, ordered by id ascending.

        Raise `ItemsReadFailed` (QUERY-005) on a read failure.
        """
        try:
            rows = self._conn.execute(
                "SELECT id, item_id, link_id, field_changed, old_value,"
                " new_value, timestamp, trigger_cause"
                " FROM change_log ORDER BY id"
            ).fetchall()
        except sqlite3.Error as exc:
            raise QueryItemsReadFailed(
                "change_log read fail", table="change_log"
            ) from exc
        return [
            ChangeRow(
                id=row["id"],
                item_id=row["item_id"],
                link_id=row["link_id"],
                field_changed=row["field_changed"],
                old_value=row["old_value"],
                new_value=row["new_value"],
                timestamp=row["timestamp"],
                trigger_cause=row["trigger_cause"],
            )
            for row in rows
        ]

    def item_exists(self, item_id: int) -> bool:
        """Return whether `items` holds `item_id`.

        Raise `ItemsReadFailed` (QUERY-005) on a read failure.
        """
        try:
            row = self._conn.execute(
                "SELECT 1 FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise QueryItemsReadFailed("item read fail", table="items") from exc
        return row is not None


class SqliteMaintainStore:
    """`MaintainStorePort` on SQLite: one atomic status write per batch.

    The `items` UPDATEs and the `change_log` INSERTs share one implicit
    transaction with a single `commit()` at the end, so the batch is
    all-or-nothing (Constitution D3). A failure on either half rolls the whole
    batch back, so a caller never sees a status written without its log row.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._conn = conn
        self._clock = clock or _utc_now

    def apply_status_changes(self, changes: list[StatusChange]) -> int:
        """Write every change's status and its `change_log` row in one batch.

        Return `len(changes)`. Raise `StatusWriteFailed` (MAINTAIN-011) when an
        `items` UPDATE fails, and `ChangeLogWriteFailed` (MAINTAIN-012) when a
        `change_log` INSERT fails. Either failure rolls the whole batch back.
        """
        for change in changes:
            try:
                self._conn.execute(
                    "UPDATE items SET status = ?, close_reason = ? WHERE id = ?",
                    (change.new_status, change.close_reason, change.item_id),
                )
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise MaintainStatusWriteFailed(
                    "status update fail", item_id=change.item_id
                ) from exc
        timestamp = self._clock()
        for change in changes:
            try:
                self._conn.execute(
                    "INSERT INTO change_log"
                    " (item_id, link_id, field_changed, old_value, new_value,"
                    " timestamp, trigger_cause) VALUES (?, ?, 'status', ?, ?, ?, ?)",
                    (
                        change.item_id,
                        change.link_id,
                        _status_old_value(change),
                        _status_new_value(change),
                        timestamp,
                        change.trigger_cause,
                    ),
                )
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise MaintainChangeLogWriteFailed(
                    "change_log insert fail", item_id=change.item_id
                ) from exc
        self._conn.commit()
        return len(changes)

    def apply_status_origin(self, item_id: int, origin: str) -> None:
        """Write one item's `status_origin` and its `change_log` row atomically.

        Raise `StatusWriteFailed` (MAINTAIN-011) when the `items` UPDATE fails,
        and `ChangeLogWriteFailed` (MAINTAIN-012) when the `change_log` INSERT
        fails. Either failure rolls the whole write back.
        """
        try:
            row = self._conn.execute(
                "SELECT status_origin FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            old_origin = row["status_origin"] if row is not None else "derived"
            self._conn.execute(
                "UPDATE items SET status_origin = ? WHERE id = ?",
                (origin, item_id),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainStatusWriteFailed(
                "status_origin update fail", item_id=item_id
            ) from exc
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value,"
                " timestamp, trigger_cause)"
                " VALUES (?, NULL, 'status_origin', ?, ?, ?,"
                " 'user_set_status')",
                (item_id, old_origin, origin, self._clock()),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainChangeLogWriteFailed(
                "change_log insert fail", item_id=item_id
            ) from exc
        self._conn.commit()

    def apply_reversal(self, change: StatusChange, marker: ChangeLogEntry) -> int:
        """Restore one item and pair the reversal column with its marker.

        One implicit transaction, one `commit()` at the end: the `items`
        UPDATE, the `status` `change_log` row derived from `change`, the
        `reversed_at` column on the `links` row, and the `link_reversed`
        marker row taken from `marker` are all-or-nothing (L2 §6 pairing rule).

        The adapter owns time: it stamps all three writes from ONE
        `self._clock()` read and **overwrites** the passed `marker.timestamp`
        (the marker's timestamp is a placeholder, not trusted). One read keeps
        `links.reversed_at` == the marker's `timestamp` by construction:
        a second read would break the db-check replay rule.

        Return `1`. Raise `StatusWriteFailed` (MAINTAIN-011) when the `items`
        UPDATE or the `reversed_at` UPDATE fails, and
        `ChangeLogWriteFailed` (MAINTAIN-012) when either `change_log` INSERT
        fails. Either failure rolls the whole write back.
        """
        try:
            self._conn.execute(
                "UPDATE items SET status = ?, close_reason = ? WHERE id = ?",
                (change.new_status, change.close_reason, change.item_id),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainStatusWriteFailed(
                "status update fail", item_id=change.item_id
            ) from exc
        timestamp = self._clock()
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value,"
                " timestamp, trigger_cause) VALUES (?, ?, 'status', ?, ?, ?, ?)",
                (
                    change.item_id,
                    change.link_id,
                    _status_old_value(change),
                    _status_new_value(change),
                    timestamp,
                    change.trigger_cause,
                ),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainChangeLogWriteFailed(
                "change_log insert fail", item_id=change.item_id
            ) from exc
        try:
            self._conn.execute(
                "UPDATE links SET reversed_at = ? WHERE id = ?",
                (timestamp, marker.link_id),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainStatusWriteFailed(
                "reversed_at update fail", item_id=change.item_id
            ) from exc
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value,"
                " timestamp, trigger_cause) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    marker.item_id,
                    marker.link_id,
                    marker.field_changed,
                    marker.old_value,
                    marker.new_value,
                    timestamp,
                    marker.trigger_cause,
                ),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainChangeLogWriteFailed(
                "change_log insert fail", item_id=marker.item_id
            ) from exc
        self._conn.commit()
        return 1

    def apply_item_edit(self, change: EditChange) -> int:
        """Write one item's authorial column and its `change_log` row atomically.

        One implicit transaction, one `commit()` at the end: the `items`
        UPDATE and the ledger INSERT (field_changed = `change.field`,
        `old_value` = the observed prior value, NULL stays NULL,
        trigger_cause from the change) are all-or-nothing, so the ledger row
        and the column can never diverge.

        Return `1`. Raise `ItemEditWriteFailed` (MAINTAIN-016) when the
        `items` UPDATE fails, and `ChangeLogWriteFailed` (MAINTAIN-012) when
        the `change_log` INSERT fails. Either failure rolls the whole write
        back.
        """
        column = _EDIT_COLUMNS.get(change.field)
        if column is None:
            raise MaintainItemEditWriteFailed(
                "item edit column unknown",
                item_id=change.item_id,
                field=change.field,
            )
        try:
            self._conn.execute(
                f"UPDATE items SET {column} = ? WHERE id = ?",
                (change.new_value, change.item_id),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainItemEditWriteFailed(
                "item edit update fail",
                item_id=change.item_id,
                field=change.field,
            ) from exc
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value,"
                " timestamp, trigger_cause) VALUES (?, NULL, ?, ?, ?, ?, ?)",
                (
                    change.item_id,
                    change.field,
                    change.old_value,
                    change.new_value,
                    self._clock(),
                    change.trigger_cause,
                ),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainChangeLogWriteFailed(
                "change_log insert fail", item_id=change.item_id
            ) from exc
        self._conn.commit()
        return 1

    def apply_remove_link(self, change: LinkChange) -> int:
        """Write the ONE removal and its `link_removed` ledger row atomically.

        One implicit transaction, one `commit()` at the end: the `links`
        status UPDATE (`Confirmed -> Rejected`, never an INSERT, never a
        DELETE, never flipped back, `reversed_at` untouched) and the ledger
        INSERT (`field_changed='link_removed'`, `item_id` = the link's
        source, the `insert_link_with_log` discipline) are all-or-nothing,
        so the row can never flip without its ledger row (Constitution D3).

        Return `1`. Raise `RemoveLinkWriteFailed` (MAINTAIN-017) when the
        `links` UPDATE fails, and `ChangeLogWriteFailed` (MAINTAIN-012) when
        the `change_log` INSERT fails. Either failure rolls the whole write
        back.
        """
        try:
            self._conn.execute(
                "UPDATE links SET status = ? WHERE id = ?",
                (change.new_status, change.link_id),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainRemoveLinkWriteFailed(
                "link removal update fail", link_id=change.link_id
            ) from exc
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value,"
                " timestamp, trigger_cause) VALUES (?, ?, 'link_removed', ?,"
                " ?, ?, ?)",
                (
                    change.item_id,
                    change.link_id,
                    change.old_status,
                    change.new_status,
                    self._clock(),
                    change.trigger_cause,
                ),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise MaintainChangeLogWriteFailed(
                "change_log insert fail",
                item_id=change.item_id,
                link_id=change.link_id,
            ) from exc
        self._conn.commit()
        return 1


def _status_old_value(change: StatusChange) -> str:
    if change.old_status == "Closed":
        return f"{change.old_status}:{change.old_close_reason}"
    return change.old_status


_EDIT_COLUMNS: dict[str, str] = {"rationale": "rationale", "source": "source"}
"""The only `items` columns `apply_item_edit` may write. The validator
whitelists the field name first, and this keeps the f-string UPDATE honest
even if a future caller forgets."""


def _status_new_value(change: StatusChange) -> str:
    if change.new_status == "Closed":
        return f"{change.new_status}:{change.close_reason}"
    return change.new_status


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


class SqliteLinkStore:
    """`LinkStorePort` on SQLite: one atomic `links` + `change_log` write.

    Order matters: the link row is inserted first so `change_log.link_id` (a
    foreign key after migration 008) can reference it. A failure on either
    insert rolls the whole transaction back.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_link_with_log(
        self, link_row: Link, change_log_row: ChangeLogEntry
    ) -> int:
        """Insert the link and its change_log row in one transaction.

        Return the new link id. Raise `LinkWriteFailed` (RELATE-029) when the
        link insert fails, and `ChangeLogWriteFailed` (RELATE-011) when the
        change_log insert fails (the link insert is rolled back).
        """
        try:
            cursor = self._conn.execute(
                "INSERT INTO links"
                " (source_item_id, target_item_id, link_type, status, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    link_row.source_item_id,
                    link_row.target_item_id,
                    link_row.link_type,
                    link_row.status,
                    link_row.created_at,
                ),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise LinkWriteFailed(
                "link insert fail",
                source_item_id=link_row.source_item_id,
                target_item_id=link_row.target_item_id,
                link_type=link_row.link_type,
            ) from exc
        link_id = int(cursor.lastrowid)
        stamped = change_log_row.model_copy(update={"link_id": link_id})
        try:
            self._conn.execute(
                "INSERT INTO change_log"
                " (item_id, link_id, field_changed, old_value, new_value,"
                " timestamp, trigger_cause) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    stamped.item_id,
                    stamped.link_id,
                    stamped.field_changed,
                    stamped.old_value,
                    stamped.new_value,
                    stamped.timestamp,
                    stamped.trigger_cause,
                ),
            )
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise ChangeLogWriteFailed(
                "change_log insert fail", item_id=stamped.item_id, link_id=link_id
            ) from exc
        self._conn.commit()
        return link_id


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


class SqliteEmbedderStore:
    """`EmbeddingStorePort` on SQLite. Owns the packed vector format.

    The cache is derived data: every method here reads or rewrites
    `item_embeddings` rows only, and never touches `items`, `links`, or
    `change_log` (Constitution D2).

    Read failures raise `EmbeddingReadFailed` (RELATE-037); write failures
    raise `EmbeddingWriteFailed` (RELATE-019).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._conn = conn
        self._clock = clock or _utc_now

    def get(self, item_id: int) -> list[float] | None:
        """Return the cached vector for `item_id`, or None when it has no row.

        Raise `EmbeddingReadFailed` (RELATE-037) on a read failure, including a
        vector blob that cannot be decoded as float32.
        """
        try:
            row = self._conn.execute(
                "SELECT vector FROM item_embeddings WHERE item_id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise EmbeddingReadFailed("embedding read fail", item_id=item_id) from exc
        if row is None:
            return None
        try:
            return _unpack_vector(row["vector"])
        except (TypeError, ValueError) as exc:
            raise EmbeddingReadFailed("embedding decode fail", item_id=item_id) from exc

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        """Store one vector row, replacing any existing row for `item_id`.

        `embedded_at` comes from the clock (UTC now by default). The row is
        replaced unconditionally, so a stale vector from an older model never
        survives a re-encode.

        Raise `EmbeddingWriteFailed` (RELATE-019) on a write failure.
        """
        blob = _pack_vector(vector)
        timestamp = self._clock()
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO item_embeddings"
                " (item_id, vector, model_name, embedded_at) VALUES (?, ?, ?, ?)",
                (item_id, blob, model_name, timestamp),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise EmbeddingWriteFailed(
                "embedding write fail", item_id=item_id
            ) from exc

    def model_name_of(self, item_id: int) -> str | None:
        """Return the model name stored for `item_id`, or None when it is absent.

        Raise `EmbeddingReadFailed` (RELATE-037) on a read failure.
        """
        try:
            row = self._conn.execute(
                "SELECT model_name FROM item_embeddings WHERE item_id = ?", (item_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise EmbeddingReadFailed("embedding read fail", item_id=item_id) from exc
        return None if row is None else row["model_name"]

    def first_model_name(self) -> str | None:
        """Return the model name of any one cached row, or None when empty.

        The pre-flight check (plan step 2 section 4 step 1) uses this to spot a
        cache written by an older model.

        Raise `EmbeddingReadFailed` (RELATE-037) on a read failure.
        """
        try:
            row = self._conn.execute(
                "SELECT model_name FROM item_embeddings ORDER BY item_id LIMIT 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise EmbeddingReadFailed("embedding read fail") from exc
        return None if row is None else row["model_name"]

    def wipe(self) -> None:
        """Delete every cached vector. The next run re-encodes from items.

        Raise `EmbeddingWriteFailed` (RELATE-019) on a write failure.
        """
        try:
            self._conn.execute("DELETE FROM item_embeddings")
            self._conn.commit()
        except sqlite3.Error as exc:
            raise EmbeddingWriteFailed("embedding wipe fail") from exc


def build_embedding_store(conn: sqlite3.Connection) -> EmbeddingStorePort:
    """Build the `item_embeddings` cache adapter for the relate engine.

    Input: an open SQLite connection. Output: a store whose reads raise
    `RELATE-037 EmbeddingReadFailed` and whose writes raise
    `RELATE-019 EmbeddingWriteFailed`. Building it performs no I/O.
    """
    return SqliteEmbedderStore(conn)


def build_ai_response_store(conn: sqlite3.Connection) -> SqliteAiResponseStore:
    """Build the raw-AI-answer store adapter for the relate Phase 3.5 save."""
    return SqliteAiResponseStore(conn)


def _pack_vector(vector: list[float]) -> bytes:
    """Pack a float vector as little-endian float32, the on-disk format."""
    values = array("f", vector)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def _unpack_vector(blob: bytes) -> list[float]:
    """Decode a little-endian float32 blob back into floats."""
    values = array("f")
    values.frombytes(blob)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tolist()

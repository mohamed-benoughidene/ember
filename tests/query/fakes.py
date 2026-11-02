"""In-memory stand-ins and seed helpers for the query tests."""

from __future__ import annotations

import importlib.resources
import sqlite3

from ember.adapters.sqlite import open_database
from ember.query.rows import ChangeRow, CurrentStateRow, QueryItem
from ember.relate.rows import Link
from tests.fakes import FIXED_TIME

_V10_MIGRATIONS = (
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
)

_V11_MIGRATIONS = _V10_MIGRATIONS + (
    "011_add_links_reversed_at_and_enforcement_triggers.sql",
)


class FakeQueryLookup:
    """Working stand-in for `QueryLookupPort` that records every call.

    `calls` holds one string per call, so a test can prove a code path made
    no lookup at all (the global `history` view) or exactly one.
    """

    def __init__(
        self,
        items: list[QueryItem] | None = None,
        links: list[Link] | None = None,
        change_rows: list[ChangeRow] | None = None,
        source_texts: dict[int, str] | None = None,
    ) -> None:
        self._items = list(items or [])
        self._links = list(links or [])
        self._change_rows = list(change_rows or [])
        # Bridge step 02: `source_text_for` texts, keyed by item id.
        self._source_texts = dict(source_texts or {})
        self.calls: list[str] = []

    def list_items(self) -> list[QueryItem]:
        self.calls.append("list_items")
        return list(self._items)

    def list_links(self) -> list[Link]:
        self.calls.append("list_links")
        return list(self._links)

    def list_change_log(self) -> list[ChangeRow]:
        self.calls.append("list_change_log")
        return list(self._change_rows)

    def item_exists(self, item_id: int) -> bool:
        self.calls.append(f"item_exists:{item_id}")
        return any(item.id == item_id for item in self._items)

    def source_text_for(self, item_id: int) -> str:
        self.calls.append(f"source_text_for:{item_id}")
        return self._source_texts.get(item_id, "")


def make_item(
    item_id: int = 1,
    *,
    status: str = "Active",
    item_type: str = "Decision",
    statement: str = "Use SQLite",
    source_id: int = 1,
    close_reason: str | None = None,
    status_origin: str = "derived",
    rationale: str | None = None,
    created_at: str = FIXED_TIME,
    source: str | None = None,
    validated: bool | None = None,
) -> QueryItem:
    """Build one `QueryItem` for the pure-core tests."""
    return QueryItem(
        id=item_id,
        type=item_type,
        statement=statement,
        status=status,
        close_reason=close_reason,
        status_origin=status_origin,
        rationale=rationale,
        created_at=created_at,
        source_id=source_id,
        source=source,
        validated=validated,
    )


def make_row(
    item_id: int = 1,
    *,
    status: str = "Active",
    item_type: str = "Decision",
    statement: str = "Use SQLite",
    source_id: int = 1,
    status_origin: str = "derived",
) -> CurrentStateRow:
    """Build one `CurrentStateRow` for the renderer tests."""
    return CurrentStateRow(
        id=item_id,
        type=item_type,
        statement=statement,
        status=status,
        created_at=FIXED_TIME,
        source_id=source_id,
        status_origin=status_origin,
        challenged=status == "Challenged",
    )


def make_change_row(
    row_id: int = 1,
    *,
    item_id: int | None = 1,
    link_id: int | None = None,
    field_changed: str = "created",
    trigger_cause: str = "user_confirmed",
    old_value: str | None = None,
    new_value: str | None = "Active",
    timestamp: str = FIXED_TIME,
) -> ChangeRow:
    """Build one `ChangeRow` for the classifier and history tests."""
    return ChangeRow(
        id=row_id,
        item_id=item_id,
        link_id=link_id,
        field_changed=field_changed,
        old_value=old_value,
        new_value=new_value,
        timestamp=timestamp,
        trigger_cause=trigger_cause,
    )


def make_link(
    link_id: int,
    source_item_id: int,
    target_item_id: int,
    *,
    link_type: str = "depends_on",
    status: str = "Confirmed",
    reversed_at: str | None = None,
) -> Link:
    """Build one `Link` for the history tests."""
    return Link(
        id=link_id,
        source_item_id=source_item_id,
        target_item_id=target_item_id,
        link_type=link_type,
        status=status,
        created_at=FIXED_TIME,
        reversed_at=reversed_at,
    )


def make_v10(db_path: str) -> sqlite3.Connection:
    """Create a real schema-version-10 database and return a writing handle.

    The migration SQL scripts 001-010 are applied by hand and the version
    is stamped 10, so nothing past 010 ever runs (finding 4.7 #10, story
    44): the file is a genuine pre-011 database where `links.reversed_at`
    and `items.metadata` do not exist, and the read-only boot accepts it
    as-is without migrating. Calling it again on an already-built file
    just returns a writing handle.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    built = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master"
        " WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()[0]
    if built:
        return conn
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _V10_MIGRATIONS:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    return conn


def make_v11(db_path: str) -> sqlite3.Connection:
    """Create a real schema-version-11 database and return a writing handle.

    Same recipe as `make_v10`, one migration further: scripts 001-011 are
    applied by hand and the version is stamped 11, so nothing past 011 ever
    runs. The file genuinely has `links.reversed_at` (migration 011) but no
    `items.metadata` (012) and no `change_log.group_id` (013). Calling it
    again on an already-built file just returns a writing handle.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    built = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master"
        " WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()[0]
    if built:
        return conn
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (11)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _V11_MIGRATIONS:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    return conn


def make_v9(db_path: str) -> None:
    """Create a real version-9 database: all tables, an older version stamp.

    The version is lowered after the migrations run, so the file is a genuine
    database the read-only boot must refuse rather than migrate.
    """
    conn = open_database(db_path)
    conn.execute("UPDATE schema_version SET version = 9")
    conn.commit()
    conn.close()

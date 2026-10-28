"""In-memory stand-ins and seed helpers for the query tests."""

from __future__ import annotations

import sqlite3

from ember.adapters.sqlite import open_database
from ember.query.rows import ChangeRow, CurrentStateRow, QueryItem
from ember.relate.rows import Link
from tests.fakes import FIXED_TIME


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
    ) -> None:
        self._items = list(items or [])
        self._links = list(links or [])
        self._change_rows = list(change_rows or [])
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


def make_v10(db_path: str) -> sqlite3.Connection:
    """Create a real schema-version-10 database and return a writing handle."""
    return open_database(db_path)


def make_v9(db_path: str) -> None:
    """Create a real version-9 database: all tables, an older version stamp.

    The version is lowered after the migrations run, so the file is a genuine
    database the read-only boot must refuse rather than migrate.
    """
    conn = open_database(db_path)
    conn.execute("UPDATE schema_version SET version = 9")
    conn.commit()
    conn.close()

"""Shared test doubles, plus the fixed clock and row-seed helpers."""

from __future__ import annotations

import sqlite3

from ember.capture.errors import UserAbort
from ember.capture.item_gatekeeper import NearDupWarning, ValidatedItem
from ember.capture.item_proposal import ContextItem, ProposalResponse
from ember.capture.source_storage import SourceRecord

FIXED_TIME = "2026-01-01T00:00:00+00:00"


class FakeItemProposer:
    """Canned AI. Each call returns the next response, or raises it if it is one."""

    def __init__(self, outcomes: list[ProposalResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, list[ContextItem]]] = []

    def propose(self, raw_text: str, context: list[ContextItem]) -> ProposalResponse:
        self.calls.append((raw_text, context))
        if not self._outcomes:
            raise AssertionError("FakeItemProposer ran out of outcomes")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeItemContext:
    """In-memory item reader. Records the limits it was asked for."""

    def __init__(self, items: list[ContextItem]) -> None:
        self.items = items
        self.limits: list[int] = []

    def recent_items(self, limit: int) -> list[ContextItem]:
        self.limits.append(limit)
        return self.items[:limit]


class FakeSourceStore:
    def __init__(self) -> None:
        self.rows: dict[str, SourceRecord] = {}
        self._next_id = 1

    def find_by_hash(self, content_hash: str) -> SourceRecord | None:
        return self.rows.get(content_hash)

    def insert_source(self, *, title: str, full_text: str, content_hash: str) -> int:
        source_id = self._next_id
        self._next_id += 1
        self.rows[content_hash] = SourceRecord(source_id, full_text, content_hash)
        return source_id


class FakeConfirm:
    """Scripted user. Answers in order; runs out -> UserAbort (STDIN closed)."""

    def __init__(
        self, answers: list[str], *, abort_error: type[Exception] | None = None
    ) -> None:
        self._answers = list(answers)
        self._abort_error = abort_error or UserAbort
        self.prompts: list[str] = []
        self.written: list[str] = []

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            raise self._abort_error("input ended")
        return self._answers.pop(0)

    def write(self, text: str) -> None:
        self.written.append(text)


class FakeItemCommit:
    """Records every `items` and `change_log` write."""

    def __init__(self) -> None:
        self.items: list[tuple[ValidatedItem, bool | None]] = []
        self.created: list[ValidatedItem] = []
        self.rejected: list[ValidatedItem] = []

    def insert_item(self, item: ValidatedItem, *, validated: bool | None) -> None:
        self.items.append((item, validated))

    def log_created(self, item: ValidatedItem) -> None:
        self.created.append(item)

    def log_rejected(self, item: ValidatedItem) -> None:
        self.rejected.append(item)


def insert_source(conn: sqlite3.Connection, full_text: str = "body") -> int:
    """Insert one `sources` row and return its id."""
    cursor = conn.execute(
        "INSERT INTO sources (title, full_text, timestamp, content_hash)"
        " VALUES ('t', ?, ?, ?)",
        (full_text, FIXED_TIME, f"hash-{full_text}"),
    )
    return int(cursor.lastrowid)


def insert_item(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    item_id: int | None = None,
    item_type: str = "Decision",
    statement: str = "Use SQLite",
    created_at: str = FIXED_TIME,
    validated: bool | None = None,
    status: str = "Active",
    close_reason: str | None = None,
    status_origin: str = "derived",
    metadata: str | None = None,
) -> int:
    """Insert one `items` row and return its id.

    The metadata column is written only when a label is given, so v10 and v11
    hand-built databases (no metadata column yet) stay insertable.
    """
    columns = (
        "id, type, statement, source_id, status, created_at,"
        " validated, close_reason, status_origin"
    )
    placeholders = "?, ?, ?, ?, ?, ?, ?, ?, ?"
    values: list[object] = [
        item_id,
        item_type,
        statement,
        source_id,
        status,
        created_at,
        validated,
        close_reason,
        status_origin,
    ]
    if metadata is not None:
        columns += ", metadata"
        placeholders += ", ?"
        values.append(metadata)
    cursor = conn.execute(
        f"INSERT INTO items ({columns}) VALUES ({placeholders})", tuple(values)
    )
    return int(cursor.lastrowid)


def insert_link(
    conn: sqlite3.Connection,
    source_item_id: int,
    target_item_id: int,
    link_type: str,
    *,
    status: str = "Confirmed",
    created_at: str = FIXED_TIME,
) -> int:
    """Insert one `links` row and return its id."""
    cursor = conn.execute(
        "INSERT INTO links (source_item_id, target_item_id, link_type, status,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (source_item_id, target_item_id, link_type, status, created_at),
    )
    return int(cursor.lastrowid)


def insert_link_reversed(
    conn: sqlite3.Connection, link_id: int, item_id: int
) -> None:
    """Write the `link_reversed` marker row for a reversed link."""
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, ?, 'link_reversed', 'Confirmed', 'Reversed', ?, 'reversal')",
        (item_id, link_id, FIXED_TIME),
    )


def make_item(
    item_id: int = 1,
    *,
    item_type: str = "Decision",
    statement: str = "Use SQLite",
    source_id: int = 1,
    warning: NearDupWarning | None = None,
    metadata: str | None = None,
) -> ValidatedItem:
    """Build one `ValidatedItem` for the Phase 4 tests."""
    return ValidatedItem(
        id=item_id,
        type=item_type,
        statement=statement,
        source_quote="use SQLite",
        confidence=0.9,
        source_id=source_id,
        created_at=FIXED_TIME,
        status="Active",
        near_dup_warning=warning,
        metadata=metadata,
    )

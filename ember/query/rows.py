"""Row models shared by the query core and the storage adapter.

`Link` is imported from `ember.relate.rows` on purpose (D3): one table, one
shape. `ChangeRow` is a *different* shape from `ChangeLogEntry` on purpose:
the write model's `item_id` is non-nullable, but Capture writes `proposed`
rows with a NULL `item_id`, so the read side needs the nullable shape.
"""

from __future__ import annotations

from pydantic import BaseModel

from ember.relate.rows import Link


class QueryItem(BaseModel):
    """One `items` row as this engine reads it (Phase 1 input)."""

    id: int
    type: str
    statement: str
    status: str
    close_reason: str | None
    status_origin: str
    rationale: str | None
    created_at: str
    source_id: int


class CurrentStateRow(BaseModel):
    """The `current_state` output view: a projection with a warning flag.

    `challenged` is the explicit warning flag the spec asks for, so a reader
    never has to compare status strings.
    """

    id: int
    type: str
    statement: str
    status: str
    created_at: str
    source_id: int
    status_origin: str
    challenged: bool


class ChangeRow(BaseModel):
    """One `change_log` row as this engine reads it (item_id may be NULL)."""

    id: int
    item_id: int | None
    link_id: int | None
    field_changed: str
    old_value: str | None
    new_value: str | None
    timestamp: str
    trigger_cause: str

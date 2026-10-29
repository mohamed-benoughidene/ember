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


class TopicFilter(BaseModel):
    """What `topic_search` may narrow before it scores (V1.x amendment D).

    `None` means no restriction on that axis. `limit` crops the ranked list
    behind the sort, so `limit` 0 is an explicit empty result, never an error.
    """

    status: str | None = None
    type: str | None = None
    limit: int | None = None


class SearchHit(BaseModel):
    """One `topic_search` result: the score plus enough to read the item.

    `status` travels with the hit so a superseded decision is visible next to
    a live one (the `Closed` items are searched on purpose).
    """

    item_id: int
    score: float
    type: str
    statement: str
    status: str


class WhyReason(BaseModel):
    """One reason behind the item `why` was asked about.

    `rationale` is NULL on every row this build can see (nothing writes the
    column yet), and that is correct rather than a bug.
    """

    item_id: int
    type: str
    statement: str
    status: str
    rationale: str | None
    depth: int
    via_link_type: str
    via_link_id: int


class WhyResult(BaseModel):
    """The start item plus its reasons, in `(depth, item_id)` order."""

    item: QueryItem
    reasons: list[WhyReason]


class HistoryEvent(BaseModel):
    """One rendered `change_log` event.

    `item_id` means whatever the writer recorded as the subject. The two
    `link_*_item_id` fields sit beside it so the two possible meanings never
    blur. `cause` is the raw `trigger_cause`, and `close_reason` is the one
    derived field (non-null only on a `status_changed` event whose new value
    is a `Closed` status).
    """

    timestamp: str
    kind: str
    cause: str
    field_changed: str
    item_id: int | None
    link_id: int | None
    link_source_item_id: int | None
    link_target_item_id: int | None
    link_type: str | None
    old_value: str | None
    new_value: str | None
    close_reason: str | None

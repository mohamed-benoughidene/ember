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
    """One `items` row as this engine reads it (Phase 1 input).

    `source` (the authorial note, migration 004) and `validated` (the human
    0/1 flag) grow the read model additively for the bridge reads (bridge
    step 02): both default to `None`, so every pre-existing constructor and
    reader keeps working unchanged.
    """

    id: int
    type: str
    statement: str
    status: str
    close_reason: str | None
    status_origin: str
    rationale: str | None
    created_at: str
    source_id: int
    source: str | None = None
    validated: bool | None = None


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
    """One `change_log` row as this engine reads it (item_id may be NULL).

    `group_id` is the additive undo-group stamp (migration 013, undo step
    05): export renders it, defaulting to `None` so every pre-013 caller and
    reader keeps working unchanged.
    """

    id: int
    item_id: int | None
    link_id: int | None
    field_changed: str
    old_value: str | None
    new_value: str | None
    timestamp: str
    trigger_cause: str
    group_id: int | None = None


class TopicFilter(BaseModel):
    """What `topic_search` may narrow before it scores (V1.x amendment D).

    `None` means no restriction on that axis. `limit` crops the ranked list
    behind the sort, so `limit` 0 is an explicit empty result, never an error.
    """

    status: str | None = None
    type: str | None = None
    limit: int | None = None


class HistoryPage(BaseModel):
    """What `history` may crop after the sort (V1.x amendment D).

    `None` means no restriction on that axis: no cap, no skip, no time cut.
    `limit` 0 is an explicit empty result, never an error. `since` is the
    normalised (UTC, `isoformat`) ISO-8601 boundary the validator writes back,
    so the core compares opaque ISO text the same way the sort already does.
    The item scope never lives here: it stays the raw `item_id` parameter (D3).
    """

    limit: int | None = None
    offset: int | None = None
    since: str | None = None


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


class ListPage(BaseModel):
    """What `list_items` may crop before the render (bridge step 02).

    `None` means no restriction on that axis: no cap, no skip, as `history`.
    `limit` 0 is an explicit empty result, never an error. The status/type
    narrowing never lives here: it stays the existing `TopicFilter` (D3).
    """

    limit: int | None = None
    offset: int | None = None


class ShowLink(BaseModel):
    """One of the shown item's links, in one direction (bridge step 02).

    `type` is the link type, `status` travels with it so a Rejected or
    reversed link stays visible. The `other_item_*` fields describe the item
    at the far end of the edge, whichever side that is. `reversed_at` is the
    migration-011 timestamp, `null` on a live link and on every pre-011
    (schema v10) file, where the column does not exist.
    """

    id: int
    type: str
    status: str
    other_item_id: int
    other_item_type: str
    other_item_statement: str
    other_item_status: str
    reversed_at: str | None


class ShowItemResult(BaseModel):
    """The `show_item` output view: the item, its source text, its links."""

    item: QueryItem
    source: str
    links_out: list[ShowLink]
    links_in: list[ShowLink]

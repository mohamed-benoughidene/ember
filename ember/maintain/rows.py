"""Row models shared by the maintain core and the storage layer.

`Link` is imported from `ember.relate.rows` on purpose (D3): one table, one
shape. Duplicating it would put two definitions for the same row in the repo.
"""

from __future__ import annotations

from pydantic import BaseModel

from ember.relate.rows import Link


class ItemState(BaseModel):
    """One item's lifecycle state, as read from `items` (Phase 1).

    `rationale` / `source` carry the item's two human authorial columns
    (migration 004): the observed old values `validate_edit_item` reads.
    Defaults are `None`, so every constructor that predates them holds.
    """

    id: int
    type: str
    status: str
    close_reason: str | None
    status_origin: str
    rationale: str | None = None
    source: str | None = None


class MaintainSnapshot(BaseModel):
    """The whole world the pure derivation reads (Phase 1 output)."""

    items: list[ItemState]
    links: list[Link]
    reversed_link_ids: set[int]


class StatusChange(BaseModel):
    """One item's intended status change (Phase 2 output).

    `new_status` stays a plain `str`, not a `Literal`: step 2's
    `MAINTAIN-011` test needs to hand it an invalid value. The `change_log`
    `old_value`/`new_value` encoding is derived in the adapter, never here.
    """

    item_id: int
    old_status: str
    new_status: str
    close_reason: str | None
    old_close_reason: str | None = None
    trigger_cause: str
    link_id: int | None


class EditChange(BaseModel):
    """One item's intended rationale or source edit (Phase 2 output).

    `old_value` is the observed prior value read in Phase 1 (NULL stays
    NULL) and is what the store writes to `change_log.old_value`. `field` is
    a column name the validator whitelisted (`rationale` or `source`).
    """

    item_id: int
    field: str
    old_value: str | None
    new_value: str
    trigger_cause: str


class LinkChange(BaseModel):
    """One link's intended removal (Phase 2 output).

    The ONE write it describes is `UPDATE links SET status='Rejected'`. It
    never INSERTs, DELETEs, or flips `Rejected` back. `old_status` is the
    observed Phase-1 value, and `item_id` is the link's **source** (Relate's
    convention, stated so Query guesses nothing, engine-query-plan §4.6).
    The link's type/target for the report line are display-only and are read
    from the Phase-1 snapshot at the CLI edge (step plan 05 §3), never
    carried here.
    """

    link_id: int
    old_status: str
    new_status: str
    trigger_cause: str
    item_id: int

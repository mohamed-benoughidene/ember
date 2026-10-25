"""Row models shared by the maintain core and the storage layer.

`Link` is imported from `ember.relate.rows` on purpose (D3): one table, one
shape. Duplicating it would put two definitions for the same row in the repo.
"""

from __future__ import annotations

from pydantic import BaseModel

from ember.relate.rows import Link


class ItemState(BaseModel):
    """One item's lifecycle state, as read from `items` (Phase 1)."""

    id: int
    type: str
    status: str
    close_reason: str | None
    status_origin: str


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

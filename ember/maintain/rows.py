"""Row models shared by the maintain core and the storage layer.

`Link` is imported from `ember.relate.rows` on purpose (D3): one table, one
shape. Duplicating it would put two definitions for the same row in the repo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ember.relate.rows import ChangeLogEntry, Link


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
    # Additive Phase-1 display column (L2 §14.3): the AI close proposal
    # judges and the confirm block shows the item's own text. Defaults are
    # None, so every constructor that predates it holds.
    statement: str | None = None
    # The `validated` flag as the ledger encodes it (`true` / `false` /
    # NULL, undo step 02): the undo refusal rule compares the CURRENT value
    # of every grouped ledger row against the row's recorded new value, so
    # the flag must ride the item read. Defaults are None, so every
    # constructor that predates it holds.
    validated: str | None = None


class MaintainSnapshot(BaseModel):
    """The whole world the pure derivation reads (Phase 1 output).

    `shield_log` is the additive Phase-1 ledger slice the timestamp-scoped
    manual shield reads (L2 §13.5): the manual-clear rows and the
    `link_confirmed` rows, in id order. The default keeps every constructor
    that predates it valid, and makes a snapshot without the slice
    fail-closed silent (no clear row visible).
    """

    items: list[ItemState]
    links: list[Link]
    reversed_link_ids: set[int]
    shield_log: list[ChangeLogEntry] = []


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
    # Set by `merge_and_filter` on a shielded item's winning change whose
    # evidence passed the timestamp rule (L2 §13.4): the adapter executes
    # the re-arm, returning `status_origin` to `'derived'` in the same
    # batch. Never stamped on exempt (human) changes.
    rearm: bool = False


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


class StatusValue(BaseModel):
    """The two halves of one encoded ledger status value (undo step 02).

    `change_log` stores a status as `<status>` or `<status>:<reason>`, and
    formats a null reason as the literal `None`, so `Closed:None` means
    Closed with no reason. The splitter is the one public inverse of the
    writer's encoding: Query's private splitter stays private, and Maintain
    never imports it (B1/B5).
    """

    status: str
    close_reason: str | None


def split_status_value(value: str) -> StatusValue:
    """Split one encoded ledger status value into status and close reason.

    The writer (`apply_status_changes`) encodes a `Closed` write as
    `<status>:<reason>` and a null reason as the literal `None`, so the read
    side splits on the **first** colon only and treats `Closed:None` and a
    bare `Closed` the same: close reason `None`. A non-`Closed` value never
    carries a reason.

    This is the public home for that rule; `history.py` may call it, and
    nothing outside the rows module may re-implement it (D3).
    """
    status, separator, reason = value.partition(":")
    if status != "Closed" or not separator or not reason or reason == "None":
        return StatusValue(status=status, close_reason=None)
    return StatusValue(status=status, close_reason=reason)


class LedgerGroup(BaseModel):
    """One undo group: the ledger rows ONE human action wrote (L2 §5.1).

    A group is the unit Undo and Redo step back by. Rows from before
    migration 013 carry no group id and never appear here — the grouped
    read returns only rows with a non-NULL `group_id` (story 123).
    """

    group_id: int
    rows: list[ChangeLogEntry]


class UndoSnapshot(BaseModel):
    """The whole world the pure undo core reads (undo step 02, L2 §5.3).

    `groups` is the grouped ledger slice the new lookup read
    `list_grouped_ledger()` returns, in group order; `items` and `links`
    come from the existing reads. `ungrouped_rows_exist` is the one bit the
    grouped read cannot see by definition: whether ledger rows WITHOUT a
    group id exist (pre-013 rows). The refused-with-nothing-to-undo message
    must tell the user whether such older changes exist (story 123), so the
    flag rides the snapshot. Defaults to False, so every constructor that
    predates the field holds.
    """

    groups: list[LedgerGroup]
    items: list[ItemState]
    links: list[Link]
    ungrouped_rows_exist: bool = False


class InverseChange(BaseModel):
    """One pending inverse write (undo step 02, L2 §5.3 rules 4 and 5).

    Named model, never a tuple (I4). `item_id` or `link_id` — exactly one —
    names the row the store must UPDATE; `field` is the column on that row.
    Status values are carried in the ledger's encoded `<status>:<reason>`
    form; the store splits them with the public `split_status_value` before
    writing the two item columns. `expected_value` is the value the refusal
    rule verified against the live state — the store re-checks it in the
    same transaction it writes (fail closed, never returned). A
    `reversed_at` change is symbolic: `expected_value` reads the marker
    state (`Reversed` / `Confirmed`), and a `new_value` of `Reversed` means
    "stamp `reversed_at` with the write time", `None` means "clear it".
    `ledger_row` is the appended `change_log` row (cause `user_undo` or
    `user_redo`), kept in the same shape the original action wrote.
    """

    item_id: int | None = None
    link_id: int | None = None
    field: str
    expected_value: str | None
    new_value: str | None
    ledger_row: ChangeLogEntry


class UndoResult(BaseModel):
    """The plan one undo or redo applies (undo step 02, L2 §5.3).

    `source_action` and `target_label` feed the menu line
    `"Undo Close item 3"` (story 113): the action being reversed or
    re-applied, and the human name of its primary target. `marker` is the
    single `undo_of` / `redo_of` pointer row the store appends (L2 §5.2,
    spec 12.4: one column, the pointer is a row).
    """

    source_group_id: int
    source_action: str
    target_label: str
    direction: Literal["undo", "redo"]
    changes: list[InverseChange]
    marker: ChangeLogEntry

"""Pure validators for the human Maintain commands.

Each validator reads a `MaintainSnapshot` and returns the list of changes
(`StatusChange` / `EditChange` / `LinkChange`) the store should apply. No
I/O, no clock, no DB (T1): the snapshot is the whole world, and the store
port does the writing (B3, T2).

The first three are the authoritative primary changes of their commands, so
each passes its primary change to `merge_and_filter(..., exempt=primary)` because a
human may move an item down (`Challenged -> Active`, `Closed -> Active`) or sideways
(`Challenged -> Closed`), bypassing the escalation-only ladder and the manual
shield. The rule-2 fan-out is *not* exempt: a dependent already `Challenged`
or `Closed` is not re-challenged (step-03 §4.4).
"""

from __future__ import annotations

from ember.maintain.derive import FLAGGING_REASONS, merge_and_filter
from ember.maintain.errors import (
    CloseReasonInvalid,
    CloseReasonMismatch,
    EditFieldUnknown,
    EditTargetMismatch,
    ItemAlreadyClosed,
    MaintainItemNotFound,
    RemoveLinkNotConfirmed,
    ReversalPreconditionFailed,
    StatusTransitionInvalid,
)
from ember.maintain.rows import (
    EditChange,
    ItemState,
    LinkChange,
    MaintainSnapshot,
    StatusChange,
)

CLOSE_REASONS: frozenset[str] = frozenset(
    {"answered", "invalidated", "superseded", "reversed", "expired"}
)
"""The 5 legal `--reason` values (L2 §6, `MAINTAIN-002` boundary)."""

EDIT_FIELDS: frozenset[str] = frozenset({"rationale", "source", "statement"})
"""The three field names `--field` may name. Under the ADR's Option A a
`statement` edit is known-but-rejected (`MAINTAIN-014`) and only `rationale`
on a `Decision` plus `source` on a `Finding` are writable."""

EDITABLE: dict[str, str] = {"rationale": "Decision", "source": "Finding"}
"""The Option-A writability gate (`MAINTAIN-014`), field -> item type that
may carry it. `statement` is deliberately absent, so nobody may write it."""

HUMAN_SETTABLE_REASONS: frozenset[str] = frozenset({"invalidated", "expired"})
"""Only these two reasons a human may pass to `close-item`; the rest are
machine reasons (`superseded`/`answered`) or reversal semantics (`reversed`)."""

SET_STATUS_TARGETS: frozenset[str] = frozenset({"Active", "Challenged"})
"""The only two `--to` values `set-status` accepts."""

_FLAGGING_HUMAN_REASONS: frozenset[str] = (
    FLAGGING_REASONS & HUMAN_SETTABLE_REASONS
)
"""Which human close reasons flag dependents: the sweep's own flagging set
(`derive.py:FLAGGING_REASONS`) intersected with the human-settable reasons,
so it derives from rule 2 and cannot drift: `invalidated` flags, `expired`
does not."""


def validate_close_item(
    snapshot: MaintainSnapshot, item_id: int, reason: str
) -> list[StatusChange]:
    """Validate a `close-item` command and return the changes to apply.

    Input: the snapshot, the `--item` id, the `--reason`.
    Output: the primary close change plus, for an `invalidated` close, one
    `Challenged` change per confirmed `depends_on` dependent, reduced to at
    most one change per item by `merge_and_filter`.
    Raises: `MAINTAIN-001` (item missing, carries `item_id`);
    `MAINTAIN-002` (reason not one of the 5); `MAINTAIN-003` (reason not
    human-settable); `MAINTAIN-004` (item already `Closed`, carries `item_id`).
    Side effects: none (pure). Empty list is never returned in v1 because the
    primary change always exists once the checks pass.
    """
    by_id = {item.id: item for item in snapshot.items}
    item = by_id.get(item_id)
    if item is None:
        raise MaintainItemNotFound(
            "close-item: item does not exist", item_id=item_id
        )
    if reason not in CLOSE_REASONS:
        raise CloseReasonInvalid(
            "close-item: unknown --reason", item_id=item_id, reason=reason
        )
    if reason not in HUMAN_SETTABLE_REASONS:
        raise CloseReasonMismatch(
            "close-item: reason is not human-settable",
            item_id=item_id,
            reason=reason,
        )
    if item.status == "Closed":
        raise ItemAlreadyClosed(
            "close-item: item is already Closed", item_id=item_id
        )

    primary = StatusChange(
        item_id=item.id,
        old_status=item.status,
        new_status="Closed",
        close_reason=reason,
        old_close_reason=item.close_reason,
        trigger_cause="user_closed",
        link_id=None,
    )
    fanout: list[StatusChange] = []
    if reason in _FLAGGING_HUMAN_REASONS:
        fanout = _dependent_challenges(snapshot, by_id, item_id)
    return merge_and_filter([primary, *fanout], snapshot, exempt=primary)


def _dependent_challenges(
    snapshot: MaintainSnapshot,
    by_id: dict[int, ItemState],
    target_id: int,
) -> list[StatusChange]:
    """The rule-2 fan-out: challenge each live `depends_on` dependent.

    A dependent is the **source** of a confirmed `depends_on` link whose
    **target** is the closed item. Same shape as the sweep's rule 2; the
    single-step limit and the `answered`/`expired` exclusion apply unchanged.
    """
    challenges: list[StatusChange] = []
    for link in snapshot.links:
        if link.status != "Confirmed" or link.link_type != "depends_on":
            continue
        if link.target_item_id != target_id:
            continue
        source = by_id.get(link.source_item_id)
        if source is None:
            continue
        challenges.append(
            StatusChange(
                item_id=source.id,
                old_status=source.status,
                new_status="Challenged",
                close_reason=None,
                old_close_reason=source.close_reason,
                trigger_cause="dependency_closed",
                link_id=link.id,
            )
        )
    return challenges


def validate_set_status(
    snapshot: MaintainSnapshot, item_id: int, to: str
) -> list[StatusChange]:
    """Validate a `set-status` command and return the changes to apply.

    Input: the snapshot, the `--item` id, the `--to` target status.
    Output: a single-element list with the status change, or an **empty**
    list when `--to` equals the current status (a no-op).
    Raises: `MAINTAIN-001` (item missing, carries `item_id`);
    `MAINTAIN-006` (`--to` is not `Active`/`Challenged`, or the item is
    `Closed`).
    Side effects: none (pure). The `status_origin` shield is written by the
    command's store path, never here.
    """
    by_id = {item.id: item for item in snapshot.items}
    item = by_id.get(item_id)
    if item is None:
        raise MaintainItemNotFound(
            "set-status: item does not exist", item_id=item_id
        )
    if to not in SET_STATUS_TARGETS:
        raise StatusTransitionInvalid(
            "set-status: --to must be Active or Challenged",
            item_id=item_id,
            to=to,
        )
    if item.status == "Closed":
        raise StatusTransitionInvalid(
            "set-status: item is Closed; only reversal reopens",
            item_id=item_id,
        )
    if to == item.status:
        return []

    primary = StatusChange(
        item_id=item.id,
        old_status=item.status,
        new_status=to,
        close_reason=None,
        old_close_reason=item.close_reason,
        trigger_cause="user_set_status",
        link_id=None,
    )
    return merge_and_filter([primary], snapshot, exempt=primary)


def validate_reverse_supersedes(
    snapshot: MaintainSnapshot, item_id: int, link_id: int
) -> list[StatusChange]:
    """Validate a `reverse-supersedes` command and return the change to apply.

    Input: the snapshot, the `--item` id, the `--link` id.
    Output: a single-element list restoring the item `Closed -> Active`.
    Raises: `MAINTAIN-001` (item missing, carries `item_id` and `link_id`);
    `MAINTAIN-005` (item is not `Closed`, its `close_reason` is not
    `superseded`, or the named `--link` is not a confirmed `supersedes` link
    pointing at the item — each carries `item_id` and `link_id`).
    Side effects: none (pure). The `link_reversed` marker is built by the
    command's store path, never here.
    """
    by_id = {item.id: item for item in snapshot.items}
    item = by_id.get(item_id)
    if item is None:
        raise MaintainItemNotFound(
            "reverse-supersedes: item does not exist",
            item_id=item_id,
            link_id=link_id,
        )
    if item.status != "Closed":
        raise ReversalPreconditionFailed(
            "reverse-supersedes: item is not Closed",
            item_id=item_id,
            link_id=link_id,
        )
    if item.close_reason != "superseded":
        raise ReversalPreconditionFailed(
            "reverse-supersedes: close_reason is not superseded",
            item_id=item_id,
            link_id=link_id,
        )
    if not _supersedes_targets_link(snapshot, link_id, item_id):
        raise ReversalPreconditionFailed(
            "reverse-supersedes: --link is not a confirmed supersedes "
            "link pointing at the item",
            item_id=item_id,
            link_id=link_id,
        )

    primary = StatusChange(
        item_id=item.id,
        old_status=item.status,
        new_status="Active",
        close_reason=None,
        old_close_reason="superseded",
        trigger_cause="reversal",
        link_id=link_id,
    )
    return merge_and_filter([primary], snapshot, exempt=primary)


def _supersedes_targets_link(
    snapshot: MaintainSnapshot, link_id: int, item_id: int
) -> bool:
    """True when a confirmed `supersedes` link with `link_id` targets `item_id`."""
    return any(
        link.id == link_id
        and link.link_type == "supersedes"
        and link.status == "Confirmed"
        and link.target_item_id == item_id
        for link in snapshot.links
    )


def validate_edit_item(
    snapshot: MaintainSnapshot, item_id: int, field: str, value: str
) -> list[EditChange]:
    """Validate an `edit-item` command and return the changes to apply.

    Input: the snapshot, the `--item` id, the `--field` name, the `--value`
    text. Output: a single-element list with the edit, or an **empty** list
    when `value` equals the observed value (a no-op, the `set-status` B3
    precedent).

    Under the rule-7 ADR's Option A only `rationale` (on a `Decision`) and
    `source` (on a `Finding`) are writable. `statement` and every raw table
    stay immutable.

    Raises: `MAINTAIN-001` (item missing, carries `item_id`),
    `MAINTAIN-013` (`field` is not one of the three known names) and
    `MAINTAIN-014` (the field is not writable on that item's type, which
    under Option A includes `statement`, carries `item_id` + `field`).
    Side effects: none (pure). The old value is the observed Phase-1 value,
    never invented.
    """
    by_id = {item.id: item for item in snapshot.items}
    item = by_id.get(item_id)
    if item is None:
        raise MaintainItemNotFound(
            "edit-item: item does not exist", item_id=item_id
        )
    if field not in EDIT_FIELDS:
        raise EditFieldUnknown(
            "edit-item: unknown --field", item_id=item_id, field=field
        )
    if EDITABLE.get(field) != item.type:
        raise EditTargetMismatch(
            "edit-item: field is not writable on this item type",
            item_id=item_id,
            field=field,
        )

    old_value = item.rationale if field == "rationale" else item.source
    if old_value == value:
        return []

    return [
        EditChange(
            item_id=item.id,
            field=field,
            old_value=old_value,
            new_value=value,
            trigger_cause="user_edit_item",
        )
    ]


def validate_remove_link(
    snapshot: MaintainSnapshot, link_id: int
) -> list[LinkChange]:
    """Validate a `remove-link` command and return the change to apply.

    Input: the snapshot, the `--link` id. Output: a single-element list with
    the removal (`Confirmed -> Rejected`, `trigger_cause='user_remove_link'`,
    `item_id` = the link's source). A no-op is impossible by design: a
    missing-or-not-Confirmed link is ONE failure (MAINTAIN-015), so there is
    no silent-success shape (the recorded I8 deviation, the MAINTAIN-004
    precedent).

    A reversed-but-Confirmed link is ACCEPTED (orthogonal to reversal, Gap C):
    it is still a Confirmed row, and the ledger ends with both a
    `link_reversed` and a `link_removed` row.

    Raises: `MAINTAIN-015` (no Confirmed link with that id, a Phase-1
    Confirmed-only read cannot distinguish "no such row" from "not
    Confirmed", same conflation as MAINTAIN-005, carries `link_id`).
    Side effects: none (pure). The one `links` UPDATE is the store's job,
    never here (B1/B3).
    """
    link = next(
        (
            link
            for link in snapshot.links
            if link.id == link_id and link.status == "Confirmed"
        ),
        None,
    )
    if link is None:
        raise RemoveLinkNotConfirmed(
            "remove-link: no Confirmed link with that id", link_id=link_id
        )

    return [
        LinkChange(
            link_id=link.id,
            old_status=link.status,
            new_status="Rejected",
            trigger_cause="user_remove_link",
            item_id=link.source_item_id,
        )
    ]

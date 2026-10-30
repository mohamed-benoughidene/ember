"""Write port for the maintain engine (B1/B2/B3).

`derive.py` is the pure rules; this port is the only allowed writer. The
adapter behind it owns the database driver and the transaction; the core sees
one call per write path (T2, P4).

Every human write method carries an optional `group_id` (undo step 01): one
group id = one user action's shared ledger stamp. `None` keeps the pre-013
behaviour byte for byte (the sweep, which passes nothing, stays NULL).
"""

from __future__ import annotations

from typing import Protocol

from ember.maintain.rows import EditChange, LinkChange, StatusChange, UndoResult
from ember.relate.rows import ChangeLogEntry


class MaintainStorePort(Protocol):
    def apply_status_changes(
        self, changes: list[StatusChange], group_id: int | None = None
    ) -> int:
        """One transaction, all-or-nothing; returns the number applied.

        A `rearm` change (the timestamp-scoped shield's re-arm) also returns
        `items.status_origin` to `'derived'` in the same batch UPDATE and
        appends one `status_origin` ledger row (`trigger_cause='sweep_rearm'`,
        `old_value` the observed prior origin, `link_id` the causing link)
        from the same ONE clock read. Exempt (human) changes are never
        stamped rearm.

        `group_id` stamps every ledger row of the batch with one undo group
        id (engine-undo-plan §5.1); the sweep passes nothing and its rows
        read NULL.

        Raises MAINTAIN-011 on the items UPDATE, MAINTAIN-012 on the change_log
        INSERT (both roll the batch back).
        """
        ...

    def apply_status_origin(
        self, item_id: int, origin: str, group_id: int | None = None
    ) -> None:
        """Write items.status_origin AND its field_changed='status_origin'
        change_log row in one transaction (`group_id` stamps the row, undo
        step 01). Raises MAINTAIN-011 / MAINTAIN-012.
        """
        ...

    def apply_reversal(
        self,
        change: StatusChange,
        marker: ChangeLogEntry,
        group_id: int | None = None,
    ) -> int:
        """Write the item restore, its `status` log row, AND the `link_reversed`
        marker row in ONE transaction (`group_id` stamps both rows, undo step
        01). Raises MAINTAIN-011 / MAINTAIN-012.
        """
        ...

    def apply_item_edit(
        self, change: EditChange, group_id: int | None = None
    ) -> int:
        """Write one item's rationale or source column AND its `change_log`
        row in ONE transaction (the `apply_status_origin` pattern). Returns 1.
        `group_id` stamps the row (undo step 01). Raises MAINTAIN-016 on the
        items UPDATE, MAINTAIN-012 on the change_log INSERT (both roll the
        whole write back).
        """
        ...

    def apply_remove_link(
        self, change: LinkChange, group_id: int | None = None
    ) -> int:
        """Write the ONE removal (`UPDATE links SET status='Rejected'`) AND
        its `link_removed` change_log row in ONE transaction. This method
        never INSERTs, DELETEs, or flips a row back — the one exception is
        the undo path (`apply_inverse_group`), which may restore a removed
        link to `Confirmed` as an undo of its own removal. Returns 1.
        `group_id` stamps the row (undo step 01). Raises MAINTAIN-017 on the
        links UPDATE, MAINTAIN-012 on the change_log INSERT (both roll the
        whole write back).
        """
        ...

    def apply_inverse_group(self, plan: UndoResult) -> int:
        """Write one undo or redo plan atomically (undo step 03, L2 §5.5).

        ONE transaction, ONE clock read: the `items` / `links` UPDATEs of
        `plan.changes` (a redo of a close sets `status` and `close_reason`
        in the ONE UPDATE so the migration-011 trigger sees the reason),
        then the inverse `change_log` rows and the `undo_of` / `redo_of`
        marker row, all stamped with the ONE new group id. All-or-nothing.

        The declared B2 exception lives here: an undo of the `validated`
        flag writes `items.validated`, a Capture-owned column — the only
        cross-module write, covered by a test.

        Returns the number of inverse changes applied (the marker row is
        not counted). Raises MAINTAIN-026 on any UPDATE failure and
        MAINTAIN-012 on any INSERT failure; either rolls the whole group
        back, so the ledger never gains a half-undone group.
        """
        ...

"""Write port for the maintain engine (B1/B2/B3).

`derive.py` is the pure rules; this port is the only allowed writer. The
adapter behind it owns the database driver and the transaction; the core sees
one call per write path (T2, P4).
"""

from __future__ import annotations

from typing import Protocol

from ember.maintain.rows import EditChange, LinkChange, StatusChange
from ember.relate.rows import ChangeLogEntry


class MaintainStorePort(Protocol):
    def apply_status_changes(self, changes: list[StatusChange]) -> int:
        """One transaction, all-or-nothing; returns the number applied.

        A `rearm` change (the timestamp-scoped shield's re-arm) also returns
        `items.status_origin` to `'derived'` in the same batch UPDATE and
        appends one `status_origin` ledger row (`trigger_cause='sweep_rearm'`,
        `old_value` the observed prior origin, `link_id` the causing link)
        from the same ONE clock read. Exempt (human) changes are never
        stamped rearm.

        Raises MAINTAIN-011 on the items UPDATE, MAINTAIN-012 on the change_log
        INSERT (both roll the batch back).
        """
        ...

    def apply_status_origin(self, item_id: int, origin: str) -> None:
        """Write items.status_origin AND its field_changed='status_origin'
        change_log row in one transaction. Raises MAINTAIN-011 / MAINTAIN-012.
        """
        ...

    def apply_reversal(self, change: StatusChange, marker: ChangeLogEntry) -> int:
        """Write the item restore, its `status` log row, AND the `link_reversed`
        marker row in ONE transaction. Raises MAINTAIN-011 / MAINTAIN-012.
        """
        ...

    def apply_item_edit(self, change: EditChange) -> int:
        """Write one item's rationale or source column AND its `change_log`
        row in ONE transaction (the `apply_status_origin` pattern). Returns 1.
        Raises MAINTAIN-016 on the items UPDATE, MAINTAIN-012 on the
        change_log INSERT (both roll the whole write back).
        """
        ...

    def apply_remove_link(self, change: LinkChange) -> int:
        """Write the ONE removal (`UPDATE links SET status='Rejected'`) AND
        its `link_removed` change_log row in ONE transaction. Never INSERT,
        DELETE, or flip back. Returns 1. Raises MAINTAIN-017 on the links
        UPDATE, MAINTAIN-012 on the change_log INSERT (both roll the whole
        write back).
        """
        ...

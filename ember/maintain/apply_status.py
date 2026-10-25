"""Write port for the maintain engine (B1/B2/B3).

`derive.py` is the pure rules; this port is the only allowed writer. The
adapter behind it owns the database driver and the transaction; the core sees
one call per write path (T2, P4).
"""

from __future__ import annotations

from typing import Protocol

from ember.maintain.rows import StatusChange


class MaintainStorePort(Protocol):
    def apply_status_changes(self, changes: list[StatusChange]) -> int:
        """One transaction, all-or-nothing; returns the number applied.

        Raises MAINTAIN-011 on the items UPDATE, MAINTAIN-012 on the change_log
        INSERT (both roll the batch back).
        """
        ...

    def apply_status_origin(self, item_id: int, origin: str) -> None:
        """Write items.status_origin AND its field_changed='status_origin'
        change_log row in one transaction. Raises MAINTAIN-011 / MAINTAIN-012.
        """
        ...

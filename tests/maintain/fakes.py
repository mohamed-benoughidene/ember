"""In-memory stand-ins for the maintain ports."""

from __future__ import annotations

from ember.maintain.rows import ItemState, StatusChange
from ember.relate.rows import ChangeLogEntry, Link


class FakeMaintainLookup:
    def __init__(
        self,
        items: list[ItemState] | None = None,
        links: list[Link] | None = None,
        reversed_link_ids: set[int] | None = None,
        shield_log: list[ChangeLogEntry] | None = None,
    ) -> None:
        self._items = list(items or [])
        self._links = list(links or [])
        self._reversed = set(reversed_link_ids or set())
        self._shield = list(shield_log or [])

    def list_items(self) -> list[ItemState]:
        return list(self._items)

    def list_confirmed_links(self) -> list[Link]:
        return [link for link in self._links if link.status == "Confirmed"]

    def list_reversed_link_ids(self) -> set[int]:
        return set(self._reversed)

    def list_shield_log(self) -> list[ChangeLogEntry]:
        return list(self._shield)


class FakeMaintainStore:
    """Working stand-in for `MaintainStorePort` that also records calls.

    `applied_changes` holds one entry per `apply_status_changes` call (so a
    test can assert exactly-once and inspect the exact list written).
    `origins` holds one `(item_id, origin)` tuple per `apply_status_origin`
    call. `reversals` holds one `(change, marker)` tuple per `apply_reversal`
    call. `apply_status_changes` and `apply_reversal` return the port's count.
    """

    def __init__(self) -> None:
        self.applied_changes: list[list[StatusChange]] = []
        self.origins: list[tuple[int, str]] = []
        self.reversals: list[tuple[StatusChange, ChangeLogEntry]] = []

    def apply_status_changes(self, changes: list[StatusChange]) -> int:
        self.applied_changes.append(list(changes))
        return len(changes)

    def apply_status_origin(self, item_id: int, origin: str) -> None:
        self.origins.append((item_id, origin))

    def apply_reversal(self, change: StatusChange, marker: ChangeLogEntry) -> int:
        self.reversals.append((change, marker))
        return 1

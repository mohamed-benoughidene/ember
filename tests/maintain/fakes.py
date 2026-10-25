"""In-memory stand-in for `MaintainLookupPort`."""

from __future__ import annotations

from ember.maintain.rows import ItemState
from ember.relate.rows import Link


class FakeMaintainLookup:
    def __init__(
        self,
        items: list[ItemState] | None = None,
        links: list[Link] | None = None,
        reversed_link_ids: set[int] | None = None,
    ) -> None:
        self._items = list(items or [])
        self._links = list(links or [])
        self._reversed = set(reversed_link_ids or set())

    def list_items(self) -> list[ItemState]:
        return list(self._items)

    def list_confirmed_links(self) -> list[Link]:
        return [link for link in self._links if link.status == "Confirmed"]

    def list_reversed_link_ids(self) -> set[int]:
        return set(self._reversed)

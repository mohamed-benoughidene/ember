"""In-memory stand-in for `LinkLookupPort`."""

from __future__ import annotations

from ember.relate.rows import Link, NewItem


class FakeLinkLookup:
    def __init__(
        self,
        items: list[NewItem],
        links: list[Link] | None = None,
        latest: NewItem | None = None,
    ) -> None:
        self._items = list(items)
        self._links = list(links or [])
        self._latest = latest
        self._by_id = {item.id: item for item in self._items}

    def item_exists(self, item_id: int) -> bool:
        return item_id in self._by_id

    def item_type(self, item_id: int) -> str | None:
        item = self._by_id.get(item_id)
        return item.type if item is not None else None

    def item_statement(self, item_id: int) -> str | None:
        item = self._by_id.get(item_id)
        return item.statement if item is not None else None

    def item_created_at(self, item_id: int) -> str | None:
        item = self._by_id.get(item_id)
        return item.created_at if item is not None else None

    def find_existing(
        self, source_id: int, target_id: int, link_type: str
    ) -> Link | None:
        for link in self._links:
            triple = (link.source_item_id, link.target_item_id, link.link_type)
            if triple == (source_id, target_id, link_type):
                return link
        return None

    def existing_link_types(self, source_item_id: int) -> dict[int, set[str]]:
        existing: dict[int, set[str]] = {}
        for link in self._links:
            if link.source_item_id == source_item_id:
                existing.setdefault(link.target_item_id, set()).add(link.link_type)
        return existing

    def list_other_items(self, new_item_id: int) -> list[NewItem]:
        return [item for item in self._items if item.id != new_item_id]

    def find_latest_unlinked_active(self) -> NewItem | None:
        return self._latest

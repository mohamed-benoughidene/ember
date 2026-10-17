"""Read port for items and links. The storage adapter owns the SQL."""

from __future__ import annotations

from typing import Protocol

from ember.relate.rows import Link, NewItem


class LinkLookupPort(Protocol):
    def item_exists(self, item_id: int) -> bool: ...
    def item_type(self, item_id: int) -> str | None: ...
    def item_statement(self, item_id: int) -> str | None: ...
    def item_created_at(self, item_id: int) -> str | None: ...
    def find_existing(
        self, source_id: int, target_id: int, link_type: str
    ) -> Link | None: ...
    def existing_link_types(self, source_item_id: int) -> dict[int, set[str]]:
        """Return the link types already present from this source, by target id."""
        ...

    def list_other_items(self, new_item_id: int) -> list[NewItem]:
        """Return every item except `new_item_id`, ordered by id."""
        ...

    def find_latest_unlinked_active(self) -> NewItem | None:
        """Return the newest Active item with no outgoing link, or None."""
        ...

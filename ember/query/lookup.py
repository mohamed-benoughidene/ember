"""Read port for the query engine. The storage adapter owns the SQL."""

from __future__ import annotations

from typing import Protocol

from ember.query.rows import ChangeRow, QueryItem
from ember.relate.rows import Link


class QueryLookupPort(Protocol):
    """The only way the query core reaches the database (T9).

    Every method raises `QUERY-005 ItemsReadFailed` on a read failure.
    """

    def list_items(self) -> list[QueryItem]:
        """Return every item, ordered by id ascending."""
        ...

    def list_links(self) -> list[Link]:
        """Return every link, ordered by id ascending."""
        ...

    def list_change_log(self) -> list[ChangeRow]:
        """Return every `change_log` row, ordered by id ascending."""
        ...

    def item_exists(self, item_id: int) -> bool:
        """Return whether `items` holds `item_id` (used by the gatekeeper)."""
        ...

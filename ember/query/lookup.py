"""Read port for the query engine. The storage adapter owns the SQL."""

from __future__ import annotations

from typing import Protocol

from ember.query.rows import ChangeRow, HistoryPage, QueryItem
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

    def list_change_log(
        self,
        item_id: int | None = None,
        window: HistoryPage | None = None,
    ) -> list[ChangeRow]:
        """Return `change_log` rows, filtered and bounded in SQL.

        `item_id` keeps only the rows about that item by subject or by link
        (exactly `history`'s `_belongs_to` rule); `window.limit` bounds the
        read to at most `offset + limit` rows of the NEWEST prefix, ordered
        by the same `(timestamp, id)` DESCENDING key `history()` sorts
        (Batch 8, finding 4.7 #12), so sorting and cropping the prefix in
        memory yields exactly the full-window view. `None` on either
        parameter keeps today's whole-ledger read valid for the no-argument
        callers (I10); `history()` still applies the full window itself.
        Raise `QUERY-005 ItemsReadFailed` on a read failure.
        """
        ...

    def item_exists(self, item_id: int) -> bool:
        """Return whether `items` holds `item_id` (used by the gatekeeper)."""
        ...

    def source_text_for(self, item_id: int) -> str:
        """Return the verbatim `sources.full_text` behind the item's source.

        Bridge step 02's one new read: `show-item` renders the raw source.
        Raised on failure like every other read here (`QUERY-005`).
        """
        ...

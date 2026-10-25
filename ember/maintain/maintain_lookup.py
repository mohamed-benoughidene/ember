"""Read port for the maintain sweep. The storage adapter owns the SQL."""

from __future__ import annotations

from typing import Protocol

from ember.maintain.rows import ItemState
from ember.relate.rows import Link


class MaintainLookupPort(Protocol):
    def list_items(self) -> list[ItemState]:
        """Return every item: id, type, status, close_reason, status_origin.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

    def list_confirmed_links(self) -> list[Link]:
        """Return every `links` row whose status is `Confirmed`.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

    def list_reversed_link_ids(self) -> set[int]:
        """Return the link ids carrying a `link_reversed` change_log row.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

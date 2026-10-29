"""Read port for the maintain sweep. The storage adapter owns the SQL."""

from __future__ import annotations

from typing import Protocol

from ember.maintain.rows import ItemState
from ember.relate.rows import ChangeLogEntry, Link


class MaintainLookupPort(Protocol):
    def list_items(self) -> list[ItemState]:
        """Return every item: id, type, status, close_reason, status_origin,
        plus the `rationale`/`source` authorial columns.

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

    def list_shield_log(self) -> list[ChangeLogEntry]:
        """Return the ledger slice the timestamp-scoped manual shield reads
        (L2 §13.5), in id order: the manual-clear rows (`status_origin` /
        `user_set_status` / `manual`) and the `link_confirmed` rows.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

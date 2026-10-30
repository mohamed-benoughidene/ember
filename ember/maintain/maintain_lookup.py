"""Read port for the maintain sweep. The storage adapter owns the SQL."""

from __future__ import annotations

from typing import Protocol

from ember.maintain.rows import ItemState, LedgerGroup
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

    def list_all_links(self) -> list[Link]:
        """Return every `links` row, ANY status, carrying `reversed_at`.

        Undo step 04 (the binding step-03 deviation U3-3): the undo refusal
        rule compares each grouped ledger row against the LIVE link state,
        so the snapshot needs links of any status with the `reversed_at`
        column — the Confirmed-only `list_confirmed_links` read cannot
        supply that for a removed or reversed link.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

    def has_ungrouped_rows(self) -> bool:
        """Return whether `change_log` rows WITHOUT a `group_id` exist.

        Undo step 04: the one bit the grouped read cannot see by definition
        (story 123) — the `MAINTAIN-023` message must tell the user whether
        older ledger changes are invisible to undo.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

    def list_reversed_link_ids(self) -> set[int]:
        """Return the link ids whose reversal state reads "reversed": the
        highest-id marker among `link_reversed` / `link_unreversed` is a
        `link_reversed` (undo step 03, so an undone reversal reads live).

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

    def list_shield_log(self) -> list[ChangeLogEntry]:
        """Return the ledger slice the timestamp-scoped manual shield reads
        (L2 §13.5), in id order: the manual-clear rows (`status_origin` /
        `manual` with cause `user_set_status` OR `user_redo`, undo step 03)
        and the `link_confirmed` rows.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

    def list_grouped_ledger(self) -> list[LedgerGroup]:
        """Return every undo group: only ledger rows with a non-NULL
        `group_id`, wrapped per group in id, then row-id, order (undo step
        02, L2 §5.1). Rows from before migration 013 have no group id and
        are invisible here by definition (story 123) — the undo core is
        told whether such rows exist separately, so its refusal message can
        say so.

        Raise `MAINTAIN-010 ItemsReadFailed` on a read failure.
        """
        ...

"""In-memory stand-ins for the maintain ports."""

from __future__ import annotations

from ember.maintain.close_proposer import CloseProposalResponse, StaleCandidate
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

    def apply_status_changes(
        self, changes: list[StatusChange], group_id: int | None = None
    ) -> int:
        self.applied_changes.append(list(changes))
        return len(changes)

    def apply_status_origin(
        self, item_id: int, origin: str, group_id: int | None = None
    ) -> None:
        self.origins.append((item_id, origin))

    def apply_reversal(
        self,
        change: StatusChange,
        marker: ChangeLogEntry,
        group_id: int | None = None,
    ) -> int:
        self.reversals.append((change, marker))
        return 1


class FakeCloseProposer:
    """Canned close AI. Each call returns the next response, or raises it.

    `calls` records one `StaleCandidate` per `propose_close` call, so a test
    can assert exactly-once per shortlist entry and that an abort stops the
    calls early.
    """

    def __init__(
        self, outcomes: list[CloseProposalResponse | Exception]
    ) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[StaleCandidate] = []

    def propose_close(self, candidate: StaleCandidate) -> CloseProposalResponse:
        self.calls.append(candidate)
        if not self._outcomes:
            raise AssertionError("FakeCloseProposer ran out of outcomes")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class AiResponseStoreStub:
    """`ai_responses` stand-in that records saves, or always fails.

    With `fail=None` every save is recorded as an `(item_id, raw_response)`
    pair. With `fail` set, `save` raises that exception once configured,
    which the engine maps to `MAINTAIN-021 CloseAiStoreFailed`.
    """

    def __init__(self, fail: Exception | None = None) -> None:
        self.saved: list[tuple[int | None, str]] = []
        self._fail = fail

    def save(
        self,
        *,
        item_id: int | None = None,
        source_id: int | None = None,
        raw_response: str,
    ) -> None:
        if self._fail is not None:
            raise self._fail
        self.saved.append((item_id, raw_response))

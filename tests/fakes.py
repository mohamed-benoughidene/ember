"""In-memory stand-ins for the ports (Rule T3: fakes over mocks)."""

from __future__ import annotations

from ember.capture.item_proposal import ContextItem, ItemProposal
from ember.capture.source_storage import SourceRecord


class FakeItemProposer:
    """Canned AI. Each call returns the next outcome, or raises it if it is one."""

    def __init__(self, outcomes: list[list[ItemProposal] | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, list[ContextItem]]] = []

    def propose(self, raw_text: str, context: list[ContextItem]) -> list[ItemProposal]:
        self.calls.append((raw_text, context))
        if not self._outcomes:
            raise AssertionError("FakeItemProposer ran out of outcomes")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeItemContext:
    """In-memory item reader. Records the limits it was asked for."""

    def __init__(self, items: list[ContextItem]) -> None:
        self.items = items
        self.limits: list[int] = []

    def recent_items(self, limit: int) -> list[ContextItem]:
        self.limits.append(limit)
        return self.items[:limit]


class FakeSourceStore:
    def __init__(self) -> None:
        self.rows: dict[str, SourceRecord] = {}
        self._next_id = 1

    def find_by_hash(self, content_hash: str) -> SourceRecord | None:
        return self.rows.get(content_hash)

    def insert_source(self, *, title: str, full_text: str, content_hash: str) -> int:
        source_id = self._next_id
        self._next_id += 1
        self.rows[content_hash] = SourceRecord(source_id, full_text, content_hash)
        return source_id

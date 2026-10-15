"""In-memory stand-ins for the ports (Rule T3: fakes over mocks)."""

from __future__ import annotations

from ember.capture.errors import UserAbort
from ember.capture.item_gatekeeper import ValidatedItem
from ember.capture.item_proposal import ContextItem, ProposalResponse
from ember.capture.source_storage import SourceRecord


class FakeItemProposer:
    """Canned AI. Each call returns the next response, or raises it if it is one."""

    def __init__(self, outcomes: list[ProposalResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, list[ContextItem]]] = []

    def propose(self, raw_text: str, context: list[ContextItem]) -> ProposalResponse:
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


class FakeConfirm:
    """Scripted user. Answers in order; runs out -> UserAbort (STDIN closed)."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []
        self.written: list[str] = []

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            raise UserAbort("input ended")
        return self._answers.pop(0)

    def write(self, text: str) -> None:
        self.written.append(text)


class FakeItemCommit:
    """Records every `items` and `change_log` write."""

    def __init__(self) -> None:
        self.items: list[tuple[ValidatedItem, bool | None]] = []
        self.created: list[ValidatedItem] = []
        self.rejected: list[ValidatedItem] = []

    def insert_item(self, item: ValidatedItem, *, validated: bool | None) -> None:
        self.items.append((item, validated))

    def log_created(self, item: ValidatedItem) -> None:
        self.created.append(item)

    def log_rejected(self, item: ValidatedItem) -> None:
        self.rejected.append(item)

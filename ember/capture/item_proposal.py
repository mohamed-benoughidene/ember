"""Phase 2 core: turn raw text into AI-proposed typed items.

Pure logic. The AI and the item table sit behind ports, so the engine core
never imports a provider SDK or a database driver.

The AI answer is untrusted outside data. Rule I9 says check it at the boundary,
so `parse_proposals` runs there (the adapter calls it) and core only ever sees
checked `ItemProposal` objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol

from pydantic import BaseModel, Field, ValidationError

from ember.capture.errors import AiError, AiSchemaError, ContextModeInvalid

CONTEXT_WINDOW = 50

SYSTEM_PROMPT = (
    "You turn one raw project note into typed items. "
    "Pick each item's type from exactly these four: "
    "Decision, Assumption, Finding, Question. "
    "Return one item for each thing worth keeping, as a JSON list. "
    "Each item has four keys: "
    "type (one of the four), "
    "statement (the item in your own words), "
    "source_quote (an exact substring copied from the raw note), "
    "confidence (your own score from 0.0 to 1.0). "
    "Return an empty list when the note holds nothing worth keeping."
)


class ItemType(str, Enum):
    """The only 4 item types V1 allows (L1 section 1)."""

    DECISION = "Decision"
    ASSUMPTION = "Assumption"
    FINDING = "Finding"
    QUESTION = "Question"


class ContextMode(str, Enum):
    """Whether the AI sees recent items. B = yes, A = no. Default B."""

    A = "A"
    B = "B"


class ContextItem(BaseModel):
    """Read-only view of one existing item, handed to the AI as context."""

    id: int
    type: ItemType
    statement: str


class ItemProposal(BaseModel):
    """One AI-proposed typed item, after boundary checks pass."""

    type: ItemType
    statement: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class DroppedProposal:
    """A proposal the checks threw away, with the rule it failed."""

    rule: str
    payload: object


@dataclass(frozen=True)
class ProposalBatch:
    """Surviving proposals plus the drops, so the edge can log them."""

    proposals: list[ItemProposal]
    dropped: list[DroppedProposal]


class ItemProposerPort(Protocol):
    """AI boundary. The adapter owns the provider SDK and request format."""

    def propose(self, raw_text: str, context: list[ContextItem]) -> list[ItemProposal]:
        """Return checked proposals for `raw_text`.

        The adapter builds the provider request from `raw_text`, `context` and
        `SYSTEM_PROMPT`, then checks the raw answer with `parse_proposals`
        (rule I9: outside data is checked at the boundary).

        Raise `AiCallError` when the provider call fails, and
        `AiSchemaError` when the answer cannot be read. Both are retried.
        """
        ...


class ItemContextPort(Protocol):
    """Read boundary for existing items. Adapter owns SQL."""

    def recent_items(self, limit: int) -> list[ContextItem]:
        """Return the newest items first, at most `limit` of them."""
        ...


def read_context_mode(env: Mapping[str, str]) -> ContextMode:
    """Read `EMBER_CAPTURE_CONTEXT_MODE`. Default `B`. Fail fast on junk."""
    raw = env.get("EMBER_CAPTURE_CONTEXT_MODE", ContextMode.B.value)
    try:
        return ContextMode(raw.strip().upper())
    except ValueError as exc:
        raise ContextModeInvalid("invalid context mode", value=raw) from exc


def build_context(
    reader: ItemContextPort,
    mode: ContextMode,
) -> list[ContextItem]:
    """Mode A sends no context. Mode B sends the newest `CONTEXT_WINDOW` items."""
    if mode is ContextMode.A:
        return []
    return reader.recent_items(CONTEXT_WINDOW)


def parse_proposals(ai_response: str, raw_text: str) -> ProposalBatch:
    """Check one raw AI answer at the boundary.

    The whole answer must be a JSON list; anything else is a schema failure and
    is retried. Each entry is checked alone, so one bad entry is dropped with a
    reason instead of sinking the whole answer.
    """
    entries = _load_entries(ai_response)
    proposals: list[ItemProposal] = []
    dropped: list[DroppedProposal] = []
    for entry in entries:
        proposal, rule = _check_entry(entry, raw_text)
        if proposal is not None:
            proposals.append(proposal)
        else:
            dropped.append(DroppedProposal(rule=rule, payload=entry))
    return ProposalBatch(proposals=proposals, dropped=dropped)


def propose_items(
    proposer: ItemProposerPort,
    *,
    raw_text: str,
    context: list[ContextItem],
) -> list[ItemProposal]:
    """Ask the AI for proposals. One retry, no wait (plan section 5).

    The second call is not wrapped, so its failure reaches the caller.
    """
    try:
        return proposer.propose(raw_text, context)
    except AiError:
        return proposer.propose(raw_text, context)


def _load_entries(ai_response: str) -> list[object]:
    try:
        data = json.loads(ai_response)
    except json.JSONDecodeError as exc:
        raise AiSchemaError("ai response not json") from exc
    if not isinstance(data, list):
        raise AiSchemaError("ai response not a list")
    return data


def _check_entry(entry: object, raw_text: str) -> tuple[ItemProposal | None, str]:
    if not isinstance(entry, dict):
        return None, "shape"
    try:
        proposal = ItemProposal.model_validate(entry)
    except ValidationError as exc:
        return None, _rule_for(exc)
    if proposal.source_quote not in raw_text:
        return None, "quote"
    return proposal, ""


def _rule_for(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = first.get("loc") or ()
    field = str(location[0]) if location else ""
    if field == "source_quote":
        return "quote"
    if field in {"type", "statement", "confidence"}:
        return field
    return "shape"

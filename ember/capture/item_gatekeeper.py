"""Phase 3 core: validate proposals, generate id/timestamp/Active status.

Pure logic. The stored source text and the existing item statements sit behind
ports, so the engine core never imports a database driver. The near-duplicate
scan uses plain text similarity, no embedder (Engine B owns vectors), and is a
warning only; it never blocks a proposal (L2 section 3, Phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Protocol

from ember.capture.errors import (
    ItemNotFound,
    ItemSourceMissing,
    NotAnAssumption,
)
from ember.capture.item_proposal import ItemProposal, ItemType

NEAR_DUP_THRESHOLD = 0.85
STATUS_ACTIVE = "Active"
_ITEM_TYPES = frozenset(item.value for item in ItemType)


@dataclass(frozen=True)
class ProposalDraft:
    """One proposal about to be checked.

    `type` is a plain string on purpose: the Phase 4 edit path feeds raw user
    input here, so check #1 must be able to fail.
    """

    type: str
    statement: str
    source_quote: str
    confidence: float
    metadata: str | None = None


@dataclass(frozen=True)
class NearDupWarning:
    """A similar existing item. Warning only, never a block."""

    matching_item_id: int
    similarity: float


@dataclass(frozen=True)
class ExistingItem:
    """One stored item's id and statement, for the near-duplicate scan."""

    item_id: int
    statement: str


@dataclass(frozen=True)
class StoredItem:
    """One row read back from `items`, for the human flag change."""

    id: int
    type: str
    validated: bool | None


@dataclass(frozen=True)
class ValidatedItem:
    """Phase 3 output, ready for the Phase 4 confirm loop."""

    id: int
    type: str
    statement: str
    source_quote: str
    confidence: float
    source_id: int
    created_at: str
    status: str
    near_dup_warning: NearDupWarning | None
    metadata: str | None = None


@dataclass(frozen=True)
class RejectedProposal:
    """A proposal a check threw away, with the rule it failed."""

    rule: str


@dataclass(frozen=True)
class GatekeeperResult:
    """Validated items plus the rejects, so the edge can log the reasons."""

    validated: list[ValidatedItem]
    rejected: list[RejectedProposal]


@dataclass(frozen=True)
class GatekeeperRun:
    """Read-once values and injected edges for one Phase 3 pass.

    `source_text` and `existing` are read once by the caller. `next_id` and
    `clock` are the injected id source and clock (rule T2).
    """

    source_id: int
    source_text: str
    existing: list[ExistingItem]
    next_id: Callable[[], int]
    clock: Callable[[], str]


class SourceTextPort(Protocol):
    """Read boundary for stored source text (check #3)."""

    def full_text_for(self, source_id: int) -> str | None:
        """Return `sources.full_text` for `source_id`, or None."""
        ...


def _to_draft(proposal: ItemProposal) -> ProposalDraft:
    """Turn a checked Phase 2 proposal into a Phase 3 draft."""
    return ProposalDraft(
        type=proposal.type.value,
        statement=proposal.statement,
        source_quote=proposal.source_quote,
        confidence=proposal.confidence,
        metadata=proposal.metadata,
    )


def is_allowed_type(value: str) -> bool:
    """Check #1: type is one of the 4 V1 types."""
    return value in _ITEM_TYPES


def _find_near_dup(
    statement: str, existing: list[ExistingItem]
) -> NearDupWarning | None:
    """Check #4: the closest existing statement above the threshold, or None."""
    best: NearDupWarning | None = None
    for item in existing:
        score = SequenceMatcher(None, statement, item.statement).ratio()
        if score > NEAR_DUP_THRESHOLD and (best is None or score > best.similarity):
            best = NearDupWarning(matching_item_id=item.item_id, similarity=score)
    return best


def load_source_text(sources: SourceTextPort, source_id: int) -> str:
    """Read the stored source text, or fail fast when the id is unknown.

    Raise `ItemSourceMissing` (CAPTURE-012) when no row has this id.
    """
    text = sources.full_text_for(source_id)
    if text is None:
        raise ItemSourceMissing("source not found", source_id=source_id)
    return text


def validate_set_validated(item: StoredItem | None, item_id: int) -> StoredItem:
    """Check the `validated` flag change is allowed, and return the item.

    Raise `ItemNotFound` (CAPTURE-015) when no row has `item_id`, and
    `NotAnAssumption` (CAPTURE-016) when the item is not an Assumption:
    only Assumptions carry the flag (spec 3.5, L1 section 3 `set_validated`).
    """
    if item is None:
        raise ItemNotFound("item not found", item_id=item_id)
    if item.type != ItemType.ASSUMPTION.value:
        raise NotAnAssumption("validated flag is Assumption-only", item_id=item_id)
    return item


def validate_add_item(
    draft: ProposalDraft,
    run: GatekeeperRun,
) -> ValidatedItem | RejectedProposal:
    """Run the 4 gatekeeper checks on one draft (L2 section 3, Phase 3).

    Checks: type, non-empty statement, quote substring of the stored source,
    near-duplicate warning. A near-duplicate still validates; it only carries
    a warning. On success the item gets a generated id, timestamp and
    `Active` status.
    """
    if not is_allowed_type(draft.type):
        return RejectedProposal(rule="type")
    if not draft.statement.strip():
        return RejectedProposal(rule="statement")
    if draft.source_quote not in run.source_text:
        return RejectedProposal(rule="quote")
    return ValidatedItem(
        id=run.next_id(),
        type=draft.type,
        statement=draft.statement,
        source_quote=draft.source_quote,
        confidence=draft.confidence,
        source_id=run.source_id,
        created_at=run.clock(),
        status=STATUS_ACTIVE,
        near_dup_warning=_find_near_dup(draft.statement, run.existing),
        metadata=draft.metadata,
    )


def validate_proposals(
    proposals: list[ItemProposal],
    run: GatekeeperRun,
) -> GatekeeperResult:
    """Phase 3 loop: validate every proposal, keep the good ones."""
    validated: list[ValidatedItem] = []
    rejected: list[RejectedProposal] = []
    for proposal in proposals:
        outcome = validate_add_item(_to_draft(proposal), run)
        if isinstance(outcome, RejectedProposal):
            rejected.append(outcome)
        else:
            validated.append(outcome)
    return GatekeeperResult(validated=validated, rejected=rejected)

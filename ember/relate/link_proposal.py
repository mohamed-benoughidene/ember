"""Phase 3 core: ask the AI to propose typed links from one new item to candidates."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ValidationError

from ember.relate.errors import (
    AiCallFailed,
    AiResponseSchemaInvalid,
    ProposalSourceMismatch,
    TargetNotInCandidates,
)
from ember.relate.rows import NewItem

SYSTEM_PROMPT = (
    "You propose typed links from one new item to a short list of candidate items. "
    "Pick every link's type from exactly these five: "
    "supports, contradicts, depends_on, supersedes, answers. "
    "Follow these type-compatibility rules: "
    "(1) a Finding can support or contradict an Assumption, a Decision, or another Finding; "
    "(2) a Decision or an Assumption can depend_on another item; "
    "(3) a Decision or a Finding can answer a Question; "
    "(4) only a Question can supersede a Question, and supersedes is the only "
    "type allowed between two items of the same type. "
    "Follow these directionality rules: "
    "supports never comes from an Assumption or a Decision, use depends_on instead; "
    "contradicts only ever comes from a Finding. "
    "Drop any candidate that does not fit a rule. Never invent a link type "
    "outside the five. "
    "Return strict JSON: "
    '{"proposals": [{"target_item_id": <int>, '
    '"link_type": <one of the five>, '
    '"rationale": <short string or null>}]}'
)


class LinkProposal(BaseModel):
    """One AI-proposed link from the new item to a candidate, after boundary checks."""

    target_item_id: int
    link_type: str
    rationale: str | None = None
    source_item_id: int | None = None


class LinkProposalResponse(BaseModel):
    """One AI call's raw answer plus the proposals checked from it."""

    raw_response: str
    proposals: list[LinkProposal]


class LinkProposerPort(Protocol):
    """AI boundary. The adapter owns the provider SDK and request format."""

    def propose_links(
        self, new_item: NewItem, candidates: list[NewItem]
    ) -> LinkProposalResponse:
        """Return the raw provider answer and the proposals checked from it."""
        ...


def parse_proposals(ai_response: str) -> list[LinkProposal]:
    """Boundary parser. Raises AiResponseSchemaInvalid (RELATE-033) on the FIRST bad shape."""
    try:
        data = json.loads(_without_fence(ai_response))
    except json.JSONDecodeError as exc:
        raise AiResponseSchemaInvalid("ai response not json") from exc

    if isinstance(data, dict):
        entries = data.get("proposals")
        if not isinstance(entries, list):
            raise AiResponseSchemaInvalid("ai response missing proposals list")
    elif isinstance(data, list):
        entries = data
    else:
        raise AiResponseSchemaInvalid("ai response not object or list")

    proposals: list[LinkProposal] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise AiResponseSchemaInvalid("proposal entry not an object")
        try:
            proposals.append(LinkProposal.model_validate(entry))
        except ValidationError as exc:
            raise AiResponseSchemaInvalid("proposal entry failed schema") from exc
    return proposals


def propose_links_with_retry(
    proposer: LinkProposerPort,
    *,
    new_item: NewItem,
    candidates: list[NewItem],
) -> LinkProposalResponse:
    """Call the port; on AiCallFailed retry ONCE; the second failure propagates.

    AiResponseSchemaInvalid is NOT caught (no retry, RELATE-033).
    """
    try:
        return proposer.propose_links(new_item, candidates)
    except AiCallFailed:
        return proposer.propose_links(new_item, candidates)


def validate_proposals(
    proposals: list[LinkProposal],
    *,
    candidates: list[NewItem],
    new_item: NewItem,
) -> list[LinkProposal]:
    """Semantic checks after a successful call.

    Raises TargetNotInCandidates (RELATE-024) when a target is not a candidate,
    and ProposalSourceMismatch (RELATE-025) when a source is set but not the new
    item. Returns the same list on success.
    """
    candidate_ids = {candidate.id for candidate in candidates}
    for proposal in proposals:
        if proposal.target_item_id not in candidate_ids:
            raise TargetNotInCandidates(
                "proposal target is not a candidate",
                target_item_id=proposal.target_item_id,
            )
        if (
            proposal.source_item_id is not None
            and proposal.source_item_id != new_item.id
        ):
            raise ProposalSourceMismatch(
                "proposal source does not match the new item",
                source_item_id=proposal.source_item_id,
                new_item_id=new_item.id,
            )
    return proposals


def _without_fence(text: str) -> str:
    """Drop a Markdown code fence, which models often wrap the answer in."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()

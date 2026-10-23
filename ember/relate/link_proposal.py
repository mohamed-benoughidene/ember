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
    "You propose typed links from one new item to a list of candidate items. "
    "Use ONLY these five link types: supports, contradicts, depends_on, "
    "supersedes, answers. "
    "Allowed pairs (source type -> target type : link types): "
    "Finding -> Assumption, Decision or Finding : supports or contradicts; "
    "Decision or Assumption -> Decision, Assumption or Finding : depends_on; "
    "Decision or Finding -> Question : answers; "
    "same type only (Decision -> Decision, Assumption -> Assumption, "
    "Finding -> Finding, Question -> Question) : supersedes. "
    "Direction is fixed: supports and contradicts only ever come from a "
    "Finding; depends_on only ever comes from a Decision or an Assumption. "
    "For every candidate whose type pair fits one of those rules, return one "
    "proposal; drop a candidate that fits no rule. "
    "Return ONLY a JSON object, with no Markdown code fence and no text before "
    "or after it: "
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
    payload = _json_payload(ai_response)
    if payload == "":
        raise AiResponseSchemaInvalid("ai response not json")
    data = json.loads(payload)

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


def _json_payload(text: str) -> str:
    """Return the JSON substring of `text`, or "" when none is present.

    Handles: a bare JSON value; a whole-string Markdown fence; a fence plus
    trailing/leading prose; the first balanced `{...}` or `[...]` found.
    """
    stripped = text.strip()
    if _is_json(stripped):
        return stripped
    unfenced = _without_fence(stripped)
    if _is_json(unfenced):
        return unfenced
    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        while start != -1:
            end = _matching_end(stripped, start, opener, closer)
            if end != -1:
                candidate = stripped[start : end + 1]
                if _is_json(candidate):
                    return candidate
            start = stripped.find(opener, start + 1)
    return ""


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def _matching_end(text: str, start: int, opener: str, closer: str) -> int:
    """Return the index of the closer that balances `opener` at `start`, or -1.

    Skips characters inside JSON strings (honouring backslash escapes).
    """
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1

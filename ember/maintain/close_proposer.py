"""Maintain Phase 5 core: the stale shortlist and the close-proposal pieces.

Pure (T1): `stale_close_candidates` and `parse_close_proposal` never touch
I/O and `now` is injected. The provider SDK hides behind `CloseProposerPort`
(B3/B4): the adapter in `ember/adapters/llm.py` owns the SDK, the wire format
and the boundary check. One AI call per candidate, capped at
`MAX_CLOSE_PROPOSALS`, and an empty shortlist means zero calls and zero keys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel

from ember.maintain.errors import CloseAiCallFailed, CloseAiSchemaInvalid
from ember.maintain.human_actions import HUMAN_SETTABLE_REASONS
from ember.maintain.rows import MaintainSnapshot
from ember.relate.rows import Link

STALE_DAYS = 30
MAX_CLOSE_PROPOSALS = 10

PROMPT = "[y]es / [n]o / [q]uit"

# The pinned prompt, word-for-word (step plan 07 §2, L2 §14.3). No Markdown
# fence, one strict JSON object, decline allowed via close=false.
SYSTEM_PROMPT = "\n".join(
    [
        "You judge whether one stale Question from a project-knowledge graph "
        "can be retired.",
        "You see the question and the confirmation date of the link that "
        "answered it.",
        'Propose a close only when the question is clearly settled. Use reason',
        '"invalidated" when the question\'s premise is wrong or was disproven. '
        "Use reason",
        '"expired" when the answer is old and the question no longer matters.',
        "Return close=false when the question may still be open.",
        "Return ONLY a JSON object, no Markdown fence and no text before or "
        "after it:",
        '{"close": <true|false>, "reason": "<invalidated|expired>",'
        ' "confidence": <0.0-1.0>, "rationale": <short string or null>}',
    ]
)


class StaleCandidate(BaseModel):
    """The display and prompt slice of one shortlist entry."""

    item_id: int
    item_type: str
    statement: str | None
    newest_answers_link_id: int
    answered_by_item_id: int
    newest_answer_created_at: str


class StaleShortlist(BaseModel):
    """The pre-filter output (I4: a named object, never a bare list).

    `candidates` holds at most `MAX_CLOSE_PROPOSALS` entries by `item_id`
    ascending, and `truncated` is True when more existed and were dropped.
    """

    candidates: list[StaleCandidate]
    truncated: bool = False


class CloseProposal(BaseModel):
    """One accepted proposal after the boundary check. `reason` is bounded to
    `HUMAN_SETTABLE_REASONS` (D3: one frozenset, shared with the validator the
    write path uses), so the AI can never propose a reason the close path
    would refuse."""

    reason: str
    confidence: float
    rationale: str | None = None


class CloseProposalResponse(BaseModel):
    """One AI call's raw answer plus the proposal checked from it. A
    `proposal` of None means the model declined to propose (close=false)."""

    raw_response: str
    proposal: CloseProposal | None


class CloseProposerPort(Protocol):
    """AI boundary. The adapter owns the provider SDK and request format."""

    def propose_close(self, candidate: StaleCandidate) -> CloseProposalResponse:
        """Return the raw provider answer and the proposal checked from it.

        Raise `MAINTAIN-018 CloseAiCallFailed` on a call failure and
        `MAINTAIN-019 CloseAiSchemaInvalid` on an unreadable answer (the raw
        answer is checked at this boundary, rule I9).
        """
        ...


class ConfirmPort(Protocol):
    """User I/O boundary for the maintain proposal loop (the third sibling
    of capture's and relate's `ConfirmPort`)."""

    def ask(self, prompt: str) -> str:
        """Show `prompt`, return the raw answer. The edge raises
        `MAINTAIN-022 UserAbort` when input ends (STDIN closed)."""
        ...

    def write(self, text: str) -> None:
        """Show one line to the user."""
        ...


@dataclass(frozen=True)
class ProposalOutcome:
    """Phase 5 output: the outcome line's five fields (I4). `proposed` counts
    AI proposals made. `accepted` / `rejected` are the `y`/`n` answers, and a
    decline is proven by `stale - proposed`."""

    stale: int
    proposed: int
    accepted: int
    rejected: int
    aborted: bool = False


def stale_close_candidates(
    snapshot: MaintainSnapshot, *, now: datetime
) -> StaleShortlist:
    """Name the stale candidates (the ONE pre-filter rule, L2 §14.2).

    A candidate is an item that is `type == "Question"`, `status == "Active"`,
    and whose newest Confirmed `answers` link (by `links.created_at`, higher
    link id breaking exact ties) is confirmed at least `STALE_DAYS` before
    `now` (boundary inclusive). Fail-closed totality: a `created_at` that
    cannot be parsed (or parses naive) means not a candidate, never raises.
    The output takes the first `MAX_CLOSE_PROPOSALS` by `item_id` ascending
    and sets `truncated` when it had to drop any.
    """
    by_id = {item.id: item for item in snapshot.items}
    newest: dict[int, tuple[datetime, int, Link]] = {}
    for link in snapshot.links:
        if link.status != "Confirmed" or link.link_type != "answers":
            continue
        created = _confirmed_at(link)
        if created is None:
            continue
        current = newest.get(link.target_item_id)
        if current is None or (created, link.id) > (current[0], current[1]):
            newest[link.target_item_id] = (created, link.id, link)
    candidates: list[StaleCandidate] = []
    for target_id in sorted(newest):
        item = by_id.get(target_id)
        if item is None or item.type != "Question" or item.status != "Active":
            continue
        created, _, link = newest[target_id]
        if now - created < timedelta(days=STALE_DAYS):
            continue
        if link.id is None:  # only possible in a synthetic snapshot: fail closed
            continue
        candidates.append(
            StaleCandidate(
                item_id=item.id,
                item_type=item.type,
                statement=item.statement,
                newest_answers_link_id=link.id,
                answered_by_item_id=link.source_item_id,
                newest_answer_created_at=link.created_at,
            )
        )
    truncated = len(candidates) > MAX_CLOSE_PROPOSALS
    return StaleShortlist(
        candidates=candidates[:MAX_CLOSE_PROPOSALS], truncated=truncated
    )


def parse_close_proposal(ai_response: str) -> CloseProposal | None:
    """Check one raw AI answer at the boundary (I9).

    Returns None when the model declines (`close` false, other keys ignored).
    Every rule deviation raises `MAINTAIN-019 CloseAiSchemaInvalid`: the whole
    answer must be a JSON object, `close` boolean, and a `true` close requires
    `reason` in `HUMAN_SETTABLE_REASONS`, `confidence` a float in
    [0.0, 1.0], and `rationale` a string or null.
    """
    try:
        data = json.loads(_without_fence(ai_response))
    except json.JSONDecodeError as exc:
        raise CloseAiSchemaInvalid("ai response not json") from exc
    if not isinstance(data, dict):
        raise CloseAiSchemaInvalid("ai response not object")
    close = data.get("close")
    if not isinstance(close, bool):
        raise CloseAiSchemaInvalid("close not boolean")
    if close is False:
        return None
    reason = data.get("reason")
    if reason not in HUMAN_SETTABLE_REASONS:
        raise CloseAiSchemaInvalid("reason not human settable")
    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise CloseAiSchemaInvalid("confidence not a number")
    if not 0.0 <= float(confidence) <= 1.0:
        raise CloseAiSchemaInvalid("confidence out of range")
    rationale = data.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        raise CloseAiSchemaInvalid("rationale not string or null")
    return CloseProposal(
        reason=reason, confidence=float(confidence), rationale=rationale
    )


def propose_close_with_retry(
    proposer: CloseProposerPort, *, candidate: StaleCandidate
) -> CloseProposalResponse:
    """Call the port and retry ONCE on `MAINTAIN-018` or `MAINTAIN-019`. The
    second failure propagates. Both failure kinds are retried (the capture
    `propose_items` shape), deliberately unlike relate's schema-no-retry:
    the ticket's pinned policy retries an empty answer too.
    """
    try:
        return proposer.propose_close(candidate)
    except (CloseAiCallFailed, CloseAiSchemaInvalid):
        return proposer.propose_close(candidate)


def format_proposal_block(
    candidate: StaleCandidate,
    proposal: CloseProposal | None,
    *,
    index: int,
    total: int,
) -> list[str]:
    """The confirmation block for one shortlist entry (exact bytes pinned in
    step plan 07 §2/§6). A decline prints the header plus `no close proposed`
    and never prompts."""
    statement = candidate.statement if candidate.statement is not None else ""
    lines = [
        f"Proposal {index}/{total}: item {candidate.item_id}"
        f" [{candidate.item_type}] {statement}",
        f"  newest answers link {candidate.newest_answers_link_id},"
        f" confirmed {candidate.newest_answer_created_at}",
    ]
    if proposal is None:
        lines.append("  no close proposed")
    else:
        lines.append(
            f"  reason: {proposal.reason}, confidence {proposal.confidence}"
        )
        rationale = (
            proposal.rationale if proposal.rationale is not None else "-"
        )
        lines.append(f"  rationale: {rationale}")
    return lines


def _confirmed_at(link: Link) -> datetime | None:
    """Parse `links.created_at` (UTC `isoformat()` with `+00:00` in every
    production row). Malformed or naive -> None: fail closed, never raises
    (the step-06 totality precedent)."""
    try:
        parsed = datetime.fromisoformat(link.created_at)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _without_fence(text: str) -> str:
    """Drop a Markdown code fence, which models often wrap the answer in
    (the `item_proposal.py` precedent, copied: private there)."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()

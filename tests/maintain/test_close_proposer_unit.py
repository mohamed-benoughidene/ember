"""Unit tests for the stale pre-filter, the boundary parser, and the retry.

Pure (T1/T7): fake-lookup snapshots plus recorded answer fixtures, fixed
`now`s, no DB, no AI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ember.maintain.close_proposer import (
    STALE_DAYS,
    StaleCandidate,
    CloseProposal,
    CloseProposalResponse,
    format_proposal_block,
    parse_close_proposal,
    propose_close_with_retry,
    stale_close_candidates,
)
from ember.maintain.errors import CloseAiCallFailed, CloseAiSchemaInvalid
from ember.maintain.rows import ItemState, MaintainSnapshot
from ember.relate.rows import Link
from tests.maintain.fakes import FakeCloseProposer

NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)
OLD = "2026-01-01T00:00:00+00:00"  # 31 days before NOW: stale
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "maintain"


def _item(
    item_id: int,
    *,
    item_type: str = "Question",
    status: str = "Active",
    statement: str | None = "a question",
) -> ItemState:
    return ItemState(
        id=item_id,
        type=item_type,
        status=status,
        close_reason=None,
        status_origin="derived",
        statement=statement,
    )


def _link(
    link_id: int,
    *,
    source: int = 4,
    target: int = 7,
    link_type: str = "answers",
    status: str = "Confirmed",
    created_at: str = OLD,
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source,
        target_item_id=target,
        link_type=link_type,
        status=status,
        created_at=created_at,
    )


def _snapshot(
    items: list[ItemState] | None = None,
    links: list[Link] | None = None,
) -> MaintainSnapshot:
    return MaintainSnapshot(
        items=items or [], links=links or [], reversed_link_ids=set()
    )


def _candidate() -> StaleCandidate:
    return StaleCandidate(
        item_id=7,
        item_type="Question",
        statement="should we cache tokens?",
        newest_answers_link_id=11,
        answered_by_item_id=4,
        newest_answer_created_at=OLD,
    )


def _proposal_response(
    reason: str = "expired", confidence: float = 0.8
) -> CloseProposalResponse:
    return CloseProposalResponse(
        raw_response="RAW-PROPOSAL",
        proposal=CloseProposal(
            reason=reason, confidence=confidence, rationale="settled"
        ),
    )


def _fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- the pre-filter -------------------------------------------------------


def test_prefilter_names_active_question_with_old_answers_link() -> None:
    snapshot = _snapshot(
        [_item(7, statement="should we cache tokens?")],
        [_link(11, target=7)],
    )

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert shortlist.truncated is False
    assert [candidate.item_id for candidate in shortlist.candidates] == [7]
    candidate = shortlist.candidates[0]
    assert candidate.item_type == "Question"
    assert candidate.newest_answers_link_id == 11
    assert candidate.answered_by_item_id == 4
    assert candidate.newest_answer_created_at == OLD


def test_prefilter_ignores_challenged_and_closed_questions() -> None:
    snapshot = _snapshot(
        [
            _item(7),
            _item(8, status="Challenged"),
            _item(9, status="Closed"),
        ],
        [_link(11, target=7), _link(12, target=8), _link(13, target=9)],
    )

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert [candidate.item_id for candidate in shortlist.candidates] == [7]


def test_prefilter_ignores_answers_to_non_question() -> None:
    snapshot = _snapshot(
        [_item(7, item_type="Finding"), _item(8, item_type="Decision")],
        [_link(11, target=7), _link(12, target=8)],
    )

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert shortlist.candidates == []


def test_prefilter_uses_newest_answers_link_when_two_exist() -> None:
    older = "2025-06-01T00:00:00+00:00"
    snapshot = _snapshot(
        [_item(7)],
        [_link(3, target=7, created_at=older), _link(12, target=7)],
    )

    shortlist = stale_close_candidates(snapshot, now=NOW)

    candidate = shortlist.candidates[0]
    assert candidate.newest_answers_link_id == 12
    assert candidate.newest_answer_created_at == OLD


def test_prefilter_boundary_exactly_stale_days_is_candidate() -> None:
    boundary_now = datetime(2026, 1, 31, tzinfo=timezone.utc)
    snapshot = _snapshot([_item(7)], [_link(11, target=7)])

    shortlist = stale_close_candidates(snapshot, now=boundary_now)

    assert (boundary_now - datetime.fromisoformat(OLD)) == timedelta(
        days=STALE_DAYS
    )
    assert [candidate.item_id for candidate in shortlist.candidates] == [7]


def test_prefilter_fresh_answers_link_within_stale_days_is_not_candidate() -> None:
    fresh = "2026-01-15T00:00:00+00:00"  # 17 days before NOW
    snapshot = _snapshot([_item(7)], [_link(11, target=7, created_at=fresh)])

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert shortlist.candidates == []
    assert shortlist.truncated is False


def test_prefilter_malformed_created_at_is_not_candidate_and_never_raises() -> None:
    naive = "2026-01-01T00:00:00"  # parseable but no offset: fail closed
    snapshot = _snapshot(
        [_item(7), _item(9)],
        [
            _link(11, target=7, created_at="not-a-date"),
            _link(12, target=9, created_at=naive),
        ],
    )

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert shortlist.candidates == []


def test_prefilter_rejected_links_are_invisible() -> None:
    snapshot = _snapshot([_item(7)], [_link(11, target=7, status="Rejected")])

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert shortlist.candidates == []


def test_prefilter_caps_at_ten_and_sets_truncated() -> None:
    items = [_item(item_id) for item_id in range(1, 13)]
    links = [_link(100 + item_id, target=item_id) for item_id in range(1, 13)]

    shortlist = stale_close_candidates(_snapshot(items, links), now=NOW)

    assert [candidate.item_id for candidate in shortlist.candidates] == list(
        range(1, 11)
    )
    assert shortlist.truncated is True


def test_prefilter_carries_statement_for_display() -> None:
    snapshot = _snapshot(
        [_item(7, statement="should we cache tokens?")], [_link(11, target=7)]
    )

    shortlist = stale_close_candidates(snapshot, now=NOW)

    assert shortlist.candidates[0].statement == "should we cache tokens?"


# --- the boundary parser (T7 fixtures) ------------------------------------


def test_parser_reads_valid_proposal_fixture() -> None:
    proposal = parse_close_proposal(_fixture_text("close_proposal_valid.json"))

    assert proposal is not None
    assert proposal.reason == "expired"
    assert proposal.confidence == 0.8
    assert proposal.rationale == "answered long ago, no follow-up open"


def test_parser_decline_fixture_yields_none() -> None:
    proposal = parse_close_proposal(_fixture_text("close_proposal_decline.json"))

    assert proposal is None


def test_parser_bad_reason_fixture_raises_close_ai_schema_invalid() -> None:
    with pytest.raises(CloseAiSchemaInvalid) as excinfo:
        parse_close_proposal(_fixture_text("close_proposal_bad_reason.json"))

    assert excinfo.value.code == "MAINTAIN-019"


def test_parser_not_object_fixture_raises_close_ai_schema_invalid() -> None:
    with pytest.raises(CloseAiSchemaInvalid) as excinfo:
        parse_close_proposal(_fixture_text("close_proposal_not_object.json"))

    assert excinfo.value.code == "MAINTAIN-019"


def test_parser_empty_answer_raises_close_ai_schema_invalid() -> None:
    with pytest.raises(CloseAiSchemaInvalid):
        parse_close_proposal(_fixture_text("close_proposal_empty.txt"))


def test_parser_confidence_out_of_range_raises_close_ai_schema_invalid() -> None:
    for confidence in ("1.5", "-0.1"):
        answer = (
            '{"close": true, "reason": "expired",'
            f' "confidence": {confidence}, "rationale": null}}'
        )
        with pytest.raises(CloseAiSchemaInvalid):
            parse_close_proposal(answer)


# --- the one engine retry -------------------------------------------------


def test_retry_once_on_call_failure() -> None:
    proposer = FakeCloseProposer(
        [CloseAiCallFailed("call fail", item_id=7), _proposal_response()]
    )

    outcome = propose_close_with_retry(proposer, candidate=_candidate())

    assert outcome.proposal is not None
    assert outcome.proposal.reason == "expired"
    assert outcome.raw_response == "RAW-PROPOSAL"
    assert len(proposer.calls) == 2


def test_retry_once_on_schema_failure() -> None:
    proposer = FakeCloseProposer(
        [
            CloseAiSchemaInvalid("bad schema", item_id=7),
            _proposal_response(),
        ]
    )

    outcome = propose_close_with_retry(proposer, candidate=_candidate())

    assert outcome.proposal is not None
    assert len(proposer.calls) == 2


def test_second_failure_propagates_coded_error() -> None:
    proposer = FakeCloseProposer(
        [
            CloseAiCallFailed("call fail 1", item_id=7),
            CloseAiCallFailed("call fail 2", item_id=7),
        ]
    )

    with pytest.raises(CloseAiCallFailed) as excinfo:
        propose_close_with_retry(proposer, candidate=_candidate())

    assert excinfo.value.code == "MAINTAIN-018"
    assert len(proposer.calls) == 2


# --- the display block ----------------------------------------------------


def test_format_block_decline_shape() -> None:
    lines = format_proposal_block(_candidate(), None, index=1, total=1)

    assert lines == [
        "Proposal 1/1: item 7 [Question] should we cache tokens?",
        f"  newest answers link 11, confirmed {OLD}",
        "  no close proposed",
    ]

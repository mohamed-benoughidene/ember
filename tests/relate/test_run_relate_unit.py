"""Unit tests for the relate phase 3 + 4 engine core (`run_relate`).

Every effect goes through a fake port. The tests read the returned
`ConfirmResult` and the observable side effects the fakes record (the saved raw
answer, the accepted link ids).
"""

from __future__ import annotations

import pytest

from ember.relate.confirm_write import ConfirmResult
from ember.relate.errors import (
    AiResponseWriteFailed,
    SchemaValidationFailed,
    TargetNotInCandidates,
)
from ember.relate.link_gatekeeper import RejectedLink
from ember.relate.link_proposal import LinkProposal, LinkProposalResponse
from ember.relate.rows import Link, NewItem, RankedCandidate, SignalKind
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate
from tests.fakes import FIXED_TIME, FakeConfirm
from tests.relate.fakes import (
    FakeAiResponseStore,
    FakeLinkLookup,
    FakeLinkProposer,
    FakeLinkStore,
)


def _item(i, t="Decision"):
    return NewItem(id=i, type=t, statement=f"s{i}", created_at=FIXED_TIME)


def _ranked(*ids):
    return [
        RankedCandidate(item=_item(i), cosine=1.0, source=SignalKind.dense)
        for i in ids
    ]


def _ports(*, responses, lookup=None, store=None, ai_store=None, confirm=None):
    return RelatePorts(
        link_lookup=lookup or FakeLinkLookup(items=[_item(1), _item(2), _item(3)]),
        link_store=store or FakeLinkStore(),
        link_proposer=FakeLinkProposer(responses),
        ai_response_store=ai_store or FakeAiResponseStore(),
        confirm=confirm or FakeConfirm(["y"]),
    )


def test_happy_path_accepts_and_saves():
    ai_store = FakeAiResponseStore()
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="depends_on")],
            )
        ],
        store=FakeLinkStore(start_id=7),
        ai_store=ai_store,
        confirm=FakeConfirm(["y"]),
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    result = run_relate(ports, request)

    assert result == ConfirmResult(accepted=[7], rejected=0, skipped=0, aborted=False)
    assert ai_store.saved == [(1, "raw")]


def test_phase35_valueerror_maps_to_030():
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="depends_on")],
            )
        ],
        ai_store=FakeAiResponseStore(error=ValueError("bad owner")),
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    with pytest.raises(SchemaValidationFailed) as excinfo:
        run_relate(ports, request)
    assert excinfo.value.code == "RELATE-030"


def test_phase35_runtimeerror_maps_to_036():
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="depends_on")],
            )
        ],
        ai_store=FakeAiResponseStore(error=RuntimeError("disk")),
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    with pytest.raises(AiResponseWriteFailed) as excinfo:
        run_relate(ports, request)
    assert excinfo.value.code == "RELATE-036"


def test_gatekeeper_rejection_counted_not_shown():
    lookup = FakeLinkLookup(
        items=[_item(1), _item(2)],
        links=[
            Link(
                id=9,
                source_item_id=1,
                target_item_id=2,
                link_type="depends_on",
                status="Rejected",
                created_at=FIXED_TIME,
            )
        ],
    )
    confirm = FakeConfirm(["y"])
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="depends_on")],
            )
        ],
        lookup=lookup,
        confirm=confirm,
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    result = run_relate(ports, request)

    assert result.accepted == []
    assert result.rejected == 1
    assert confirm.written == []


def test_gatekeeper_rejections_carry_codes_and_detail():
    lookup = FakeLinkLookup(
        items=[_item(1), _item(2)],
        links=[
            Link(
                id=9,
                source_item_id=1,
                target_item_id=2,
                link_type="depends_on",
                status="Rejected",
                created_at=FIXED_TIME,
            )
        ],
    )
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="depends_on")],
            )
        ],
        lookup=lookup,
        confirm=FakeConfirm(["y"]),
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    result = run_relate(ports, request)

    assert result.accepted == []
    assert result.rejected == 1
    assert result.gatekeeper_rejections == [
        RejectedLink(
            code="RELATE-009", detail="link 9 exists (1 -> 2)"
        )
    ]


def test_bad_target_propagates_024():
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=99, link_type="depends_on")],
            )
        ]
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    with pytest.raises(TargetNotInCandidates) as excinfo:
        run_relate(ports, request)
    assert excinfo.value.code == "RELATE-024"


def test_abort_sets_aborted():
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="depends_on")],
            )
        ],
        confirm=FakeConfirm(["q"]),
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    result = run_relate(ports, request)

    assert result.aborted is True
    assert result.accepted == []


def test_raw_response_saved_even_when_target_invalid():
    ai_store = FakeAiResponseStore()
    ports = _ports(
        responses=[
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=99, link_type="depends_on")],
            )
        ],
        ai_store=ai_store,
    )
    request = RelateRequest(new_item=_item(1), ranked=_ranked(2), env={})

    with pytest.raises(TargetNotInCandidates):
        run_relate(ports, request)

    assert ai_store.saved == [(1, "raw")]

"""Unit tests for relate phase 3 proposal parsing, retry and boundary checks.

No DB, no model. `parse_proposals` is driven with raw strings, the retry loop
with a scripted `FakeLinkProposer`, and `validate_proposals` with plain rows.
"""

from __future__ import annotations

import pytest

from ember.relate.errors import (
    AiCallFailed,
    AiResponseSchemaInvalid,
    ProposalSourceMismatch,
    TargetNotInCandidates,
)
from ember.relate.link_proposal import (
    LinkProposal,
    LinkProposalResponse,
    parse_proposals,
    propose_links_with_retry,
    validate_proposals,
)
from ember.relate.rows import NewItem, RankedCandidate, SignalKind
from tests.fakes import FIXED_TIME
from tests.relate.fakes import FakeLinkProposer


def _item(i, t="Decision"):
    return NewItem(id=i, type=t, statement=f"s{i}", created_at=FIXED_TIME)


def _ranked(*ids):
    return [
        RankedCandidate(item=_item(i), cosine=1.0, source=SignalKind.dense)
        for i in ids
    ]


def test_parse_object_form():
    proposals = parse_proposals(
        '{"proposals":[{"target_item_id":2,"link_type":"supports"}]}'
    )
    assert len(proposals) == 1
    assert proposals[0].target_item_id == 2


def test_parse_bare_list():
    proposals = parse_proposals('[{"target_item_id":3,"link_type":"answers"}]')
    assert len(proposals) == 1
    assert proposals[0].target_item_id == 3


def test_parse_strips_code_fence():
    fenced = (
        "```json\n"
        '{"proposals":[{"target_item_id":2,"link_type":"supports"}]}'
        "\n```"
    )
    proposals = parse_proposals(fenced)
    assert len(proposals) == 1
    assert proposals[0].target_item_id == 2


def test_parse_not_json():
    with pytest.raises(AiResponseSchemaInvalid) as excinfo:
        parse_proposals("nope")
    assert excinfo.value.code == "RELATE-033"


def test_parse_object_without_proposals_list():
    with pytest.raises(AiResponseSchemaInvalid):
        parse_proposals('{"x":1}')


def test_parse_bad_entry_shape():
    with pytest.raises(AiResponseSchemaInvalid):
        parse_proposals('{"proposals":[{"link_type":"supports"}]}')


def test_retry_succeeds_on_second_call():
    proposer = FakeLinkProposer(
        [
            AiCallFailed("x"),
            LinkProposalResponse(
                raw_response="raw",
                proposals=[LinkProposal(target_item_id=2, link_type="supports")],
            ),
        ]
    )
    response = propose_links_with_retry(
        proposer, new_item=_item(1), candidates=[_item(2)]
    )
    assert response.raw_response == "raw"
    assert len(response.proposals) == 1
    assert len(proposer.calls) == 2


def test_retry_exhausted_raises_032():
    proposer = FakeLinkProposer([AiCallFailed("a"), AiCallFailed("b")])
    with pytest.raises(AiCallFailed):
        propose_links_with_retry(
            proposer, new_item=_item(1), candidates=[_item(2)]
        )
    assert len(proposer.calls) == 2


def test_parse_failure_does_not_retry():
    proposer = FakeLinkProposer([AiResponseSchemaInvalid("bad")])
    with pytest.raises(AiResponseSchemaInvalid):
        propose_links_with_retry(
            proposer, new_item=_item(1), candidates=[_item(2)]
        )
    assert len(proposer.calls) == 1


def test_validate_target_not_in_candidates():
    with pytest.raises(TargetNotInCandidates) as excinfo:
        validate_proposals(
            [LinkProposal(target_item_id=9, link_type="supports")],
            candidates=[_item(2)],
            new_item=_item(1),
        )
    assert excinfo.value.code == "RELATE-024"


def test_validate_source_mismatch():
    with pytest.raises(ProposalSourceMismatch) as excinfo:
        validate_proposals(
            [LinkProposal(target_item_id=2, link_type="supports", source_item_id=5)],
            candidates=[_item(2)],
            new_item=_item(1),
        )
    assert excinfo.value.code == "RELATE-025"


def test_validate_ok():
    proposals = [LinkProposal(target_item_id=2, link_type="supports")]
    result = validate_proposals(
        proposals, candidates=[_item(2)], new_item=_item(1)
    )
    assert result is proposals

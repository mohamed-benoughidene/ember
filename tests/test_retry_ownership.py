"""Retry-ownership tests: engine cores call the AI port exactly once.

Retry policy lives in the adapter (the OpenAI SDK client), not in the
engine cores. Each test pins that the core wraps the port once and
propagates the error instead of retrying.
"""

from __future__ import annotations

import pytest

from ember.capture.errors import AiCallError
from ember.capture.item_proposal import propose_items
from ember.maintain.close_proposer import StaleCandidate, propose_close_with_retry
from ember.maintain.errors import CloseAiCallFailed
from ember.relate.errors import AiCallFailed
from ember.relate.link_proposal import propose_links_with_retry
from ember.relate.rows import NewItem
from tests.fakes import FIXED_TIME, FakeItemProposer
from tests.maintain.fakes import FakeCloseProposer
from tests.relate.fakes import FakeLinkProposer


def _new_item(item_id: int) -> NewItem:
    return NewItem(id=item_id, type="Decision", statement="s", created_at=FIXED_TIME)


def _stale_candidate() -> StaleCandidate:
    return StaleCandidate(
        item_id=7,
        item_type="Question",
        statement="should we cache tokens?",
        newest_answers_link_id=11,
        answered_by_item_id=4,
        newest_answer_created_at="2026-01-01T00:00:00+00:00",
    )


def test_propose_items_calls_the_port_once() -> None:
    """A failing AI call surfaces after exactly ONE port call, no retry."""
    proposer = FakeItemProposer([AiCallError("ai call fail")])

    with pytest.raises(AiCallError):
        propose_items(proposer, raw_text="note text", context=[])

    assert len(proposer.calls) == 1


def test_propose_links_with_retry_calls_the_port_once() -> None:
    """A failing relate AI call surfaces after exactly ONE port call, no retry."""
    proposer = FakeLinkProposer([AiCallFailed("ai call fail")])

    with pytest.raises(AiCallFailed):
        propose_links_with_retry(
            proposer, new_item=_new_item(1), candidates=[_new_item(2)]
        )

    assert len(proposer.calls) == 1


def test_propose_close_with_retry_calls_the_port_once() -> None:
    """A failing maintain AI call surfaces after exactly ONE port call, no retry."""
    proposer = FakeCloseProposer([CloseAiCallFailed("ai call fail", item_id=7)])

    with pytest.raises(CloseAiCallFailed):
        propose_close_with_retry(proposer, candidate=_stale_candidate())

    assert len(proposer.calls) == 1

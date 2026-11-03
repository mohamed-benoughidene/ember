"""Retry-ownership tests: engine cores call the AI port exactly once.

Retry policy lives in the adapter (the OpenAI SDK client), not in the
engine cores. Each test pins that the core wraps the port once and
propagates the error instead of retrying.
"""

from __future__ import annotations

import pytest

from ember.capture.errors import AiCallError
from ember.capture.item_proposal import propose_items
from tests.fakes import FakeItemProposer


def test_propose_items_calls_the_port_once() -> None:
    """A failing AI call surfaces after exactly ONE port call, no retry."""
    proposer = FakeItemProposer([AiCallError("ai call fail")])

    with pytest.raises(AiCallError):
        propose_items(proposer, raw_text="note text", context=[])

    assert len(proposer.calls) == 1

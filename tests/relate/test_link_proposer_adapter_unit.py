"""Unit tests for the relate `OpenAiLinkProposer` adapter, no network."""

from __future__ import annotations

from types import SimpleNamespace

import openai._httpx2  # the SDK's own vendored httpx2 (request shape only)
import pytest
from openai import APITimeoutError, OpenAIError

from ember.adapters.llm import OpenAiLinkProposer, build_link_proposer
from ember.relate.errors import (
    AiCallFailed,
    AiCallTimedOut,
    AiRateLimited,
    AiResponseSchemaInvalid,
    ApiKeyMissing,
)
from ember.relate.rows import NewItem
from tests.fakes import FIXED_TIME


class _OpenAIRateLimited(OpenAIError):
    """A 429-shaped provider error: the shape the SDK raises as
    `APIStatusError` with `status_code = 429` (the capture fake's shape)."""

    status_code = 429


class _OpenAITimeout(APITimeoutError):
    """A timeout-shaped provider error: the exact class real request
    timeouts arrive as (`openai.APITimeoutError`)."""

    pass


def _timeout_error() -> _OpenAITimeout:
    """Build the timeout fake; the SDK's constructor wants a request."""
    request = openai._httpx2.httpx2.Request("POST", "http://127.0.0.1")
    return _OpenAITimeout(request=request)


class _FakeCompletions:
    def __init__(self, *, content=None, error=None):
        self._content = content
        self._error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeClient:
    def __init__(self, *, content=None, error=None):
        self.api_key = "secret-key"
        self.chat = SimpleNamespace(completions=_FakeCompletions(content=content, error=error))


def _items():
    new_item = NewItem(id=1, type="Finding", statement="s1", created_at=FIXED_TIME)
    candidate = NewItem(id=2, type="Decision", statement="s2", created_at=FIXED_TIME)
    return new_item, candidate


def test_propose_links_returns_parsed_proposals() -> None:
    client = _FakeClient(content='{"proposals":[{"target_item_id":2,"link_type":"supports"}]}')
    new_item, candidate = _items()

    response = OpenAiLinkProposer(client, "model").propose_links(new_item, [candidate])

    assert response.proposals[0].target_item_id == 2
    assert response.raw_response.startswith("{")


def test_propose_links_transport_error_maps_to_032() -> None:
    client = _FakeClient(error=OpenAIError("boom"))
    new_item, candidate = _items()

    with pytest.raises(AiCallFailed) as excinfo:
        OpenAiLinkProposer(client, "model").propose_links(new_item, [candidate])

    assert excinfo.value.code == "RELATE-032"


def test_propose_links_bad_json_maps_to_033() -> None:
    client = _FakeClient(content="not json")
    new_item, candidate = _items()

    with pytest.raises(AiResponseSchemaInvalid) as excinfo:
        OpenAiLinkProposer(client, "model").propose_links(new_item, [candidate])

    assert excinfo.value.code == "RELATE-033"


def test_build_link_proposer_missing_key_maps_to_038() -> None:
    with pytest.raises(ApiKeyMissing) as excinfo:
        build_link_proposer({})

    assert excinfo.value.code == "RELATE-038"


def test_propose_links_rate_limited_429_retried_once_with_controlled_sleep() -> None:
    """Chunk 3: a 429 is not fatal at once — the adapter's own policy
    retries once. The fake sees exactly 2 calls, and the ONE wait between
    them goes through the injected `sleep` (no real waiting in tests). The
    final failure carries the NEW relate rate-limit code, not the shared
    RELATE-032 call-failure code."""
    client = _FakeClient(error=_OpenAIRateLimited("rate limit exceeded"))
    sleeps: list[tuple[int, float]] = []

    def controlled_sleep(seconds: float) -> None:
        # Record how many calls the fake had seen when the sleep began.
        sleeps.append((len(client.chat.completions.calls), seconds))

    new_item, candidate = _items()
    proposer = OpenAiLinkProposer(
        client,
        "model",
        sleep=controlled_sleep,
        jitter=lambda: 0.0,
        clock=lambda: 0.0,
    )

    with pytest.raises(AiRateLimited) as excinfo:
        proposer.propose_links(new_item, [candidate])

    assert excinfo.value.code == "RELATE-041"
    assert excinfo.value.code != "RELATE-032"
    assert len(client.chat.completions.calls) == 2
    # Exactly one sleep, and it happened AFTER attempt 1, BEFORE attempt 2.
    assert len(sleeps) == 1
    assert sleeps[0][0] == 1
    assert 0 < sleeps[0][1]


def test_propose_links_timed_out_maps_to_the_timeout_code() -> None:
    """Chunk 3: a request timeout carries the NEW relate timeout code, not
    the shared RELATE-032 call-failure code. The same policy applies: it
    retries once before giving up."""
    client = _FakeClient(error=_timeout_error())
    new_item, candidate = _items()
    proposer = OpenAiLinkProposer(
        client,
        "model",
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        clock=lambda: 0.0,
    )

    with pytest.raises(AiCallTimedOut) as excinfo:
        proposer.propose_links(new_item, [candidate])

    assert excinfo.value.code == "RELATE-042"
    assert excinfo.value.code != "RELATE-032"
    assert len(client.chat.completions.calls) == 2

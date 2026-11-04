"""Unit tests for the `OpenAiCloseProposer` adapter, no network."""

from __future__ import annotations

from types import SimpleNamespace

import openai._httpx2  # the SDK's own vendored httpx2 (request shape only)
import pytest
from openai import APITimeoutError, OpenAIError

from ember.adapters.llm import (
    REQUEST_TIMEOUT_SECONDS,
    OpenAiCloseProposer,
    build_close_proposer,
)
from ember.maintain.close_proposer import StaleCandidate
from ember.maintain.errors import (
    CloseAiCallFailed,
    CloseAiCallTimedOut,
    CloseAiConfigMissing,
    CloseAiRateLimited,
)

OLD = "2026-01-01T00:00:00+00:00"


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
VALID_ANSWER = (
    '{"close": true, "reason": "expired", "confidence": 0.8,'
    ' "rationale": null}'
)


def _candidate() -> StaleCandidate:
    return StaleCandidate(
        item_id=9,
        item_type="Question",
        statement="which auth backend?",
        newest_answers_link_id=12,
        answered_by_item_id=4,
        newest_answer_created_at=OLD,
    )


class _FakeCompletions:
    def __init__(self, *, content=None, error=None):
        self._content = content
        self._error = error
        self.kwargs: dict | None = None
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.kwargs = kwargs
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeClient:
    def __init__(self, *, content=None, error=None):
        self.api_key = "secret-key"
        self.chat = SimpleNamespace(
            completions=_FakeCompletions(content=content, error=error)
        )


def test_build_close_proposer_missing_key_raises_close_ai_config_missing() -> None:
    with pytest.raises(CloseAiConfigMissing) as excinfo:
        build_close_proposer({})

    assert excinfo.value.code == "MAINTAIN-020"


def test_build_close_proposer_uses_env_overrides(monkeypatch) -> None:
    recorded: dict = {}

    def fake_openai(**kwargs):
        recorded.update(kwargs)
        return object()

    monkeypatch.setattr("ember.adapters.llm.OpenAI", fake_openai)

    proposer = build_close_proposer(
        {
            "EMBER_AI_API_KEY": "k",
            "EMBER_AI_BASE_URL": "http://example.internal/v1",
            "EMBER_AI_MODEL": "model-x",
        }
    )

    assert recorded["api_key"] == "k"
    assert recorded["base_url"] == "http://example.internal/v1"
    assert recorded["timeout"] == REQUEST_TIMEOUT_SECONDS
    assert recorded["max_retries"] == 0
    assert proposer._model == "model-x"


def test_openai_close_proposer_maps_openaierror_to_close_ai_call_failed() -> None:
    client = _FakeClient(error=OpenAIError("boom"))

    with pytest.raises(CloseAiCallFailed) as excinfo:
        OpenAiCloseProposer(client, "model").propose_close(_candidate())

    assert excinfo.value.code == "MAINTAIN-018"
    assert excinfo.value.context["item_id"] == 9
    assert "secret-key" not in str(excinfo.value.context.get("detail", ""))


def test_openai_close_proposer_passes_temperature_zero() -> None:
    client = _FakeClient(content=VALID_ANSWER)
    proposer = OpenAiCloseProposer(client, "model")

    response = proposer.propose_close(_candidate())

    assert client.chat.completions.kwargs["temperature"] == 0.0
    assert client.chat.completions.kwargs["model"] == "model"
    assert response.proposal is not None
    assert response.proposal.reason == "expired"
    assert response.raw_response == VALID_ANSWER


def test_openai_close_proposer_rate_limited_429_retried_once_item_id_stays() -> None:
    """Chunk 3: a 429 is not fatal at once — the adapter's own policy
    retries once. The fake sees exactly 2 calls, and the ONE wait between
    them goes through the injected `sleep` (no real waiting in tests). The
    final failure carries the NEW maintain rate-limit code, not the shared
    MAINTAIN-018 call-failure code, and `item_id` stays on the error (I19)."""
    client = _FakeClient(error=_OpenAIRateLimited("rate limit exceeded"))
    sleeps: list[tuple[int, float]] = []

    def controlled_sleep(seconds: float) -> None:
        # Record how many calls the fake had seen when the sleep began.
        sleeps.append((len(client.chat.completions.calls), seconds))

    proposer = OpenAiCloseProposer(
        client,
        "model",
        sleep=controlled_sleep,
        jitter=lambda: 0.0,
        clock=lambda: 0.0,
    )

    with pytest.raises(CloseAiRateLimited) as excinfo:
        proposer.propose_close(_candidate())

    assert excinfo.value.code == "MAINTAIN-029"
    assert excinfo.value.code != "MAINTAIN-018"
    assert excinfo.value.context["item_id"] == 9
    assert "secret-key" not in str(excinfo.value.context.get("detail", ""))
    assert len(client.chat.completions.calls) == 2
    # Exactly one sleep, and it happened AFTER attempt 1, BEFORE attempt 2.
    assert len(sleeps) == 1
    assert sleeps[0][0] == 1
    assert 0 < sleeps[0][1]


def test_openai_close_proposer_timed_out_maps_to_timeout_code() -> None:
    """Chunk 3: a request timeout carries the NEW maintain timeout code, not
    the shared MAINTAIN-018 call-failure code, and `item_id` stays on the
    error (I19). The same policy applies: it retries once before giving up."""
    client = _FakeClient(error=_timeout_error())
    proposer = OpenAiCloseProposer(
        client,
        "model",
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        clock=lambda: 0.0,
    )

    with pytest.raises(CloseAiCallTimedOut) as excinfo:
        proposer.propose_close(_candidate())

    assert excinfo.value.code == "MAINTAIN-030"
    assert excinfo.value.code != "MAINTAIN-018"
    assert excinfo.value.context["item_id"] == 9
    assert len(client.chat.completions.calls) == 2

"""Unit tests for the `OpenAiCloseProposer` adapter, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from openai import OpenAIError

from ember.adapters.llm import (
    REQUEST_TIMEOUT_SECONDS,
    OpenAiCloseProposer,
    build_close_proposer,
)
from ember.maintain.close_proposer import StaleCandidate
from ember.maintain.errors import CloseAiCallFailed, CloseAiConfigMissing

OLD = "2026-01-01T00:00:00+00:00"
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

    def create(self, **kwargs):
        self.kwargs = kwargs
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

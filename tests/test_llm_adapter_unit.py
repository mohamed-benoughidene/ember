"""Unit tests for the OpenAI-compatible adapter (fake client, no network)."""

from __future__ import annotations

import json

import pytest
from openai import OpenAIError

from ember.adapters.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    REQUEST_TIMEOUT_SECONDS,
    OpenAiItemProposer,
    build_item_proposer,
)
from ember.capture.errors import AiCallError, AiSchemaError
from ember.capture.item_proposal import ContextItem, ItemType

RAW_TEXT = "We decided to use SQLite."
ANSWER = json.dumps(
    [
        {
            "type": "Decision",
            "statement": "Use SQLite",
            "source_quote": "use SQLite",
            "confidence": 0.9,
        },
        {
            "type": "Risk",
            "statement": "bad entry",
            "source_quote": "SQLite",
            "confidence": 0.1,
        },
    ]
)


class _Boom(OpenAIError):
    pass


class _Message:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


class _EmptyResponse:
    choices: list = []


class _Completions:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeClient:
    def __init__(self, outcome: object) -> None:
        self.completions = _Completions(outcome)
        self.chat = type("_Chat", (), {"completions": self.completions})()


def _proposer(outcome: object, model: str = "test-model") -> OpenAiItemProposer:
    return OpenAiItemProposer(_FakeClient(outcome), model)


# --- request shape --------------------------------------------------------


def test_propose_sends_the_system_prompt_and_raw_text() -> None:
    proposer = _proposer(_Response(ANSWER))

    proposer.propose(RAW_TEXT, [])

    messages = proposer._client.completions.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "Decision" in messages[0]["content"]
    assert RAW_TEXT in messages[1]["content"]


def test_propose_sends_the_context_items() -> None:
    proposer = _proposer(_Response("[]"))
    context = [ContextItem(id=7, type=ItemType.FINDING, statement="Old finding")]

    proposer.propose(RAW_TEXT, context)

    user = proposer._client.completions.calls[0]["messages"][1]["content"]
    assert "[7] Finding: Old finding" in user


def test_model_name_goes_into_the_request() -> None:
    proposer = _proposer(_Response("[]"), model="my-model")

    proposer.propose(RAW_TEXT, [])

    assert proposer._client.completions.calls[0]["model"] == "my-model"


# --- answer handling ------------------------------------------------------


def test_propose_returns_the_parsed_batch_with_drops() -> None:
    proposer = _proposer(_Response(ANSWER))

    response = proposer.propose(RAW_TEXT, [])

    assert [proposal.statement for proposal in response.batch.proposals] == [
        "Use SQLite"
    ]
    assert [drop.rule for drop in response.batch.dropped] == ["type"]


def test_propose_hands_back_the_raw_answer_verbatim() -> None:
    proposer = _proposer(_Response(ANSWER))

    response = proposer.propose(RAW_TEXT, [])

    assert response.raw_response == ANSWER


def test_provider_failure_becomes_ai_call_error() -> None:
    proposer = _proposer(_Boom("nope"))

    with pytest.raises(AiCallError) as excinfo:
        proposer.propose(RAW_TEXT, [])

    assert excinfo.value.code == "CAPTURE-008"


def test_non_json_answer_becomes_schema_error() -> None:
    proposer = _proposer(_Response("the model said hello"))

    with pytest.raises(AiSchemaError):
        proposer.propose(RAW_TEXT, [])


def test_empty_content_becomes_schema_error() -> None:
    proposer = _proposer(_Response(None))

    with pytest.raises(AiSchemaError):
        proposer.propose(RAW_TEXT, [])


def test_no_choices_becomes_schema_error() -> None:
    proposer = _proposer(_EmptyResponse())

    with pytest.raises(AiSchemaError):
        proposer.propose(RAW_TEXT, [])


# --- config ---------------------------------------------------------------


def test_build_requires_an_api_key() -> None:
    with pytest.raises(AiCallError) as excinfo:
        build_item_proposer({})

    assert excinfo.value.code == "CAPTURE-008"


def test_build_reads_the_env_and_returns_the_adapter() -> None:
    proposer = build_item_proposer({"OPENROUTER_API_KEY": "k", "EMBER_AI_MODEL": "m"})

    assert isinstance(proposer, OpenAiItemProposer)


def test_build_bounds_the_timeout_and_sdk_retries(monkeypatch) -> None:
    recorded: dict = {}

    def fake_openai(**kwargs):
        recorded.update(kwargs)
        return object()

    monkeypatch.setattr("ember.adapters.llm.OpenAI", fake_openai)

    build_item_proposer({"OPENROUTER_API_KEY": "k"})

    assert recorded["api_key"] == "k"
    assert recorded["timeout"] == REQUEST_TIMEOUT_SECONDS
    assert recorded["max_retries"] == 0


def test_default_model_and_base_url_are_locked() -> None:
    assert DEFAULT_MODEL == "anthropic/claude-3.5-sonnet"
    assert DEFAULT_BASE_URL == "https://openrouter.ai/api/v1"

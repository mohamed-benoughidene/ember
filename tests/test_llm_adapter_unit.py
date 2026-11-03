"""Unit tests for the OpenAI-compatible adapter (fake client, no network)."""

from __future__ import annotations

import json

import pytest
import openai._httpx2  # the SDK's own vendored httpx2 (request shape only)
from openai import APITimeoutError, OpenAIError

from ember.adapters.llm import (
    REQUEST_TIMEOUT_SECONDS,
    OpenAiItemProposer,
    build_item_proposer,
    build_link_proposer,
)
from ember.capture.errors import (
    AiCallError,
    AiRateLimitError,
    AiSchemaError,
    AiTimeoutError,
)
from ember.capture.item_proposal import ContextItem, ItemType
from ember.errors import EmberError

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


class _RateLimitedBoom(_Boom):
    """A 429-shaped provider error: the shape the SDK raises as
    `APIStatusError` with `status_code = 429` (Chunk 1)."""

    status_code = 429


class _TimeoutBoom(APITimeoutError):
    """A timeout-shaped provider error: the exact class real request
    timeouts arrive as (`openai.APITimeoutError`), so the fake copies no
    shape by hand."""

    pass


def _timeout_boom() -> _TimeoutBoom:
    """Build the timeout fake; the SDK's constructor wants a request."""
    request = openai._httpx2.httpx2.Request("POST", "http://127.0.0.1")
    return _TimeoutBoom(request=request)


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


class _StrangeReply:
    """A reply object with no `choices` attribute at all (Chunk 9c)."""


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
    def __init__(self, outcome: object, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.completions = _Completions(outcome)
        self.chat = type("_Chat", (), {"completions": self.completions})()


def _proposer(
    outcome: object,
    model: str = "test-model",
    *,
    sleep=None,
    jitter=None,
    clock=None,
) -> OpenAiItemProposer:
    """Build a proposer with the retry injectables faked out (no real
    waiting, deterministic backoff) unless a test passes its own."""
    return OpenAiItemProposer(
        _FakeClient(outcome),
        model,
        sleep=sleep if sleep is not None else (lambda _seconds: None),
        jitter=jitter if jitter is not None else (lambda: 0.0),
        clock=clock if clock is not None else (lambda: 0.0),
    )


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


def test_provider_failure_keeps_the_provider_reason() -> None:
    proposer = _proposer(_Boom("No endpoints found for model x"))

    with pytest.raises(AiCallError) as excinfo:
        proposer.propose(RAW_TEXT, [])

    assert excinfo.value.context["reason"] == "_Boom"
    assert "No endpoints found for model x" in str(excinfo.value.context["detail"])


def test_provider_failure_never_carries_the_api_key() -> None:
    client = _FakeClient(_Boom("rejected key sk-secret-123"), api_key="sk-secret-123")
    proposer = OpenAiItemProposer(client, "test-model")

    with pytest.raises(AiCallError) as excinfo:
        proposer.propose(RAW_TEXT, [])

    assert "sk-secret-123" not in excinfo.value.log_line()
    assert "REDACTED" in excinfo.value.log_line()


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


def test_strange_reply_without_choices_attr_becomes_schema_error() -> None:
    """A reply object with no `choices` attribute maps to CAPTURE-009
    (Chunk 9c), it never leaks a raw `AttributeError`."""
    proposer = _proposer(_StrangeReply())

    with pytest.raises(AiSchemaError) as excinfo:
        proposer.propose(RAW_TEXT, [])

    assert excinfo.value.code == "CAPTURE-009"


def test_429_provider_failure_raises_the_capture_rate_limited_code() -> None:
    """A 429 reply carries its OWN capture code (Chunk 1); the number is
    the next free one in the family, not pinned here."""
    proposer = _proposer(_RateLimitedBoom("rate limit exceeded"))

    with pytest.raises(AiCallError) as excinfo:
        proposer.propose(RAW_TEXT, [])

    assert isinstance(excinfo.value, AiRateLimitError)
    assert excinfo.value.code == AiRateLimitError.code


def test_timeout_provider_failure_raises_the_capture_timed_out_code() -> None:
    """A request timeout carries its OWN capture code (Chunk 1); the
    number is the next free one in the family, not pinned here."""
    proposer = _proposer(_timeout_boom())

    with pytest.raises(AiCallError) as excinfo:
        proposer.propose(RAW_TEXT, [])

    assert isinstance(excinfo.value, AiTimeoutError)
    assert excinfo.value.code == AiTimeoutError.code


# --- the one capture retry policy (Chunk 2) --------------------------------


def test_429_retried_once_with_a_backoff_sleep_between_attempts() -> None:
    """Chunk 2: a 429 is not fatal at once — the policy retries once. The
    fake sees exactly 2 attempts, and the ONE wait between them goes
    through the injected `sleep` (no real waiting in tests)."""
    client = _FakeClient(_RateLimitedBoom("rate limit exceeded"))
    sleeps: list[tuple[int, float]] = []

    def controlled_sleep(seconds: float) -> None:
        # Record how many calls the fake had seen when the sleep began.
        sleeps.append((len(client.completions.calls), seconds))

    proposer = OpenAiItemProposer(
        client,
        "test-model",
        sleep=controlled_sleep,
        jitter=lambda: 0.0,
        clock=lambda: 0.0,
    )

    with pytest.raises(AiRateLimitError):
        proposer.propose(RAW_TEXT, [])

    assert len(client.completions.calls) == 2
    # Exactly one sleep, and it happened AFTER attempt 1, BEFORE attempt 2.
    assert len(sleeps) == 1
    assert sleeps[0][0] == 1
    assert 0 < sleeps[0][1]


def test_propose_sends_temperature_zero() -> None:
    """Chunk 2: capture sends temperature=0 (deterministic), through the
    same policy that owns the retry."""
    proposer = _proposer(_Response("[]"))

    proposer.propose(RAW_TEXT, [])

    assert proposer._client.completions.calls[0]["temperature"] == 0


# --- config ---------------------------------------------------------------


def test_build_requires_an_api_key() -> None:
    """The missing-key refusal carries its OWN dedicated code, no longer the
    shared CAPTURE-008 call-failure code (Batch 6, D-08, I17)."""
    with pytest.raises(EmberError) as excinfo:
        build_item_proposer({})

    assert excinfo.value.code == "CAPTURE-022"
    assert excinfo.value.code != "CAPTURE-008"


def test_build_link_proposer_missing_key_has_dedicated_code() -> None:
    """The relate side's missing-key refusal carries its OWN dedicated code,
    no longer the shared RELATE-035 config code (Batch 6, D-08, I17)."""
    with pytest.raises(EmberError) as excinfo:
        build_link_proposer({})

    assert excinfo.value.code == "RELATE-038"
    assert excinfo.value.code != "RELATE-035"
    assert excinfo.value.name != "ConfigMissing"


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

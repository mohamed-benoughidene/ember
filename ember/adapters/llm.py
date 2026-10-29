"""OpenAI-compatible LLM adapter for the Capture `ItemProposerPort`.

Points at the OpenRouter base URL by default (L1 section 0). The provider SDK
and the request shape live here; the engine core only knows the port. The raw
answer is checked with `parse_proposals` at this boundary (rule I9).
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from openai import OpenAI, OpenAIError

from ember.capture.errors import AiCallError, AiSchemaError
from ember.capture.item_proposal import (
    SYSTEM_PROMPT,
    ContextItem,
    ProposalResponse,
    parse_proposals,
)
from ember.maintain.close_proposer import (
    SYSTEM_PROMPT as CLOSE_SYSTEM_PROMPT,
    CloseProposalResponse,
    StaleCandidate,
    parse_close_proposal,
)
from ember.maintain.errors import (
    CloseAiCallFailed,
    CloseAiConfigMissing,
    CloseAiSchemaInvalid,
)
from ember.relate.errors import AiCallFailed, AiResponseSchemaInvalid, ConfigMissing
from ember.relate.link_proposal import (
    SYSTEM_PROMPT as LINK_SYSTEM_PROMPT,
    LinkProposalResponse,
    parse_proposals as parse_link_proposals,
)
from ember.relate.rows import NewItem

DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
REQUEST_TIMEOUT_SECONDS = 60.0
_API_KEY_VARS = ("EMBER_AI_API_KEY", "OPENROUTER_API_KEY")


class OpenAiItemProposer:
    """`ItemProposerPort` on the OpenAI SDK, OpenRouter base URL by default."""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def propose(self, raw_text: str, context: list[ContextItem]) -> ProposalResponse:
        """Return the raw provider answer and the proposals checked from it.

        Raise `AiCallError` (CAPTURE-008) with the provider's own status and
        message when the call fails, and `AiSchemaError` (CAPTURE-009) when the
        answer cannot be read. Side effect: one HTTP request to the provider.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=_messages(raw_text, context),
            )
        except OpenAIError as exc:
            raise AiCallError(
                "ai call fail",
                reason=type(exc).__name__,
                status=getattr(exc, "status_code", "?"),
                detail=_without_secret(str(exc), self._client.api_key),
            ) from exc
        content = _content(response)
        return ProposalResponse(
            raw_response=content,
            batch=parse_proposals(content, raw_text),
        )


def build_item_proposer(
    env: Mapping[str, str] | None = None,
) -> OpenAiItemProposer:
    """Build the adapter from env config. Fail fast when the key is missing.

    Keys: `EMBER_AI_API_KEY` (or `OPENROUTER_API_KEY`), `EMBER_AI_MODEL`,
    `EMBER_AI_BASE_URL`.

    Raise `AiCallError` (CAPTURE-008) when no API key is configured.

    The client is built with an explicit timeout and `max_retries=0`, so the
    only retry is the one `propose_items` owns (plan section 5, rule I15).
    """
    values = os.environ if env is None else env
    api_key = _first_present(values, _API_KEY_VARS)
    if not api_key:
        raise AiCallError("ai api key missing")
    client = OpenAI(
        api_key=api_key,
        base_url=values.get("EMBER_AI_BASE_URL", DEFAULT_BASE_URL),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )
    return OpenAiItemProposer(client, values.get("EMBER_AI_MODEL", DEFAULT_MODEL))


class OpenAiLinkProposer:
    """`LinkProposerPort` on the OpenAI SDK, OpenRouter base URL by default."""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def propose_links(
        self, new_item: NewItem, candidates: list[NewItem]
    ) -> LinkProposalResponse:
        """Return the raw provider answer and the proposals checked from it.

        Raise `AiCallFailed` (RELATE-032) when the call fails, and
        `AiResponseSchemaInvalid` (RELATE-033) when the answer cannot be read.
        Temperature is 0.0.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=_link_messages(new_item, candidates),
                temperature=0.0,
            )
        except OpenAIError as exc:
            raise AiCallFailed(
                "ai call fail",
                reason=type(exc).__name__,
                status=getattr(exc, "status_code", "?"),
                detail=_without_secret(str(exc), self._client.api_key),
            ) from exc
        content = _link_content(response)
        return LinkProposalResponse(
            raw_response=content,
            proposals=parse_link_proposals(content),
        )


def build_link_proposer(env: Mapping[str, str] | None = None) -> OpenAiLinkProposer:
    """Build the relate link proposer from env config. Fail fast on a missing key.

    Keys: `EMBER_AI_API_KEY` (or `OPENROUTER_API_KEY`), `EMBER_AI_MODEL`,
    `EMBER_AI_BASE_URL`. Raise `ConfigMissing` (RELATE-035) when no API key is
    configured. The client is built with an explicit timeout and
    `max_retries=0`, so the only retry is the one `propose_links_with_retry`
    owns.
    """
    values = os.environ if env is None else env
    api_key = _first_present(values, _API_KEY_VARS)
    if not api_key:
        raise ConfigMissing("ai api key missing")
    client = OpenAI(
        api_key=api_key,
        base_url=values.get("EMBER_AI_BASE_URL", DEFAULT_BASE_URL),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )
    return OpenAiLinkProposer(
        client, values.get("EMBER_AI_MODEL", DEFAULT_MODEL)
    )


class OpenAiCloseProposer:
    """`CloseProposerPort` on the OpenAI SDK, OpenRouter base URL by default."""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def propose_close(self, candidate: StaleCandidate) -> CloseProposalResponse:
        """Return the raw provider answer and the proposal checked from it.

        Raise `CloseAiCallFailed` (MAINTAIN-018) when the call fails (carries
        `item_id` and the provider status), and `CloseAiSchemaInvalid`
        (MAINTAIN-019) when the answer cannot be read (I9: the raw answer is
        checked at this boundary with `parse_close_proposal`). Temperature is
        0.0. Side effect: one HTTP request to the provider.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=_close_messages(candidate),
                temperature=0.0,
            )
        except OpenAIError as exc:
            raise CloseAiCallFailed(
                "ai call fail",
                item_id=candidate.item_id,
                reason=type(exc).__name__,
                status=getattr(exc, "status_code", "?"),
                detail=_without_secret(str(exc), self._client.api_key),
            ) from exc
        content = _close_content(response, candidate.item_id)
        try:
            proposal = parse_close_proposal(content)
        except CloseAiSchemaInvalid as exc:
            raise CloseAiSchemaInvalid(str(exc), item_id=candidate.item_id) from exc
        return CloseProposalResponse(raw_response=content, proposal=proposal)


def build_close_proposer(env: Mapping[str, str] | None = None) -> OpenAiCloseProposer:
    """Build the maintain close proposer from env config. Fail fast on a
    missing key.

    Keys: `EMBER_AI_API_KEY` (or `OPENROUTER_API_KEY`), `EMBER_AI_MODEL`,
    `EMBER_AI_BASE_URL`. Raise `CloseAiConfigMissing` (MAINTAIN-020) when no
    API key is configured. The client is built with an explicit timeout and
    `max_retries=0`, so the only retry is the one `propose_close_with_retry`
    owns.
    """
    values = os.environ if env is None else env
    api_key = _first_present(values, _API_KEY_VARS)
    if not api_key:
        raise CloseAiConfigMissing("ai api key missing")
    client = OpenAI(
        api_key=api_key,
        base_url=values.get("EMBER_AI_BASE_URL", DEFAULT_BASE_URL),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )
    return OpenAiCloseProposer(
        client, values.get("EMBER_AI_MODEL", DEFAULT_MODEL)
    )


def _close_messages(candidate: StaleCandidate) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": CLOSE_SYSTEM_PROMPT},
        {"role": "user", "content": _close_user_content(candidate)},
    ]


def _close_user_content(candidate: StaleCandidate) -> str:
    """One candidate per call (the pinned user message, step plan 07 §2)."""
    statement = candidate.statement if candidate.statement is not None else ""
    return "\n".join(
        [
            f"Item {candidate.item_id} [{candidate.item_type}]: {statement}",
            (
                f"Newest answers link: link {candidate.newest_answers_link_id}"
                f" from item {candidate.answered_by_item_id},"
                f" confirmed {candidate.newest_answer_created_at}"
            ),
            "Return the judgment as strict JSON.",
        ]
    )


def _close_content(response: Any, item_id: int) -> str:
    """Return the assistant text, or raise MAINTAIN-019 when there is no
    choice."""
    if not response.choices:
        raise CloseAiSchemaInvalid("ai response has no choices", item_id=item_id)
    return response.choices[0].message.content or ""


def _first_present(values: Mapping[str, str], keys: Sequence[str]) -> str | None:
    for key in keys:
        found = values.get(key)
        if found:
            return found
    return None


def _without_secret(detail: str, secret: str | None) -> str:
    """Trim the provider message and strip the API key if it was echoed back."""
    if secret:
        detail = detail.replace(secret, "REDACTED")
    return detail[:200]


def _messages(raw_text: str, context: list[ContextItem]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_content(raw_text, context)},
    ]


def _user_content(raw_text: str, context: list[ContextItem]) -> str:
    lines = ["Raw note:", raw_text, "", "Recent items for context:"]
    if context:
        lines.extend(
            f"- [{item.id}] {item.type.value}: {item.statement}" for item in context
        )
    else:
        lines.append("- (none)")
    lines.extend(["", "Return the items as a JSON list."])
    return "\n".join(lines)


def _content(response: Any) -> str:
    if not response.choices:
        raise AiSchemaError("ai response has no choices")
    return response.choices[0].message.content or ""


def _link_messages(
    new_item: NewItem, candidates: list[NewItem]
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": LINK_SYSTEM_PROMPT},
        {"role": "user", "content": _link_user_content(new_item, candidates)},
    ]


def _link_user_content(new_item: NewItem, candidates: list[NewItem]) -> str:
    lines = [
        f"New item [{new_item.id}] {new_item.type}: {new_item.statement}",
        "",
        "Candidates:",
    ]
    if candidates:
        lines.extend(
            f"- [{item.id}] {item.type}: {item.statement}" for item in candidates
        )
    else:
        lines.append("- (none)")
    lines.extend(["", "Return the proposals as strict JSON."])
    return "\n".join(lines)


def _link_content(response: Any) -> str:
    """Return the assistant text, or raise RELATE-033 when there is no choice."""
    if not response.choices:
        raise AiResponseSchemaInvalid("ai response has no choices")
    return response.choices[0].message.content or ""

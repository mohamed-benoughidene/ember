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

DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"
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

        Raise `AiCallError` (CAPTURE-008) when the provider call fails, and
        `AiSchemaError` (CAPTURE-009) when the answer cannot be read. Side
        effect: one HTTP request to the configured provider.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=_messages(raw_text, context),
            )
        except OpenAIError as exc:
            raise AiCallError("ai call fail") from exc
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


def _first_present(values: Mapping[str, str], keys: Sequence[str]) -> str | None:
    for key in keys:
        found = values.get(key)
        if found:
            return found
    return None


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

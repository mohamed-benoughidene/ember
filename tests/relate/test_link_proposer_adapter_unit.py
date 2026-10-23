"""Unit tests for the relate `OpenAiLinkProposer` adapter, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from openai import OpenAIError

from ember.adapters.llm import OpenAiLinkProposer, build_link_proposer
from ember.relate.errors import AiCallFailed, AiResponseSchemaInvalid, ConfigMissing
from ember.relate.rows import NewItem
from tests.fakes import FIXED_TIME


class _FakeCompletions:
    def __init__(self, *, content=None, error=None):
        self._content = content
        self._error = error

    def create(self, **kwargs):
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


def test_build_link_proposer_missing_key_maps_to_035() -> None:
    with pytest.raises(ConfigMissing) as excinfo:
        build_link_proposer({})

    assert excinfo.value.code == "RELATE-035"

"""Live AI round trip (opt-in: needs an OpenRouter API key).

Skipped unless `EMBER_AI_API_KEY` or `OPENROUTER_API_KEY` is set, so CI stays
offline. Rule T7: assert the schema and the grounding, never the exact wording.

Run it yourself with:  ./.venv/bin/python -m pytest tests/test_capture_live.py -v
"""

from __future__ import annotations

import os

import pytest

from ember.adapters.llm import build_item_proposer
from ember.adapters.sqlite import (
    SqliteAiResponseStore,
    SqliteItemContext,
    SqliteItemGatekeeper,
    SqliteSourceStore,
    open_database,
)
from ember.capture.confirm_write import run_confirm_loop
from ember.capture.item_gatekeeper import (
    GatekeeperRun,
    load_source_text,
    validate_add_item,
    validate_proposals,
)
from ember.capture.item_proposal import (
    ContextMode,
    ItemType,
    build_context,
    propose_items,
)
from ember.capture.source_storage import store_source
from tests.fakes import FakeConfirm

pytestmark = pytest.mark.skipif(
    not (os.environ.get("EMBER_AI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")),
    reason="no OpenRouter API key set",
)

NOTE = (
    "We decided to use SQLite for local storage instead of Postgres, because "
    "this runs on one machine and needs no server. "
    "We assume the team ships a release every week. "
    "Open question: do we still need a backup job?"
)


def test_live_adapter_returns_grounded_proposals() -> None:
    response = build_item_proposer().propose(NOTE, [])

    assert response.raw_response != ""
    assert len(response.batch.proposals) >= 1
    for proposal in response.batch.proposals:
        assert isinstance(proposal.type, ItemType)
        assert proposal.statement.strip() != ""
        assert proposal.source_quote in NOTE
        assert 0.0 <= proposal.confidence <= 1.0


def test_live_pipeline_writes_items_and_keeps_the_raw_answer(db_path) -> None:
    conn = open_database(db_path)
    sources = SqliteSourceStore(conn)
    stored = store_source(sources, NOTE)

    response = propose_items(
        build_item_proposer(),
        raw_text=stored.raw_text,
        context=build_context(SqliteItemContext(conn), ContextMode.B),
    )
    assert len(response.batch.proposals) >= 1
    SqliteAiResponseStore(conn).save(
        source_id=stored.source_id, raw_response=response.raw_response
    )

    gatekeeper = SqliteItemGatekeeper(conn)
    run = GatekeeperRun(
        source_id=stored.source_id,
        source_text=load_source_text(sources, stored.source_id),
        existing=gatekeeper.statements(),
        next_id=gatekeeper.next_item_id,
        clock=gatekeeper.now,
    )
    outcome = validate_proposals(response.batch.proposals, run)
    assert outcome.validated != []

    result = run_confirm_loop(
        outcome.validated,
        confirm=FakeConfirm(["y"] * len(outcome.validated)),
        commit=gatekeeper,
        revalidate=lambda draft: validate_add_item(draft, run),
    )

    assert result.aborted is False
    assert result.accepted_ids == [item.id for item in outcome.validated]
    items = conn.execute("SELECT id, source_id, status FROM items").fetchall()
    assert [row["id"] for row in items] == result.accepted_ids
    assert {row["source_id"] for row in items} == {stored.source_id}
    assert {row["status"] for row in items} == {"Active"}

    raw = conn.execute("SELECT response_text FROM ai_responses").fetchall()
    assert [row["response_text"] for row in raw] == [response.raw_response]
    assert response.raw_response.strip() != ""

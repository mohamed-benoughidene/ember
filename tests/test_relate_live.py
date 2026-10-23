"""Live AI round trip for the Relate link proposer (opt-in: needs an API key).

The `live` marker keeps this file out of a plain pytest run, so a normal suite
never calls the API and never costs money. Run it on purpose with:

    ./.venv/bin/python -m pytest -m live

Rule T7: assert the schema and the write path, never the exact wording.
"""

from __future__ import annotations

import os

import pytest

from ember.adapters.llm import build_link_proposer
from ember.adapters.sqlite import (
    SqliteAiResponseStore,
    SqliteLinkContext,
    SqliteLinkStore,
    open_database,
)
from ember.relate.compat import LINK_TYPES
from ember.relate.link_proposal import LinkProposal
from ember.relate.load_filter import load_item_candidates
from ember.relate.rows import NewItem, RankedCandidate, SignalKind
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate
from tests.fakes import FIXED_TIME, FakeConfirm, insert_item, insert_source

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (
            os.environ.get("EMBER_AI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
        ),
        reason="no OpenRouter API key set",
    ),
]

DECISION = "We store all project data in SQLite."
FINDING_A = "SQLite needs no server and is file-based."
FINDING_B = "The prototype ran 10x faster after switching to SQLite."


def test_live_proposer_returns_schema_valid_proposals() -> None:
    proposer = build_link_proposer()
    new_item = NewItem(
        id=1, type="Decision", statement=DECISION, created_at=FIXED_TIME
    )
    candidates = [
        NewItem(id=2, type="Finding", statement=FINDING_A, created_at=FIXED_TIME),
        NewItem(id=3, type="Finding", statement=FINDING_B, created_at=FIXED_TIME),
    ]

    response = proposer.propose_links(new_item, candidates)

    assert response.raw_response.strip() != ""
    for proposal in response.proposals:
        assert isinstance(proposal, LinkProposal)
        assert proposal.link_type in LINK_TYPES
        assert proposal.target_item_id in {2, 3}


def test_live_relate_pipeline_writes_a_link_and_keeps_the_raw_answer(
    db_path,
) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=1, item_type="Decision",
            statement=DECISION,
        )
        insert_item(
            conn, source_id=source_id, item_id=2, item_type="Finding",
            statement=FINDING_A,
        )
        insert_item(
            conn, source_id=source_id, item_id=3, item_type="Finding",
            statement=FINDING_B,
        )
        conn.commit()

        lookup = SqliteLinkContext(conn)
        loaded = load_item_candidates(lookup, item_id=1, db_path=db_path)
        ranked = [
            RankedCandidate(item=item, cosine=1.0, source=SignalKind.dense)
            for item in loaded.universe.items
        ]

        ports = RelatePorts(
            link_lookup=lookup,
            link_store=SqliteLinkStore(conn),
            link_proposer=build_link_proposer(),
            ai_response_store=SqliteAiResponseStore(conn),
            confirm=FakeConfirm(["y"] * len(ranked)),
        )
        request = RelateRequest(
            new_item=loaded.new_item, ranked=ranked, env=os.environ
        )

        result = run_relate(ports, request)

        assert result.aborted is False

        raw = conn.execute(
            "SELECT item_id, response_text FROM ai_responses"
        ).fetchall()
        assert len(raw) == 1
        assert raw[0]["item_id"] == 1
        assert raw[0]["response_text"].strip() != ""

        statuses = [
            row["status"] for row in conn.execute("SELECT status FROM links")
        ]
        assert all(status in {"Confirmed", "Rejected"} for status in statuses)
        if result.accepted:
            confirmed = conn.execute(
                "SELECT COUNT(*) FROM links WHERE status = 'Confirmed'"
            ).fetchone()[0]
            assert confirmed == len(result.accepted)
    finally:
        conn.close()

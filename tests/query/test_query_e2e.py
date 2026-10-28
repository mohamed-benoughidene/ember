"""The query engine's one end-to-end test (L2 §7.6).

Runs the whole house chain on a single temp database with every outside tool
faked: `FakeItemProposer` for Capture's model, `FakeLinkProposer` for
Relate's, and `FakeConfirm` for the user. Then it asserts the JSON of all four
query commands against that same database, and that the query phase left the
file untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ember.adapters.sqlite import (
    SqliteItemGatekeeper,
    SqliteItemContext,
    SqliteLinkContext,
    SqliteLinkStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    SqliteQueryContext,
    SqliteSourceStore,
    build_ai_response_store,
    open_database,
    open_query_database,
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
    ItemProposal,
    ItemType,
    ProposalBatch,
    ProposalResponse,
    build_context,
    propose_items,
)
from ember.capture.source_storage import store_source
from ember.maintain.run_maintain import MaintainPorts, MaintainRequest, run_sweep
from ember.query.run_query import (
    run_current_state,
    run_history,
    run_topic_search,
    run_why,
)
from ember.relate.link_proposal import LinkProposal, LinkProposalResponse
from ember.relate.rows import NewItem, RankedCandidate, SignalKind
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate
from tests.fakes import FIXED_TIME, FakeConfirm, FakeItemProposer
from tests.relate.fakes import FakeLinkProposer

RAW_TEXT = (
    "We decided to use SQLite for local storage. "
    "We decided to use Postgres instead. "
    "The benchmark ran in 12ms."
)

PROPOSALS = ProposalBatch(
    proposals=[
        ItemProposal(
            type=ItemType.DECISION,
            statement="Use SQLite for local storage",
            source_quote="decided to use SQLite for local storage",
            confidence=0.9,
        ),
        ItemProposal(
            type=ItemType.DECISION,
            statement="Use Postgres instead",
            source_quote="decided to use Postgres instead",
            confidence=0.9,
        ),
        ItemProposal(
            type=ItemType.FINDING,
            statement="The benchmark ran in 12ms",
            source_quote="benchmark ran in 12ms",
            confidence=0.9,
        ),
    ],
    dropped=[],
)


def _hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run_capture(conn) -> None:
    """Phase 1-4 for Capture, with the AI faked."""
    sources = SqliteSourceStore(conn, clock=lambda: FIXED_TIME)
    stored = store_source(sources, RAW_TEXT)
    proposer = FakeItemProposer(
        [ProposalResponse(raw_response="raw", batch=PROPOSALS)]
    )
    response = propose_items(
        proposer,
        raw_text=stored.raw_text,
        context=build_context(SqliteItemContext(conn), ContextMode.B),
    )
    gatekeeper = SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME)
    run = GatekeeperRun(
        source_id=stored.source_id,
        source_text=load_source_text(sources, stored.source_id),
        existing=gatekeeper.statements(),
        next_id=gatekeeper.next_item_id,
        clock=lambda: FIXED_TIME,
    )
    outcome = validate_proposals(response.batch.proposals, run)
    run_confirm_loop(
        outcome.validated,
        confirm=FakeConfirm(["y", "y", "y"]),
        commit=gatekeeper,
        revalidate=lambda draft: validate_add_item(draft, run),
    )


def _run_relate(conn, new_item_id: int, proposals) -> None:
    """Phase 3-4 for Relate, with the AI and the user faked."""
    ports = RelatePorts(
        link_lookup=SqliteLinkContext(conn),
        link_store=SqliteLinkStore(conn),
        link_proposer=FakeLinkProposer(
            [
                LinkProposalResponse(
                    raw_response="raw", proposals=list(proposals)
                )
            ]
        ),
        ai_response_store=build_ai_response_store(conn),
        confirm=FakeConfirm(["y"] * len(proposals)),
    )
    request = RelateRequest(
        new_item=NewItem(
            id=new_item_id,
            type="Decision",
            statement="Use Postgres instead",
            created_at=FIXED_TIME,
        ),
        ranked=[
            RankedCandidate(
                item=NewItem(
                    id=proposal.target_item_id,
                    type="Decision",
                    statement="s",
                    created_at=FIXED_TIME,
                ),
                cosine=1.0,
                source=SignalKind.dense,
            )
            for proposal in proposals
        ],
        env={},
    )
    run_relate(ports, request)


def _run_maintain(conn) -> None:
    """The sweep: derive the status changes and write them."""
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
    )
    run_sweep(ports, MaintainRequest())


def test_the_house_chain_then_all_four_query_commands(db_path) -> None:
    conn = open_database(db_path)
    try:
        _run_capture(conn)
        _run_relate(
            conn,
            2,
            [
                LinkProposal(target_item_id=1, link_type="depends_on"),
                LinkProposal(target_item_id=3, link_type="depends_on"),
                LinkProposal(target_item_id=1, link_type="supersedes"),
            ],
        )
        _run_maintain(conn)
        conn.commit()
    finally:
        conn.close()

    before = _hash(db_path)
    conn = open_query_database(db_path)
    try:
        context = SqliteQueryContext(conn)
        current_state = json.loads(run_current_state(context))
        search = json.loads(run_topic_search(context, "sqlite"))
        explanation = json.loads(run_why(context, 2))
        item_history = json.loads(run_history(context, 1))
        global_history = json.loads(run_history(context, None))
    finally:
        conn.close()

    # Item 1 was superseded by item 2 and closed. Item 2 was challenged as a
    # dependent of item 1. Item 3 stays Active.
    assert current_state["count"] == 2
    assert [item["id"] for item in current_state["items"]] == [2, 3]
    assert current_state["items"][0]["challenged"] is True

    # The Closed item is still findable by search, with its status visible.
    assert [hit["item_id"] for hit in search["results"]] == [1]
    assert search["results"][0]["status"] == "Closed"

    # Both reasons, both direct, in item_id order.
    assert [reason["item_id"] for reason in explanation["reasons"]] == [1, 3]
    assert all(reason["depth"] == 1 for reason in explanation["reasons"])

    # Item 1's history covers its own close and the link that caused it.
    assert "status_changed" in [event["kind"] for event in item_history["events"]]
    assert item_history["count"] <= global_history["count"]

    # The query phase changed nothing on disk.
    assert _hash(db_path) == before

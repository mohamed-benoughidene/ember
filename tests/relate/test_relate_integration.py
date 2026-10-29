"""End-to-end integration tests for `run_relate` on a real SQLite DB.

Phase 3 (propose), Phase 3.5 (raw answer save), the pure gatekeeper and Phase 4
(the confirm loop plus the atomic `links` / `change_log` write) all run against
real `SqliteLinkContext`, `SqliteLinkStore` and `SqliteAiResponseStore` adapters,
with a scripted `FakeConfirm` standing in for the user.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ember.adapters.sqlite import (
    SqliteAiResponseStore,
    SqliteLinkContext,
    SqliteLinkStore,
    SqliteMaintainStore,
    open_database,
    open_maintain_database,
)
from ember.maintain.rows import StatusChange
from ember.relate.ai_response_store import AiResponseStorePort
from ember.relate.errors import (
    AiResponseWriteFailed,
    ChangeLogWriteFailed,
    LinkWriteFailed,
)
from ember.relate.link_gatekeeper import (
    LinkDraft,
    RejectedLink,
    ValidatedLink,
    validate_add_link,
)
from ember.relate.link_proposal import LinkProposal, LinkProposalResponse
from ember.relate.rows import ChangeLogEntry, Link, NewItem, RankedCandidate, SignalKind
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate
from tests.fakes import (
    FIXED_TIME,
    FakeConfirm,
    insert_item,
    insert_link,
    insert_source,
)
from tests.relate.fakes import FakeAiResponseStore, FakeLinkProposer


def _item(i: int, t: str = "Decision") -> NewItem:
    return NewItem(id=i, type=t, statement=f"s{i}", created_at=FIXED_TIME)


def _ranked(*ids: int) -> list[RankedCandidate]:
    return [
        RankedCandidate(item=_item(i), cosine=1.0, source=SignalKind.dense)
        for i in ids
    ]


def _proposer(ids: list[int], link_type: str = "depends_on") -> FakeLinkProposer:
    return FakeLinkProposer(
        [
            LinkProposalResponse(
                raw_response="raw",
                proposals=[
                    LinkProposal(target_item_id=i, link_type=link_type)
                    for i in ids
                ],
            )
        ]
    )


def _seed(
    db_path: str, ids: list[int]
) -> tuple[sqlite3.Connection, int]:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    for i in ids:
        insert_item(conn, source_id=source_id, item_id=i, item_type="Decision")
    conn.commit()
    return conn, source_id


def _ports(
    conn: sqlite3.Connection,
    proposer: FakeLinkProposer,
    confirm: FakeConfirm,
    ai_store: AiResponseStorePort | None = None,
) -> RelatePorts:
    return RelatePorts(
        link_lookup=SqliteLinkContext(conn),
        link_store=SqliteLinkStore(conn),
        link_proposer=proposer,
        ai_response_store=ai_store or SqliteAiResponseStore(conn),
        confirm=confirm,
    )


def _request(new_item_id: int, *targets: int) -> RelateRequest:
    return RelateRequest(
        new_item=_item(new_item_id),
        ranked=_ranked(*targets),
        env={},
    )


def test_happy_path_writes_confirmed_links(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3, 4])
    try:
        ports = _ports(conn, _proposer([2, 3, 4]), FakeConfirm(["y", "y", "y"]))

        result = run_relate(ports, _request(1, 2, 3, 4))

        assert len(result.accepted) == 3
        assert result.rejected == 0
        assert result.skipped == 0
        assert result.aborted is False

        statuses = [row["status"] for row in conn.execute("SELECT status FROM links")]
        assert statuses == ["Confirmed", "Confirmed", "Confirmed"]

        confirmed = conn.execute(
            "SELECT COUNT(*) FROM change_log"
            " WHERE field_changed = 'link_confirmed'"
            " AND trigger_cause = 'user_confirmed'"
        ).fetchone()[0]
        assert confirmed == 3

        link_ids = {row["id"] for row in conn.execute("SELECT id FROM links")}
        log_rows = conn.execute("SELECT link_id FROM change_log").fetchall()
        assert log_rows
        assert all(
            row["link_id"] is not None and row["link_id"] in link_ids
            for row in log_rows
        )

        responses = conn.execute(
            "SELECT COUNT(*) FROM ai_responses WHERE item_id = 1"
        ).fetchone()[0]
        assert responses == 1
    finally:
        conn.close()


def test_rejection_is_negative_memory(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3, 4])
    try:
        ports = _ports(conn, _proposer([2, 3, 4]), FakeConfirm(["n", "n", "y"]))

        result = run_relate(ports, _request(1, 2, 3, 4))

        assert result.rejected == 2
        assert len(result.accepted) == 1

        pairs = {
            (row["status"], row["target_item_id"])
            for row in conn.execute("SELECT status, target_item_id FROM links")
        }
        assert len(pairs) == 3
        assert ("Rejected", 2) in pairs
        assert ("Rejected", 3) in pairs
        assert ("Confirmed", 4) in pairs

        rejected = conn.execute(
            "SELECT COUNT(*) FROM change_log WHERE field_changed = 'link_rejected'"
        ).fetchone()[0]
        confirmed = conn.execute(
            "SELECT COUNT(*) FROM change_log WHERE field_changed = 'link_confirmed'"
        ).fetchone()[0]
        assert rejected == 2
        assert confirmed == 1

        existing = SqliteLinkContext(conn).existing_link_types(1)
        assert "depends_on" in existing.get(2, set())
        assert "depends_on" in existing.get(3, set())
    finally:
        conn.close()


def test_abort_after_two_writes_two_rows(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3, 4, 5, 6])
    try:
        ports = _ports(
            conn, _proposer([2, 3, 4, 5, 6]), FakeConfirm(["y", "n", "q"])
        )

        result = run_relate(ports, _request(1, 2, 3, 4, 5, 6))

        assert result.aborted is True
        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 2
        statuses = sorted(
            row["status"] for row in conn.execute("SELECT status FROM links")
        )
        assert statuses == ["Confirmed", "Rejected"]
    finally:
        conn.close()


def test_gatekeeper_rejection_counted(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3, 4])
    try:
        proposer = FakeLinkProposer(
            [
                LinkProposalResponse(
                    raw_response="raw",
                    proposals=[
                        LinkProposal(target_item_id=2, link_type="depends_on"),
                        LinkProposal(target_item_id=3, link_type="bogus"),
                        LinkProposal(target_item_id=4, link_type="depends_on"),
                    ],
                )
            ]
        )
        ports = _ports(conn, proposer, FakeConfirm(["y", "y"]))

        result = run_relate(ports, _request(1, 2, 3, 4))

        assert result.rejected == 1
        assert len(result.accepted) == 2
        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 2
    finally:
        conn.close()


def test_phase35_failure_rolls_back(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3])
    try:
        ports = _ports(
            conn,
            _proposer([2, 3]),
            FakeConfirm(["y", "y"]),
            ai_store=FakeAiResponseStore(error=RuntimeError("disk")),
        )

        with pytest.raises(AiResponseWriteFailed):
            run_relate(ports, _request(1, 2, 3))

        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
    finally:
        conn.close()


def test_phase35_real_adapter_failure_maps_to_036(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3])
    try:
        conn.execute("ALTER TABLE ai_responses RENAME TO ai_responses_bak")
        conn.commit()
        ports = _ports(conn, _proposer([2, 3]), FakeConfirm(["y", "y"]))

        with pytest.raises(AiResponseWriteFailed) as excinfo:
            run_relate(ports, _request(1, 2, 3))

        assert excinfo.value.code == "RELATE-036"
    finally:
        conn.close()


def test_link_store_fk_failure_maps_to_029(db_path) -> None:
    conn, _ = _seed(db_path, [1])
    try:
        store = SqliteLinkStore(conn)
        link = Link(id=None, source_item_id=1, target_item_id=999,
                    link_type="depends_on", status="Confirmed", created_at=FIXED_TIME)
        log = ChangeLogEntry(id=None, item_id=1, link_id=None,
                             field_changed="link_confirmed", new_value="depends_on:999",
                             timestamp=FIXED_TIME, trigger_cause="user_confirmed")

        with pytest.raises(LinkWriteFailed) as excinfo:
            store.insert_link_with_log(link, log)

        assert excinfo.value.code == "RELATE-029"
        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
    finally:
        conn.close()


def test_rerun_does_not_recreate_or_duplicate(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3, 4])
    try:
        first = run_relate(_ports(conn, _proposer([2, 3, 4]), FakeConfirm(["n", "n", "y"])), _request(1, 2, 3, 4))
        assert first.rejected == 2 and len(first.accepted) == 1

        second = run_relate(_ports(conn, _proposer([2, 3, 4]), FakeConfirm(["y", "y", "y"])), _request(1, 2, 3, 4))

        assert second.accepted == []
        assert second.rejected == 3
        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 3
    finally:
        conn.close()


def test_atomic_write_rolls_back_on_log_failure(db_path) -> None:
    conn, _ = _seed(db_path, [1, 2, 3])
    try:
        conn.execute("ALTER TABLE change_log RENAME TO change_log_bak")
        conn.commit()

        ports = _ports(conn, _proposer([2, 3]), FakeConfirm(["y"]))

        with pytest.raises(ChangeLogWriteFailed):
            run_relate(ports, _request(1, 2, 3))

        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
    finally:
        conn.close()


def test_corrective_inverse_commits_after_reversal(db_path) -> None:
    Path(db_path).touch()  # open_maintain_database requires an existing file
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        insert_item(
            conn,
            source_id=source_id,
            item_id=2,
            item_type="Decision",
            status="Closed",
            close_reason="superseded",
        )
        reversed_id = insert_link(conn, 1, 2, "supersedes")
        conn.commit()

        # The write half (step 02): undo the supersedes through the maintain
        # store, which pairs the item restore with the `reversed_at` column.
        SqliteMaintainStore(conn, clock=lambda: FIXED_TIME).apply_reversal(
            StatusChange(
                item_id=2,
                old_status="Closed",
                new_status="Active",
                close_reason=None,
                old_close_reason="superseded",
                trigger_cause="reversal",
                link_id=reversed_id,
            ),
            ChangeLogEntry(
                item_id=2,
                link_id=reversed_id,
                field_changed="link_reversed",
                old_value="Confirmed",
                new_value="Reversed",
                timestamp="",
                trigger_cause="reversal",
            ),
        )
        conn.commit()

        lookup = SqliteLinkContext(conn)

        # The UNIQUE triple still stands (#15 keep the block): re-proposing
        # the reversed triple is a RELATE-009 duplicate that names the state.
        duplicate = validate_add_link(
            LinkDraft(source_item_id=1, target_item_id=2, link_type="supersedes"),
            lookup,
        )
        assert isinstance(duplicate, RejectedLink)
        assert duplicate.code == "RELATE-009"
        assert duplicate.detail is not None
        assert str(reversed_id) in duplicate.detail
        assert "reversed" in duplicate.detail

        corrective = validate_add_link(
            LinkDraft(source_item_id=2, target_item_id=1, link_type="supersedes"),
            lookup,
        )
        assert isinstance(corrective, ValidatedLink)
        # The write commits where it was rejected before step 3.
        assert SqliteLinkStore(conn).insert_link_with_log(
            corrective.link_row, corrective.change_log_row
        ) == reversed_id + 1
    finally:
        conn.close()

"""Integration: the three human commands against a real SQLite DB (T4).

Each test drives one of `run_close_item` / `run_set_status` /
`run_reverse_supersedes` through `open_maintain_database`, so foreign keys are
ON (Constitution T10). The graphs are `compat.py`-legal, and every assertion
reads the real `items` / `change_log` / `links` rows.
"""

from __future__ import annotations

from pathlib import Path

from ember.adapters.sqlite import (
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    MaintainResult,
    run_close_item,
    run_reverse_supersedes,
    run_set_status,
    run_sweep,
)
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source


def _open(db_path: str):
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _ports(conn) -> MaintainPorts:
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
    )


def _status(conn, item_id: int) -> tuple[str, str | None, str]:
    row = conn.execute(
        "SELECT status, close_reason, status_origin FROM items WHERE id = ?",
        (item_id,),
    ).fetchone()
    return (row["status"], row["close_reason"], row["status_origin"])


def _log(conn) -> list[tuple]:
    return [
        (
            row["item_id"],
            row["link_id"],
            row["field_changed"],
            row["old_value"],
            row["new_value"],
            row["trigger_cause"],
            row["timestamp"],
        )
        for row in conn.execute(
            "SELECT item_id, link_id, field_changed, old_value, new_value,"
            " trigger_cause, timestamp FROM change_log ORDER BY id"
        )
    ]


def test_close_item_writes_close_and_dependent_challenge_in_one_batch(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision",
                    statement="A")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Decision",
                    statement="B")
        link_id = insert_link(conn, 2, 1, "depends_on")
        conn.commit()

        result = run_close_item(
            _ports(conn), MaintainRequest(item_id=1, reason="invalidated")
        )

        assert isinstance(result, MaintainResult)
        assert result.applied == 2
        assert result.total_items == 2
        assert _status(conn, 1) == ("Closed", "invalidated", "derived")
        assert _status(conn, 2) == ("Challenged", None, "derived")
        assert _log(conn) == [
            (1, None, "status", "Active", "Closed:invalidated",
             "user_closed", FIXED_TIME),
            (2, link_id, "status", "Active", "Challenged",
             "dependency_closed", FIXED_TIME),
        ]
    finally:
        conn.close()


def test_close_item_does_not_shield(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        conn.commit()

        result = run_close_item(
            _ports(conn), MaintainRequest(item_id=1, reason="expired")
        )

        assert result.applied == 1
        assert _status(conn, 1) == ("Closed", "expired", "derived")
        assert all(row[2] != "status_origin" for row in _log(conn))
    finally:
        conn.close()


def test_set_status_active_clears_challenge_shields_and_blocks_resweep(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Finding",
                    statement="Source")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Finding",
                    statement="Contradicted", status="Challenged")
        insert_link(conn, 1, 2, "contradicts")
        conn.commit()

        result = run_set_status(
            _ports(conn), MaintainRequest(item_id=2, to_status="Active")
        )

        assert result.applied == 1
        assert _status(conn, 2) == ("Active", None, "manual")
        logs = _log(conn)
        assert (2, None, "status", "Challenged", "Active",
                "user_set_status", FIXED_TIME) in logs
        assert (2, None, "status_origin", "derived", "manual",
                "user_set_status", FIXED_TIME) in logs

        second = run_sweep(_ports(conn), MaintainRequest())

        assert second.applied == 0
        assert _status(conn, 2) == ("Active", None, "manual")
    finally:
        conn.close()


def test_set_status_challenged_does_not_shield(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        conn.commit()

        result = run_set_status(
            _ports(conn), MaintainRequest(item_id=1, to_status="Challenged")
        )

        assert result.applied == 1
        assert _status(conn, 1) == ("Challenged", None, "derived")
        assert all(row[2] != "status_origin" for row in _log(conn))
    finally:
        conn.close()


def test_set_status_noop_writes_nothing(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision",
                    status="Active")
        conn.commit()

        result = run_set_status(
            _ports(conn), MaintainRequest(item_id=1, to_status="Active")
        )

        assert result.applied == 0
        assert result.changed == []
        assert _status(conn, 1) == ("Active", None, "derived")
        assert _log(conn) == []
    finally:
        conn.close()


def test_close_item_on_challenged_item_closes_it(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision",
                    status="Challenged")
        conn.commit()

        result = run_close_item(
            _ports(conn), MaintainRequest(item_id=1, reason="invalidated")
        )

        assert result.applied == 1
        assert _status(conn, 1) == ("Closed", "invalidated", "derived")
    finally:
        conn.close()


def _seed_reversal_graph(conn) -> int:
    """Seed: 2 supersedes 1, 3 depends_on 1. Return the supersedes link id."""
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Decision",
                statement="Old")
    insert_item(conn, source_id=source_id, item_id=2, item_type="Decision",
                statement="New")
    insert_item(conn, source_id=source_id, item_id=3, item_type="Decision",
                statement="Dependent")
    supersedes_id = insert_link(conn, 2, 1, "supersedes")
    insert_link(conn, 3, 1, "depends_on")
    conn.commit()
    return supersedes_id


def test_reverse_supersedes_restores_item_and_appends_two_rows(db_path) -> None:
    conn = _open(db_path)
    try:
        supersedes_id = _seed_reversal_graph(conn)
        sweep = run_sweep(_ports(conn), MaintainRequest())
        assert sweep.applied == 2
        assert _status(conn, 1) == ("Closed", "superseded", "derived")
        assert _status(conn, 3)[0] == "Challenged"
        before = _log(conn)

        result = run_reverse_supersedes(
            _ports(conn), MaintainRequest(item_id=1, link_id=supersedes_id)
        )

        assert isinstance(result, MaintainResult)
        assert result.applied == 1
        assert result.reopened == 1
        assert _status(conn, 1) == ("Active", None, "derived")

        logs = _log(conn)
        assert len(logs) == len(before) + 2
        assert logs[-2:] == [
            (1, supersedes_id, "status", "Closed:superseded", "Active",
             "reversal", FIXED_TIME),
            (1, supersedes_id, "link_reversed", "Confirmed", "Reversed",
             "reversal", FIXED_TIME),
        ]

        assert _status(conn, 3)[0] == "Challenged"

        link = conn.execute(
            "SELECT status FROM links WHERE id = ?", (supersedes_id,)
        ).fetchone()
        assert link["status"] == "Confirmed"
    finally:
        conn.close()


def test_reversal_does_not_veto_a_new_supersedes_close(db_path) -> None:
    conn = _open(db_path)
    try:
        supersedes_id = _seed_reversal_graph(conn)
        run_sweep(_ports(conn), MaintainRequest())
        run_reverse_supersedes(
            _ports(conn), MaintainRequest(item_id=1, link_id=supersedes_id)
        )
        assert _status(conn, 1) == ("Active", None, "derived")

        source_id = conn.execute("SELECT source_id FROM items WHERE id = 1").fetchone()[
            "source_id"
        ]
        insert_item(conn, source_id=source_id, item_id=4, item_type="Decision",
                    statement="Newer")
        insert_link(conn, 4, 1, "supersedes")
        conn.commit()

        result = run_sweep(_ports(conn), MaintainRequest())

        assert result.applied == 1
        assert _status(conn, 1) == ("Closed", "superseded", "derived")
    finally:
        conn.close()

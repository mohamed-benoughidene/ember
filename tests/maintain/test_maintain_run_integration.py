"""Integration tests: the sweep against a real SQLite DB (T4).

The graph is `compat.py`-legal: a Decision `supersedes` a Decision, a Decision
`answers` a Question, a Finding `contradicts` a Finding. One sweep must write the
exact `items` values and the exact `change_log` rows; a second sweep writes none.
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
    run_sweep,
)
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source


def _seed(db_path: str) -> None:
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=1, item_type="Decision",
            statement="Use SQLite",
        )
        insert_item(
            conn, source_id=source_id, item_id=2, item_type="Decision",
            statement="Use Postgres",
        )
        insert_item(
            conn, source_id=source_id, item_id=3, item_type="Question",
            statement="Which DB?",
        )
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Finding",
            statement="Latency high",
        )
        insert_item(
            conn, source_id=source_id, item_id=5, item_type="Finding",
            statement="Latency low",
        )
        insert_link(conn, 2, 1, "supersedes")
        insert_link(conn, 1, 3, "answers")
        insert_link(conn, 4, 5, "contradicts")
        conn.commit()
    finally:
        conn.close()


def _ports(conn) -> MaintainPorts:
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
    )


def _items_state(conn) -> dict[int, tuple[str, str | None]]:
    return {
        row["id"]: (row["status"], row["close_reason"])
        for row in conn.execute("SELECT id, status, close_reason FROM items")
    }


def _log_rows(conn) -> list[tuple]:
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


def test_sweep_writes_exact_status_and_change_log_rows(db_path) -> None:
    _seed(db_path)
    conn = open_maintain_database(db_path)
    try:
        result = run_sweep(_ports(conn), MaintainRequest())

        assert isinstance(result, MaintainResult)
        assert result.applied == len(result.changed) == 3
        assert result.reopened == 0
        assert result.total_items == 5

        assert _items_state(conn) == {
            1: ("Closed", "superseded"),
            2: ("Active", None),
            3: ("Closed", "answered"),
            4: ("Active", None),
            5: ("Challenged", None),
        }
        assert _log_rows(conn) == [
            (1, 1, "status", "Active", "Closed:superseded",
             "supersedes_confirmed", FIXED_TIME),
            (3, 2, "status", "Active", "Closed:answered",
             "answers_confirmed", FIXED_TIME),
            (5, 3, "status", "Active", "Challenged",
             "contradicts_confirmed", FIXED_TIME),
        ]
    finally:
        conn.close()


def test_second_sweep_writes_no_new_rows(db_path) -> None:
    _seed(db_path)
    conn = open_maintain_database(db_path)
    try:
        first = run_sweep(_ports(conn), MaintainRequest())
        assert first.applied == len(first.changed) == 3
        assert first.total_items == 5
        after_items = _items_state(conn)
        after_logs = _log_rows(conn)

        second = run_sweep(_ports(conn), MaintainRequest())

        assert second.applied == 0
        assert second.changed == []
        assert second.total_items == 5
        assert _items_state(conn) == after_items
        assert _log_rows(conn) == after_logs
    finally:
        conn.close()

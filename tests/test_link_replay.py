"""Replay tests (hardening step 02): the column is the ledger (L2 §6, §13).

`replay_reversals` is pure: ledger rows in, mapping out, no clock, no I/O
(Constitution T1). The live-equality test drives a real reversal through
`run_reverse_supersedes` on a real v11 database, so the replay is compared to
what the pairing write actually stamped (Constitution T4).
"""

from __future__ import annotations

from pathlib import Path

from ember.adapters.link_replay import replay_reversals
from ember.adapters.sqlite import (
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    run_reverse_supersedes,
    run_sweep,
)
from ember.query.rows import ChangeRow
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source


def _entry(
    entry_id: int,
    link_id: int | None,
    *,
    field_changed: str = "link_reversed",
    timestamp: str = FIXED_TIME,
    item_id: int | None = 1,
) -> ChangeRow:
    """Build one already-validated ledger row shape."""
    return ChangeRow(
        id=entry_id,
        item_id=item_id,
        link_id=link_id,
        field_changed=field_changed,
        old_value=None,
        new_value=None,
        timestamp=timestamp,
        trigger_cause="reversal" if field_changed == "link_reversed" else "test",
    )


def test_replay_reversals_matches_live_column(db_path) -> None:
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="old")
        insert_item(conn, source_id=source_id, item_id=2, statement="new")
        insert_item(conn, source_id=source_id, item_id=3, statement="dependent")
        supersedes_id = insert_link(conn, 2, 1, "supersedes")
        depends_id = insert_link(conn, 3, 1, "depends_on")
        conn.commit()
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
        )
        run_sweep(ports, MaintainRequest())
        run_reverse_supersedes(
            ports, MaintainRequest(item_id=1, link_id=supersedes_id)
        )

        ledger = [
            ChangeRow(
                id=row["id"],
                item_id=row["item_id"],
                link_id=row["link_id"],
                field_changed=row["field_changed"],
                old_value=row["old_value"],
                new_value=row["new_value"],
                timestamp=row["timestamp"],
                trigger_cause=row["trigger_cause"],
            )
            for row in conn.execute(
                "SELECT id, item_id, link_id, field_changed, old_value,"
                " new_value, timestamp, trigger_cause FROM change_log ORDER BY id"
            )
        ]
        replay = replay_reversals(ledger)

        live = {
            row["id"]: row["reversed_at"]
            for row in conn.execute("SELECT id, reversed_at FROM links")
        }
        # One link reversed with the shared clock stamp, one link live.
        assert live[supersedes_id] == FIXED_TIME
        assert live[depends_id] is None
        for link_id, reversed_at in live.items():
            assert replay.get(link_id) == reversed_at, f"link {link_id}"
    finally:
        conn.close()


def test_replay_last_marker_wins_on_clock_tie() -> None:
    first = _entry(10, 5, timestamp="2026-01-01T00:00:00+00:00")
    second = _entry(11, 5, timestamp="2026-01-01T00:00:00+00:00")

    assert replay_reversals([first, second]) == {
        5: "2026-01-01T00:00:00+00:00"
    }


def test_replay_highest_id_wins_regardless_of_input_order() -> None:
    first = _entry(10, 5, timestamp="2026-01-01T00:00:00+00:00")
    second = _entry(11, 5, timestamp="2026-01-02T00:00:00+00:00")

    assert replay_reversals([second, first]) == {5: "2026-01-02T00:00:00+00:00"}


def test_replay_returns_none_for_link_without_marker() -> None:
    status_only = _entry(
        10, 5, field_changed="status", timestamp="2026-01-01T00:00:00+00:00"
    )

    assert replay_reversals([status_only]) == {5: None}


def test_replay_skips_rows_without_a_link_id() -> None:
    item_only = _entry(10, None, field_changed="created")

    assert replay_reversals([item_only]) == {}

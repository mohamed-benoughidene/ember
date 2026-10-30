"""Group stamping: the six human actions share one group id (undo step 01).

Each test drives a real `SqliteMaintainStore` / `SqliteItemGatekeeper` through
the engine entry points on a real temp DB (T4). The seed patterns follow
`tests/maintain/test_maintain_commands_integration.py`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.adapters.sqlite import (
    SqliteGroupIdPort,
    SqliteItemGatekeeper,
    SqliteLinkStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_database,
    open_maintain_database,
)
from ember.capture.item_gatekeeper import ValidatedItem
from ember.cli import main
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    run_close_item,
    run_edit_item,
    run_remove_link,
    run_reverse_supersedes,
    run_set_status,
    run_sweep,
)
from ember.relate.rows import ChangeLogEntry, Link
from tests.fakes import (
    FIXED_TIME,
    insert_item,
    insert_link,
    insert_source,
)


def _open(db_path: str):
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _ports(conn) -> MaintainPorts:
    """Real ports with the group-id port injected, one fixed clock read."""
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
        group_ids=SqliteGroupIdPort(conn),
    )


def _groups(conn) -> list[tuple[str, str, int | None]]:
    """(field_changed, trigger_cause, group_id) per ledger row, id order."""
    return [
        (row["field_changed"], row["trigger_cause"], row["group_id"])
        for row in conn.execute(
            "SELECT field_changed, trigger_cause, group_id FROM change_log"
            " ORDER BY id"
        )
    ]


# Ports with NO group-id port: exactly what the sweep writes through. Used to
# prove the sweep-equivalent call path leaves the column NULL.
def _sweep_ports(conn) -> MaintainPorts:
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
    )


def test_close_item_stamps_close_and_dependency_closed_rows_with_one_group(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="A")
        insert_item(conn, source_id=source_id, item_id=2, statement="B")
        insert_link(conn, 2, 1, "depends_on")
        conn.commit()

        run_close_item(_ports(conn), MaintainRequest(item_id=1, reason="invalidated"))

        assert _groups(conn) == [
            ("status", "user_closed", 1),
            ("status", "dependency_closed", 1),
        ]
    finally:
        conn.close()


def test_set_status_stamps_both_its_transactions_with_the_same_group(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, status="Challenged")
        conn.commit()

        run_set_status(
            _ports(conn), MaintainRequest(item_id=1, to_status="Active")
        )

        # The TWO transactions (status batch, then the shield write) share
        # ONE group id; the items row really was shielded.
        assert _groups(conn) == [
            ("status", "user_set_status", 1),
            ("status_origin", "user_set_status", 1),
        ]
        status_origin = conn.execute(
            "SELECT status_origin FROM items WHERE id = 1"
        ).fetchone()["status_origin"]
        assert status_origin == "manual"
    finally:
        conn.close()


def test_edit_item_stamps_one_group(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        conn.commit()

        run_edit_item(
            _ports(conn),
            MaintainRequest(item_id=1, field="rationale", value="why not"),
        )

        assert _groups(conn) == [("rationale", "user_edit_item", 1)]
    finally:
        conn.close()


def test_remove_link_stamps_one_group(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        insert_item(conn, source_id=source_id, item_id=2)
        link_id = insert_link(conn, 1, 2, "depends_on")
        conn.commit()

        run_remove_link(_ports(conn), MaintainRequest(link_id=link_id))

        assert _groups(conn) == [("link_removed", "user_remove_link", 1)]
        status = conn.execute(
            "SELECT status FROM links WHERE id = ?", (link_id,)
        ).fetchone()["status"]
        assert status == "Rejected"
    finally:
        conn.close()


def test_reverse_supersedes_stamps_status_and_marker_with_one_group(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="Old")
        insert_item(conn, source_id=source_id, item_id=2, statement="New")
        insert_item(conn, source_id=source_id, item_id=3, statement="Dependent")
        supersedes_id = insert_link(conn, 2, 1, "supersedes")
        insert_link(conn, 3, 1, "depends_on")
        conn.commit()
        # The sweep closes item 1 first (supersedes), so the reversal has a
        # real superseded close to restore. The sweep writes NULL groups.
        run_sweep(_sweep_ports(conn), MaintainRequest())
        assert _groups(conn) == [
            ("status", "supersedes_confirmed", None),
            ("status", "dependency_closed", None),
        ]

        run_reverse_supersedes(
            _ports(conn), MaintainRequest(item_id=1, link_id=supersedes_id)
        )

        assert _groups(conn)[-2:] == [
            ("status", "reversal", 1),
            ("link_reversed", "reversal", 1),
        ]
    finally:
        conn.close()


def test_validated_flag_path_stamps_one_group(db_path) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_type="Assumption", statement="A"
        )
        conn.commit()
        conn.close()
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass

    result = CliRunner().invoke(
        main, ["set-validated", "--item", "1", "--db", db_path]
    )

    assert result.exit_code == 0, result.output
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        assert _groups(conn) == [("validated", "user_set_validated", 1)]
    finally:
        conn.close()


def test_sweep_rows_stay_null(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="Old")
        insert_item(conn, source_id=source_id, item_id=2, statement="New")
        insert_item(conn, source_id=source_id, item_id=3, statement="Dependent")
        insert_link(conn, 2, 1, "supersedes")
        insert_link(conn, 3, 1, "depends_on")
        conn.commit()

        sweep = run_sweep(_sweep_ports(conn), MaintainRequest())

        assert sweep.applied == 2
        assert _groups(conn) == [
            ("status", "supersedes_confirmed", None),
            ("status", "dependency_closed", None),
        ]
    finally:
        conn.close()


def test_second_action_gets_a_different_larger_group_id(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)  # Decision
        insert_item(conn, source_id=source_id, item_id=2, item_type="Finding")
        conn.commit()

        run_edit_item(
            _ports(conn),
            # rationale is the Decision's writable field (MAINTAIN-001 gate).
            MaintainRequest(item_id=1, field="rationale", value="r1"),
        )
        run_edit_item(
            _ports(conn),
            # source is the Finding's writable field.
            MaintainRequest(item_id=2, field="source", value="s2"),
        )

        groups = [group for _, _, group in _groups(conn)]
        assert groups == [1, 2]
        assert groups[1] > groups[0]
    finally:
        conn.close()


def test_capture_and_relate_rows_stay_null(db_path) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        insert_item(conn, source_id=source_id, item_id=2)
        conn.commit()

        # Relate confirm: one atomic link + ledger write through its store.
        SqliteLinkStore(conn).insert_link_with_log(
            Link(
                source_item_id=1,
                target_item_id=2,
                link_type="depends_on",
                status="Confirmed",
                created_at=FIXED_TIME,
            ),
            ChangeLogEntry(
                item_id=1,
                field_changed="link_confirmed",
                new_value="Confirmed",
                timestamp=FIXED_TIME,
                trigger_cause="user_confirm",
            ),
        )
        # Capture confirm: the `created` ledger row through its store.
        SqliteItemGatekeeper(conn).log_created(
            ValidatedItem(
                id=1,
                type="Decision",
                statement="Use SQLite",
                source_quote="Use SQLite",
                confidence=0.9,
                source_id=source_id,
                created_at=FIXED_TIME,
                status="Active",
                near_dup_warning=None,
            )
        )
        conn.commit()
        assert {(group, cause) for _, cause, group in _groups(conn)} == {
            (None, "user_confirm"),
            (None, "user_confirmed"),
        }
    finally:
        conn.close()


def test_group_id_port_starts_at_one_and_points_after_the_highest_group(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        conn.commit()

        port = SqliteGroupIdPort(conn)
        # `1` when no row carries a group id.
        assert port.next_group_id() == 1

        run_edit_item(
            _ports(conn), MaintainRequest(item_id=1, field="rationale", value="r")
        )
        # `MAX(group_id)+1` after an action stamped group 1.
        assert port.next_group_id() == 2
    finally:
        conn.close()

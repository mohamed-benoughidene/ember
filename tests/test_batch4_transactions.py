"""Batch 4 chunk 8: one user action is one transaction (4.3 #9, 4.6 #1, 4.6 #3).

Each test plants a trigger that forces one store write to fail mid-action
(Spec-Batch4 "One transaction per action"), then asserts the whole user
action rolled back — or, for `maintain --format json`, that the document of
what completed is still printed when a LATER action fails.

The triggers live on the SAME connection the engine writes through, so the
red/green difference is purely transactional:

1. `test_a_forced_ledger_failure_leaves_no_item_row` — today the item insert
   commits first, so a failed `created` ledger row still leaves the item row.
2. `test_a_forced_shield_failure_leaves_the_status_unchanged` — today the
   status write commits and the shield is lost; after the fix the whole
   `Challenged -> Active` action (status batch + shield) rolls back.
3. `test_maintain_format_json_still_prints_the_document_when_a_later_action_fails`
   — the sweep completed and wrote; the close-proposal phase fails with no
   API key (MAINTAIN-020); exit 1, but the JSON document shows the sweep
   changes first (today only the error line prints).

Real v13 files, real stores, no AI keys anywhere (delenv below).
"""

from __future__ import annotations

import json
import sqlite3
from functools import partial
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.adapters.sqlite import (
    SqliteGroupIdPort,
    SqliteItemGatekeeper,
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_database,
    unit_of_work,
)
from ember.capture.confirm_write import accept
from ember.capture.errors import ItemDbWriteError
from ember.maintain.errors import ChangeLogWriteFailed as MaintainChangeLogWriteFailed
from ember.maintain.run_maintain import MaintainPorts, MaintainRequest, run_set_status
from ember.cli import main
from tests.fakes import (
    FIXED_TIME,
    insert_item,
    insert_link,
    insert_source,
    make_item,
)

T_ANSWER = "2026-01-01T00:00:00+00:00"
T_CLEAR = "2026-01-02T00:00:00+00:00"

# The forced-failure triggers (plan chunk 8): the engine's own write path
# aborts, so every assertion sees the transaction boundary, not a mock.
_FORCED_LEDGER_TRIGGER = (
    "CREATE TRIGGER force_fail BEFORE INSERT ON change_log"
    " WHEN NEW.field_changed = 'created'"
    " BEGIN SELECT RAISE(ABORT, 'forced'); END"
)
_FORCED_SHIELD_TRIGGER = (
    "CREATE TRIGGER force_fail BEFORE INSERT ON change_log"
    " WHEN NEW.field_changed = 'status_origin'"
    " BEGIN SELECT RAISE(ABORT, 'forced'); END"
)


def test_a_forced_ledger_failure_leaves_no_item_row(tmp_path: Path) -> None:
    """One accepted item is ONE write: item row + `created` ledger row.

    The ledger `created` INSERT is forced to abort. After the unit of work,
    the `items` row is gone too — today the item insert commits first, so
    the item survives a lost ledger row.
    """
    conn = open_database(str(tmp_path / "kb.db"))
    try:
        insert_source(conn)
        conn.commit()
        conn.execute(_FORCED_LEDGER_TRIGGER)
        conn.commit()

        accepted: list[int] = []
        with pytest.raises(ItemDbWriteError):
            accept(
                make_item(1),
                commit=SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME),
                accepted=accepted,
                unit_of_work=partial(unit_of_work, conn),
            )

        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    finally:
        conn.close()
    assert accepted == []
    assert count == 0
    assert logs == 0


def test_a_forced_shield_failure_leaves_the_status_unchanged(tmp_path: Path) -> None:
    """`Challenged -> Active` is ONE action: the status batch AND its shield.

    The `status_origin` ledger row (the manual shield's write, run_maintain
    set-status) is forced to abort. The whole action rolls back: the item
    stays `Challenged`, the shield stays `derived`, and no ledger row
    survives. Today the status write commits first and the shield is lost.
    """
    conn = open_database(str(tmp_path / "kb.db"))
    try:
        insert_source(conn)
        insert_item(conn, source_id=1, item_id=1, status="Challenged")
        conn.commit()
        conn.execute(_FORCED_SHIELD_TRIGGER)
        conn.commit()
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
            group_ids=SqliteGroupIdPort(conn),
            unit_of_work=partial(unit_of_work, conn),
        )

        with pytest.raises(MaintainChangeLogWriteFailed):
            run_set_status(ports, MaintainRequest(item_id=1, to_status="Active"))

        row = conn.execute(
            "SELECT status, status_origin FROM items WHERE id = 1"
        ).fetchone()
        logs = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    finally:
        conn.close()
    assert row["status"] == "Challenged"
    assert row["status_origin"] == "derived"
    assert logs == 0


def _shield(conn: sqlite3.Connection, item_id: int) -> None:
    """Mark `status_origin='manual'` with its clear ledger row, dated after
    the answer link (the production shape the sweep cannot machine-close)."""
    conn.execute(
        "UPDATE items SET status_origin = 'manual' WHERE id = ?", (item_id,)
    )
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, NULL, 'status_origin', 'derived', 'manual', ?,"
        " 'user_set_status')",
        (item_id, T_CLEAR),
    )


def test_maintain_format_json_still_prints_the_document_when_a_later_action_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sweep completed and wrote; the close-proposal phase then fails.

    With no API key (MAINTAIN-020), a real `maintain --format json --confirm
    json` run still prints the document of what completed — the sweep's
    change must be in it AND in the database — and exits 1. Today only the
    error line prints.
    """
    db_path = tmp_path / "kb.db"
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="old")
        insert_item(conn, source_id=source_id, item_id=2, statement="new")
        insert_link(conn, 2, 1, "supersedes")
        # A shielded Question answered long ago survives the sweep and lands
        # on the stale shortlist, so the close-proposal phase runs — and
        # fails, because there is no API key (env vars dropped below).
        insert_item(
            conn, source_id=source_id, item_id=3, item_type="Question",
            statement="Which database?",
        )
        insert_item(conn, source_id=source_id, item_id=4, item_type="Finding")
        conn.execute(
            "INSERT INTO links (id, source_item_id, target_item_id, link_type,"
            " status, created_at) VALUES (?, 4, 3, 'answers', 'Confirmed', ?)",
            (11, T_ANSWER),
        )
        _shield(conn, 3)
        conn.commit()
    finally:
        conn.close()
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = CliRunner().invoke(
        main,
        ["maintain", "--db", db_path, "--format", "json", "--confirm", "json"],
    )

    assert result.exit_code == 1
    # The error is still named on stderr ...
    assert "MAINTAIN-020" in result.stderr
    # ... AND the document of what completed is on stdout (4.6 #3). D-20
    # (lead ruling B): a real `--format json` run goes through the `--confirm
    # json` event stream, so the document is the final `message` event's
    # `text`, printed BEFORE the error re-raises (exit 1).
    events = [
        json.loads(line)
        for line in result.output.splitlines()
        if line.startswith("{")
    ]
    assert events[-1]["event"] == "message"
    document = json.loads(events[-1]["text"])
    assert document["command"] == "maintain"
    changes = document["changes"]
    assert [change["new_status"] for change in changes] == ["Closed"]
    assert document["summary"]["closed"] == 1
    assert document["summary"]["stale"] == 1
    # The document matches the file: the sweep's change really completed.
    check = sqlite3.connect(db_path)
    try:
        status = check.execute(
            "SELECT status, close_reason FROM items WHERE id = 1"
        ).fetchone()
    finally:
        check.close()
    assert status == ("Closed", "superseded")

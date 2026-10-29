"""`ember db-check`: one read-only health report (hardening step 02, L2 §2).

The inspectable artifact of the storage cluster (Rule S1). It opens the
database `mode=ro`, never migrates, never writes (I12/I2/I3, no `--repair`,
no mode flags). Any drift is reported as `result: DRIFT`, a missing or
not-a-database file as `result: UNREADABLE`, both with exit 1 at the CLI site.
A check reports, it raises no error codes (I12).
"""

from __future__ import annotations

import os
import sqlite3

from ember.adapters.link_replay import replay_reversals
from ember.adapters.sqlite import _connect_readonly
from ember.query.rows import ChangeRow
from ember.relate.compat import TYPE_COMPAT

EXPECTED_TRIGGERS = (
    "links_compat_insert",
    "links_compat_update",
    "items_closed_reason_insert",
    "items_closed_reason_update",
)

FLOORS: tuple[tuple[str, int], ...] = (
    ("relate", 12),
    ("maintain", 11),
    ("query", 10),
)

OK = "OK"
DRIFT = "DRIFT"
UNREADABLE = "UNREADABLE"


class DbCheckReport:
    """The report rows, the resulting verdict, and one stderr detail line."""

    def __init__(
        self,
        lines: list[str],
        result: str,
        detail: str | None = None,
    ) -> None:
        self.lines = lines
        self.result = result
        self.detail = detail


def check_database(db_path: str) -> DbCheckReport:
    """Check one database file read-only and return the pinned report.

    A missing or unreadable file yields `result: UNREADABLE` with one detail
    line for stderr. Any floors unmet stops the walk early (the deeper tables
    belong to the newer schema, so replay there would be meaningless).
    """
    if not os.path.exists(db_path):
        return DbCheckReport(
            [f"result: {UNREADABLE}"], UNREADABLE, detail="db file missing"
        )
    try:
        conn = _connect_readonly(db_path)
    except sqlite3.Error as exc:
        return DbCheckReport(
            [f"result: {UNREADABLE}"], UNREADABLE, detail=f"db open fail: {exc}"
        )
    try:
        lines = []
        version = _read_version(conn)
        lines.append(f"version: {version}")
        unmet = [f"{name} needs {floor}" for name, floor in FLOORS if version < floor]
        if unmet:
            lines.append("floors: unmet - " + ", ".join(unmet))
            lines.append(f"result: {DRIFT}")
            return DbCheckReport(lines, DRIFT)
        drifted = False
        lines.append(_floors_line())
        line, hit = _triggers_line(conn)
        lines.append(line)
        drifted = drifted or hit
        line, hit = _link_compat_line(conn)
        lines.append(line)
        drifted = drifted or hit
        line, hit = _foreign_key_line(conn)
        lines.append(line)
        drifted = drifted or hit
        line, hit = _replay_line(conn)
        lines.append(line)
        drifted = drifted or hit
        lines.append(f"result: {DRIFT if drifted else OK}")
        return DbCheckReport(lines, DRIFT if drifted else OK)
    except sqlite3.Error as exc:
        return DbCheckReport(
            [f"result: {UNREADABLE}"], UNREADABLE, detail=f"db read fail: {exc}"
        )
    finally:
        conn.close()


def _read_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None or row["version"] is None:
        raise sqlite3.OperationalError("schema_version is empty")
    return int(row["version"])


def _floors_line() -> str:
    parts = [f"{name} {floor} ok" for name, floor in FLOORS]
    return "floors: " + ", ".join(parts) + ", capture none"


def _triggers_line(conn: sqlite3.Connection) -> tuple[str, bool]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger'"
    ).fetchall()
    present = {row["name"] for row in rows}
    missing = [name for name in EXPECTED_TRIGGERS if name not in present]
    if missing:
        return "triggers: missing " + ", ".join(missing), True
    return "triggers: " + ", ".join(EXPECTED_TRIGGERS) + " - present", False


def _link_compat_line(conn: sqlite3.Connection) -> tuple[str, bool]:
    expected = {
        (source_type, target_type, link_type)
        for (source_type, target_type), link_types in TYPE_COMPAT.items()
        for link_type in link_types
    }
    rows = conn.execute(
        "SELECT source_type, target_type, link_type FROM link_compat"
    ).fetchall()
    actual = {
        (row["source_type"], row["target_type"], row["link_type"])
        for row in rows
    }
    if actual == expected:
        return f"link_compat: {len(rows)} rows, matches TYPE_COMPAT", False
    return (
        f"link_compat: {len(rows)} rows, drift from TYPE_COMPAT"
        f" ({len(expected - actual)} missing, {len(actual - expected)} extra)",
        True,
    )


def _foreign_key_line(conn: sqlite3.Connection) -> tuple[str, bool]:
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    return f"foreign_key_check: {len(violations)} violations", bool(violations)


def _replay_line(conn: sqlite3.Connection) -> tuple[str, bool]:
    replay = replay_reversals(_ledger_rows(conn))
    live = {
        row["id"]: row["reversed_at"]
        for row in conn.execute("SELECT id, reversed_at FROM links")
    }
    reversed_count = sum(1 for value in replay.values() if value is not None)
    mismatched = sorted(
        link_id for link_id, value in live.items() if replay.get(link_id) != value
    )
    if not mismatched:
        return f"reversal replay: {reversed_count} reversed links, column == ledger", False
    return (
        f"reversal replay: {reversed_count} reversed links, column != ledger"
        f" (mismatched links: {', '.join(str(i) for i in mismatched)})",
        True,
    )


def _ledger_rows(conn: sqlite3.Connection) -> list[ChangeRow]:
    return [
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
            "SELECT id, item_id, link_id, field_changed, old_value, new_value,"
            " timestamp, trigger_cause FROM change_log ORDER BY id"
        )
    ]

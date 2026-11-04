"""`ember db-check`: one read-only health report (hardening step 02, L2 §2).

The inspectable artifact of the storage cluster (Rule S1). It opens the
database `mode=ro`, never migrates, never writes (I12/I2/I3, no `--repair`,
no mode flags). Any drift is reported as `result: DRIFT`, a missing or
not-a-database file as `result: UNREADABLE`, both with exit 1 at the CLI site.
A check reports, it raises no error codes (I12). Since undo step 05 the
report also carries the undo-group check: on schema 13+ every `undo_of` /
`redo_of` pointer row must name an existing group; on v12 it prints
`group_id: not applicable (schema v12)` (no new floor, so a healthy v12
file never reads as drift).
"""

from __future__ import annotations

import importlib.resources
import os
import re
import sqlite3

from ember.adapters.link_replay import replay_reversals
from ember.adapters.sqlite import (
    _EXPECTED_TABLES_AT_LATEST,
    _LATEST_VERSION,
    _connect_readonly,
    column_exists,
)
from ember.query.rows import ChangeRow
from ember.relate.compat import TYPE_COMPAT

EXPECTED_TRIGGERS = (
    "links_compat_insert",
    "links_compat_update",
    "items_closed_reason_insert",
    "items_closed_reason_update",
)

# Where the expected trigger definitions live (Batch 4 chunk 15): the
# stored `sqlite_master.sql` of each expected trigger must match the
# definition the pinned script set ships, not just the NAME (4.3 #8).
_TRIGGER_DEFINITIONS_SCRIPT = (
    "011_add_links_reversed_at_and_enforcement_triggers.sql"
)

# Lazily extracted `' '.join()`-normalised definitions, keyed by trigger
# name. `set()` (empty dict) means the script could not be read; the check
# then reports drift rather than crashing (the report never raises, I12).
_EXPECTED_TRIGGER_SQL: dict[str, str] | None = None

FLOORS: tuple[tuple[str, int], ...] = (
    # "relate" stays at 12 (the migration that added `items.metadata`, which
    # this walk reads): db-check never reads `item_embeddings.vector_format`,
    # so a 15 floor would report every healthy pre-015 file as drift — a
    # false alarm. The write side carries the real requirement instead
    # (`ensure_relate_schema` refuses cache writes below 15).
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
        try:
            version = _read_version(conn)
        except ValueError:
            # A non-numeric stamped version is a finding, not a crash
            # (the report never raises, story 13 / report 4.10 #15).
            lines.append("version: cannot read - not a number")
            lines.append(f"result: {DRIFT}")
            return DbCheckReport(lines, DRIFT)
        lines.append(f"version: {version}")
        unmet = [f"{name} needs {floor}" for name, floor in FLOORS if version < floor]
        if version > _LATEST_VERSION:
            # Story 18 (4.3 #12): a version beyond the pinned latest reads
            # as drift, never as "unknown, let it pass" — a file written by
            # a NEWER Ember is not something this build can vouch for.
            unmet.append(f"version {version} above latest {_LATEST_VERSION}")
        if unmet:
            lines.append("floors: unmet - " + ", ".join(unmet))
            lines.append(f"result: {DRIFT}")
            return DbCheckReport(lines, DRIFT)
        drifted = False
        lines.append(_floors_line())
        line, hit = _tables_line(conn)
        lines.append(line)
        if hit:
            # Stop the walk when an expected table is gone (same rule as
            # unmet floors: the deeper checks walk those tables, so replay
            # there would be meaningless — and could read as a crash).
            lines.append(f"result: {DRIFT}")
            return DbCheckReport(lines, DRIFT)
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
        line, hit = _group_marker_line(conn, version)
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


def _tables_line(conn: sqlite3.Connection) -> tuple[str, bool]:
    """The full expected table list is present exactly (story 17, 4.3 #7).

    `sqlite_`-prefixed internals (`sqlite_sequence`) are SQLite's own
    bookkeeping and never count for or against the shape. At the latest
    version AND on v12 the Ember table set is the same (013 only adds a
    column), so one expected list serves every file that passes floors.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master"
        " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual = {row["name"] for row in rows}
    missing = sorted(_EXPECTED_TABLES_AT_LATEST - actual)
    if missing:
        return "tables: missing " + ", ".join(missing), True
    extra = sorted(actual - _EXPECTED_TABLES_AT_LATEST)
    if extra:
        return "tables: unexpected " + ", ".join(extra), True
    return f"tables: {len(_EXPECTED_TABLES_AT_LATEST)} expected - present", False


_TRIGGER_SHAPE = re.compile(r"CREATE TRIGGER\s+(\w+)(.*?)\bEND\s*;", re.DOTALL)


def _expected_trigger_sql() -> dict[str, str]:
    """The normalised trigger definitions the pinned script set ships.

    Extracted from the 011 script (the one migration that creates all four
    expected triggers) so the expectation can never drift from what real
    opens build. Extraction failing (a wiped package) answers `{}`: the
    check then reports drift instead of crashing (I12).
    """
    global _EXPECTED_TRIGGER_SQL
    if _EXPECTED_TRIGGER_SQL is None:
        expected: dict[str, str] = {}
        try:
            package = importlib.resources.files("ember.adapters.migrations")
            text = package.joinpath(_TRIGGER_DEFINITIONS_SCRIPT).read_text(
                encoding="utf-8"
            )
        except (OSError, AttributeError):
            text = ""
        for match in _TRIGGER_SHAPE.finditer(text):
            definition = " ".join(match.group(0).split())
            # `sqlite_master.sql` stores the statement without its final
            # `;`; the extracted script text still carries it.
            expected[match.group(1)] = definition[:-1] if definition.endswith(";") else definition
        _EXPECTED_TRIGGER_SQL = expected
    return _EXPECTED_TRIGGER_SQL


def _trigger_sql_matches(name: str, stored: str | None) -> bool:
    """Whether the stored definition IS the expected one, whitespace aside."""
    expected = _expected_trigger_sql().get(name)
    if not expected or not stored:
        return False
    return " ".join(stored.split()) == expected


def _triggers_line(conn: sqlite3.Connection) -> tuple[str, bool]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
    ).fetchall()
    present = {row["name"]: row["sql"] for row in rows}
    missing = [name for name in EXPECTED_TRIGGERS if name not in present]
    if missing:
        return "triggers: missing " + ", ".join(missing), True
    # A right name with a hollow body guards nothing (story 18, 4.3 #8):
    # the stored SQL must be the shipped definition, whitespace aside.
    mismatched = [
        name
        for name in EXPECTED_TRIGGERS
        if not _trigger_sql_matches(name, present[name])
    ]
    if mismatched:
        return (
            "triggers: SQL does not match the expected definition - "
            + ", ".join(mismatched),
            True,
        )
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


UNDO_MARKER_FIELDS = ("undo_of", "redo_of")


def _group_marker_line(conn: sqlite3.Connection, version: int) -> tuple[str, bool]:
    """The undo-group check (undo step 05): pointers name existing groups.

    Runs only on schema 13 and newer, where migration 013 guarantees the
    `group_id` column — a floor of 13 would report every healthy v12 file as
    drift, so there is deliberately no new floor. On v12 the line says
    `not applicable` and never drifts. Read-only SELECTs only.
    """
    if version < 13:
        return f"group_id: not applicable (schema v{version})", False
    rows = conn.execute(
        "SELECT id, new_value FROM change_log"
        " WHERE field_changed IN (?, ?) ORDER BY id",
        UNDO_MARKER_FIELDS,
    ).fetchall()
    groups = {
        row["group_id"]
        for row in conn.execute(
            "SELECT DISTINCT group_id FROM change_log"
            " WHERE group_id IS NOT NULL"
        )
    }
    broken = [
        f"{row['id']}->{row['new_value']}"
        for row in rows
        if not (row["new_value"] or "").isdigit()
        or int(row["new_value"]) not in groups
    ]
    if broken:
        return (
            f"group_id: undo/redo pointers name missing groups"
            f" ({len(rows)} pointers, broken: {', '.join(broken)})",
            True,
        )
    return (
        f"group_id: {len(rows)} undo/redo pointers, all name existing groups",
        False,
    )


def _ledger_rows(conn: sqlite3.Connection) -> list[ChangeRow]:
    """Read the ledger as ChangeRow objects, `group_id` when the file has it.

    The group stamp is selected only when the column exists (migration 013,
    finding 4.7 #11): on 13+ the rows carry their undo group, on a pre-013
    file every row keeps the model default `None` instead of failing the
    whole check.
    """
    columns = (
        "id, item_id, link_id, field_changed, old_value, new_value,"
        " timestamp, trigger_cause"
    )
    has_groups = column_exists(conn, "change_log", "group_id")
    if has_groups:
        columns += ", group_id"
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
            group_id=(
                int(row["group_id"])
                if has_groups and row["group_id"] is not None
                else None
            ),
        )
        for row in conn.execute(
            f"SELECT {columns} FROM change_log ORDER BY id"
        )
    ]

"""CLI tests for the `set-validated` and `clear-validated` commands."""

from __future__ import annotations

import sqlite3

from click.testing import CliRunner

from ember.adapters.sqlite import open_database
from ember.cli import main

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def seed_item(db_path: str, item_type: str) -> int:
    conn = open_database(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO sources (title, full_text, timestamp, content_hash)"
            " VALUES ('t', 'body', ?, 'hash')",
            (FIXED_TIME,),
        )
        source_id = int(cursor.lastrowid)
        cursor = conn.execute(
            "INSERT INTO items"
            " (type, statement, source_id, status, created_at, validated)"
            " VALUES (?, 'Team ships weekly', ?, 'Active', ?, NULL)",
            (item_type, source_id, FIXED_TIME),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def flag(db_path: str, item_id: int):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT validated FROM items WHERE id = ?", (item_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def test_set_validated_flips_the_flag(db_path) -> None:
    item_id = seed_item(db_path, "Assumption")

    result = invoke(["set-validated", "--item", str(item_id), "--db", db_path])

    assert result.exit_code == 0
    assert flag(db_path, item_id) == 1
    assert f"item {item_id} validated: true" in result.output


def test_clear_validated_flips_the_flag_back(db_path) -> None:
    item_id = seed_item(db_path, "Assumption")
    invoke(["set-validated", "--item", str(item_id), "--db", db_path])

    result = invoke(["clear-validated", "--item", str(item_id), "--db", db_path])

    assert result.exit_code == 0
    assert flag(db_path, item_id) == 0
    assert f"item {item_id} validated: false" in result.output


def test_missing_item_exits_1(db_path) -> None:
    result = invoke(["set-validated", "--item", "99", "--db", db_path])

    assert result.exit_code == 1
    assert "CAPTURE-015" in result.output


def test_non_assumption_exits_1(db_path) -> None:
    item_id = seed_item(db_path, "Decision")

    result = invoke(["set-validated", "--item", str(item_id), "--db", db_path])

    assert result.exit_code == 1
    assert "CAPTURE-016" in result.output
    assert flag(db_path, item_id) is None


def test_flag_change_writes_one_change_log_row(db_path) -> None:
    item_id = seed_item(db_path, "Assumption")

    invoke(["set-validated", "--item", str(item_id), "--db", db_path])

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT item_id, field_changed, old_value, new_value, trigger_cause"
            " FROM change_log"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [(item_id, "validated", None, "true", "user_set_validated")]

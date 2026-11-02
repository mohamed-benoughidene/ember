"""CLI tests for the `set-validated` and `clear-validated` commands."""

from __future__ import annotations

import sqlite3

from click.testing import CliRunner

from ember.adapters.sqlite import open_database
from ember.cli import main
from tests.fakes import insert_item, insert_source


def seed_item(db_path: str, item_type: str) -> int:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        item_id = insert_item(
            conn,
            source_id=source_id,
            item_type=item_type,
            statement="Team ships weekly",
        )
        conn.commit()
        return item_id
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


def test_set_validated_on_an_already_validated_item_writes_no_ledger_row(
    db_path,
) -> None:
    """4.5 #18: a second `set-validated` changes nothing. Writing anyway
    would append a fake `true -> true` ledger row — history for a change
    that never happened. The flag keeps its value, the command still
    exits 0, and the ledger holds exactly ONE `validated` row."""
    item_id = seed_item(db_path, "Assumption")
    invoke(["set-validated", "--item", str(item_id), "--db", db_path])

    result = invoke(["set-validated", "--item", str(item_id), "--db", db_path])

    assert result.exit_code == 0
    assert flag(db_path, item_id) == 1
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT old_value, new_value FROM change_log"
            " WHERE field_changed = 'validated'"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [(None, "true")]


def test_missing_item_exits_1(db_path) -> None:
    open_database(db_path).close()  # D-25: set-validated refuses a missing file

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

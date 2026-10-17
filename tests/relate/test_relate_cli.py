"""CLI tests for the `relate` command."""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner

from ember.adapters.sqlite import open_relate_database
from ember.cli import main
from tests.fakes import FIXED_TIME, insert_item, insert_source


def _insert_link(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    link_type: str,
    status: str,
) -> None:
    conn.execute(
        "INSERT INTO links (source_item_id, target_item_id, link_type, status,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (source_id, target_id, link_type, status, FIXED_TIME),
    )


def _seed_six_items_two_links(db_path: str) -> None:
    conn = open_relate_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Question")
        insert_item(conn, source_id=source_id, item_id=3, item_type="Question")
        insert_item(conn, source_id=source_id, item_id=4, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=5, item_type="Assumption")
        insert_item(conn, source_id=source_id, item_id=6, item_type="Finding")
        _insert_link(conn, 1, 2, "answers", "Confirmed")
        _insert_link(conn, 1, 3, "answers", "Rejected")
        conn.commit()
    finally:
        conn.close()


def _seed_item(
    conn: sqlite3.Connection,
    source_id: int,
    item_id: int,
    *,
    status: str = "Active",
) -> None:
    insert_item(conn, source_id=source_id, item_id=item_id)
    if status != "Active":
        conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def test_relate_item_prints_phase1_json(db_path) -> None:
    _seed_six_items_two_links(db_path)

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "phase": 1,
        "new_item_id": 1,
        "candidates": 3,
    }


def test_relate_missing_item_exits_1_with_code(db_path) -> None:
    conn = open_relate_database(db_path)
    try:
        insert_source(conn)
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(main, ["relate", "--item", "999", "--db", db_path])

    assert result.exit_code == 1
    assert "RELATE-001" in _error_text(result)
    assert "999" in _error_text(result)
    assert db_path in _error_text(result)


def test_relate_latest_soft_exit_when_nothing_eligible(db_path) -> None:
    conn = open_relate_database(db_path)
    try:
        source_id = insert_source(conn)
        _seed_item(conn, source_id, 1)
        _seed_item(conn, source_id, 2, status="Closed")
        _insert_link(conn, 1, 2, "supports", "Confirmed")
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(main, ["relate", "--latest", "--db", db_path])

    assert result.exit_code == 0
    assert result.output.strip() == "no unrelated items"


def test_relate_latest_prints_json_when_eligible(db_path) -> None:
    conn = open_relate_database(db_path)
    try:
        source_id = insert_source(conn)
        _seed_item(conn, source_id, 1)
        _seed_item(conn, source_id, 2)
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(main, ["relate", "--latest", "--db", db_path])

    assert result.exit_code == 0
    assert json.loads(result.output)["new_item_id"] == 2


def test_relate_requires_exactly_one_selector(db_path) -> None:
    runner = CliRunner()

    missing = runner.invoke(main, ["relate", "--db", db_path])
    both = runner.invoke(main, ["relate", "--item", "1", "--latest", "--db", db_path])

    assert missing.exit_code == 2
    assert both.exit_code == 2

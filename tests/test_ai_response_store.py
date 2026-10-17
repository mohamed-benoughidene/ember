"""Tests for the raw AI response store write boundary."""

from __future__ import annotations

import pytest

from ember.adapters.sqlite import SqliteAiResponseStore, open_database
from tests.fakes import insert_item, insert_source


def test_save_with_source_id(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)

    SqliteAiResponseStore(conn).save(source_id=source_id, raw_response="a")

    rows = conn.execute("SELECT source_id, item_id FROM ai_responses").fetchall()
    assert len(rows) == 1
    assert rows[0]["source_id"] == source_id
    assert rows[0]["item_id"] is None


def test_save_with_item_id(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    item_id = insert_item(conn, source_id=source_id)

    SqliteAiResponseStore(conn).save(item_id=item_id, raw_response="b")

    rows = conn.execute("SELECT source_id, item_id FROM ai_responses").fetchall()
    assert len(rows) == 1
    assert rows[0]["item_id"] == item_id
    assert rows[0]["source_id"] is None


def test_save_rejects_both_ids(db_path) -> None:
    conn = open_database(db_path)

    with pytest.raises(ValueError):
        SqliteAiResponseStore(conn).save(source_id=1, item_id=1, raw_response="x")


def test_save_rejects_no_ids(db_path) -> None:
    conn = open_database(db_path)

    with pytest.raises(ValueError):
        SqliteAiResponseStore(conn).save(raw_response="x")

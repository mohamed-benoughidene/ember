"""Integration tests: the read-only boot and the port, on a real v10 DB."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from ember.adapters.sqlite import (
    SqliteQueryContext,
    ensure_query_schema,
    open_query_database,
)
from ember.query.errors import DbOpenFailed, ItemsReadFailed, SchemaOutdated
from ember.query.run_query import run_current_state
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source
from tests.query.fakes import make_v9, make_v10


def _seed_v10(db_path: str) -> None:
    """One item per status, plus one link and one change_log row."""
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, status="Active")
        insert_item(conn, source_id=source_id, item_id=2, status="Challenged")
        insert_item(
            conn,
            source_id=source_id,
            item_id=3,
            status="Closed",
            close_reason="expired",
        )
        insert_link(conn, 1, 2, "depends_on")
        conn.execute(
            "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, None, "created", None, "Active", FIXED_TIME, "user_confirmed"),
        )
        conn.execute(
            "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (None, None, "proposed", None, "rejected", FIXED_TIME, "rejected"),
        )
        conn.commit()
    finally:
        conn.close()


def _hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_missing_file_raises_003_and_is_never_created(tmp_path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(DbOpenFailed) as exc:
        open_query_database(str(missing))

    assert exc.value.code == "QUERY-003"
    assert exc.value.context["db_path"] == str(missing)
    assert not missing.exists()


def test_non_sqlite_file_raises_003(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(DbOpenFailed) as exc:
        open_query_database(str(corrupt))

    assert exc.value.code == "QUERY-003"


def test_version_9_database_raises_004_and_is_not_migrated(db_path) -> None:
    make_v9(db_path)

    with pytest.raises(SchemaOutdated) as exc:
        open_query_database(db_path)

    assert exc.value.code == "QUERY-004"
    assert exc.value.context["version"] == 9
    assert exc.value.context["required"] == 10

    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert version == 9


def test_ensure_query_schema_accepts_version_10(db_path) -> None:
    make_v10(db_path).close()
    conn = open_query_database(db_path)
    try:
        ensure_query_schema(conn)
    finally:
        conn.close()


def test_query_leaves_the_database_byte_identical(db_path) -> None:
    _seed_v10(db_path)
    before = _hash(db_path)

    conn = open_query_database(db_path)
    try:
        document = json.loads(run_current_state(SqliteQueryContext(conn)))
    finally:
        conn.close()

    assert document["count"] == 2
    assert [item["id"] for item in document["items"]] == [2, 1]
    assert _hash(db_path) == before


def test_read_only_connection_rejects_a_write(db_path) -> None:
    _seed_v10(db_path)
    conn = open_query_database(db_path)

    with pytest.raises(sqlite3.OperationalError):
        conn.execute("CREATE TABLE sneaky (id INTEGER)")

    conn.close()


def test_port_reads_return_rows_in_id_order(db_path) -> None:
    _seed_v10(db_path)
    conn = open_query_database(db_path)
    try:
        context = SqliteQueryContext(conn)
        items = context.list_items()
        links = context.list_links()
        rows = context.list_change_log()
        exists = context.item_exists(1)
        missing = context.item_exists(99)
    finally:
        conn.close()

    assert [item.id for item in items] == [1, 2, 3]
    assert items[0].statement == "Use SQLite"
    assert items[2].close_reason == "expired"
    assert [link.id for link in links] == [1]
    assert links[0].source_item_id == 1
    assert [row.id for row in rows] == [1, 2]
    assert rows[1].item_id is None
    assert exists is True
    assert missing is False


@pytest.mark.parametrize(
    "call",
    [
        lambda context: context.list_items(),
        lambda context: context.list_links(),
        lambda context: context.list_change_log(),
        lambda context: context.item_exists(1),
    ],
)
def test_read_failure_raises_005(db_path, call) -> None:
    _seed_v10(db_path)
    conn = open_query_database(db_path)
    context = SqliteQueryContext(conn)
    conn.close()

    with pytest.raises(ItemsReadFailed) as exc:
        call(context)

    assert exc.value.code == "QUERY-005"

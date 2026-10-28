"""CLI smoke tests for `ember current-state`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from ember.cli import main
from tests.fakes import insert_item, insert_link, insert_source
from tests.query.fakes import make_v10


def _seed(db_path: str) -> None:
    """Item 1 Active, item 2 Challenged, item 3 Closed."""
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
        conn.commit()
    finally:
        conn.close()


def test_current_state_prints_json_with_challenged_first(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["current-state", "--db", db_path])

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["mode"] == "current_state"
    assert document["count"] == 2
    assert [item["id"] for item in document["items"]] == [2, 1]


def test_current_state_rejects_an_unknown_flag_with_exit_2(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["current-state", "--item", "abc", "--db", db_path]
    )

    assert result.exit_code == 2


def test_stdout_carries_only_the_json_document(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["current-state", "--db", db_path])

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    assert json.loads(result.stdout)["count"] == 2


def test_topic_search_prints_results(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--db", db_path]
    )

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["mode"] == "topic_search"
    assert document["query"] == "sqlite"
    # All three seeded items share the default statement, so all three match —
    # including the `Closed` one, which is searched on purpose (L2 §2.2).
    assert document["count"] == 3
    assert [hit["item_id"] for hit in document["results"]] == [1, 2, 3]


def test_topic_search_on_punctuation_exits_1_with_query_002(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["topic-search", "--query", "!!!", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "QUERY-002" in (result.output + (result.stderr or ""))


def test_why_on_a_missing_item_exits_1_with_query_001(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["why", "--item", "99", "--db", db_path])

    assert result.exit_code == 1
    assert "QUERY-001" in (result.output + (result.stderr or ""))


def test_why_prints_the_reason(db_path) -> None:
    _seed(db_path)
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn, "second body")
        insert_item(
            conn,
            source_id=source_id,
            item_id=4,
            statement="Premise",
        )
        insert_link(conn, 1, 4, "depends_on")
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(main, ["why", "--item", "1", "--db", db_path])

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert [reason["item_id"] for reason in document["reasons"]] == [4]
    assert result.stdout.strip().startswith("{")

"""CLI smoke tests for `ember current-state`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from ember.cli import main
from tests.fakes import insert_item, insert_source
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

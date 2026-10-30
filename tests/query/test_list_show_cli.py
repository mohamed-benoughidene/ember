"""CLI integration tests for the bridge reads, on real temp DBs.

Bridge step 02. `list-items` and `show-item` are read-only: every test that
proves a read also proves the database file byte-identical afterwards, and
one test runs both commands on a genuine pre-011 (schema v10) file, where
`links.reversed_at` does not exist at all.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.cli import main
from tests.fakes import (
    FIXED_TIME,
    insert_item,
    insert_link,
    insert_source,
)
from tests.query.fakes import make_v10

_MIGRATIONS_TO_10 = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
    "006_create_links.sql",
    "007_create_item_embeddings.sql",
    "008_add_change_log_link_fk.sql",
    "009_drop_source_id_not_null_and_add_item_id.sql",
    "010_add_item_close_reason.sql",
)


def _seed_mixed_statuses(db_path: str) -> None:
    """Source 1 ('note body'); items 1-4: Active, Challenged, Closed, Finding.

    Items 1-2 carry an authorial `source` note and item 3 the validated
    flag, so the read model's additive columns have real values to show.
    """
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn, "note body")
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            source="whiteboard photo",
            validated=True,
        )
        insert_item(conn, source_id=source_id, item_id=2, status="Challenged")
        insert_item(
            conn,
            source_id=source_id,
            item_id=3,
            status="Closed",
            close_reason="expired",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=4,
            item_type="Finding",
            statement="Observed timeouts",
        )
        conn.commit()
    finally:
        conn.close()


def _seed_links(db_path: str, *, with_reversal: bool) -> None:
    """Give item 3 one out-link (Rejected) and one in-link (Confirmed)."""
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn, "note body")
        for item_id in range(1, 4):
            insert_item(conn, source_id=source_id, item_id=item_id)
        insert_link(conn, 3, 1, "depends_on", status="Rejected")
        insert_link(conn, 2, 3, "supersedes")
        if with_reversal:
            conn.execute(
                "UPDATE links SET reversed_at = ? WHERE id = 2", (FIXED_TIME,)
            )
        conn.commit()
    finally:
        conn.close()


def _build_v10_db(db_path: str) -> None:
    """Build a genuine pre-011 v10 file: no `links.reversed_at` column exists.

    Same recipe as `test_v12_read_never_migrates.py`: the migration SQL
    scripts 001-010 are applied by hand and the version is stamped 10, so
    the read-only boot accepts the file and nothing ever migrates it.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_10:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn)
    for item_id in range(1, 4):
        insert_item(conn, source_id=source_id, item_id=item_id)
    insert_link(conn, 3, 1, "depends_on", status="Rejected")
    insert_link(conn, 2, 3, "supersedes")
    conn.commit()
    conn.close()


def _hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _version(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(
            conn.execute("SELECT version FROM schema_version").fetchone()[0]
        )
    finally:
        conn.close()


# --- list-items --------------------------------------------------------------


def test_list_items_returns_every_status_and_the_right_total(db_path) -> None:
    _seed_mixed_statuses(db_path)

    result = CliRunner().invoke(main, ["list-items", "--db", db_path])

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert set(document) == {"total", "items"}
    assert document["total"] == 4
    assert [item["id"] for item in document["items"]] == [1, 2, 3, 4]
    statuses = {item["id"]: item["status"] for item in document["items"]}
    assert statuses[2] == "Challenged"
    # The Closed item IS listed; that is the point of the command.
    assert statuses[3] == "Closed"
    closed = document["items"][2]
    assert closed["close_reason"] == "expired"
    # Nine-field spec projection per item.
    assert set(closed) == {
        "id",
        "type",
        "statement",
        "status",
        "close_reason",
        "rationale",
        "source",
        "validated",
        "created_at",
    }
    assert document["items"][0]["source"] == "whiteboard photo"
    assert document["items"][0]["validated"] is True
    assert document["items"][1]["validated"] is None


def test_list_items_status_filter_returns_only_closed(db_path) -> None:
    _seed_mixed_statuses(db_path)

    result = CliRunner().invoke(
        main, ["list-items", "--status", "Closed", "--db", db_path]
    )

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["total"] == 1
    assert [item["id"] for item in document["items"]] == [3]


def test_list_items_filters_and_paging_compose(db_path) -> None:
    _seed_mixed_statuses(db_path)

    by_type = CliRunner().invoke(
        main,
        ["list-items", "--status", "Active", "--type", "Finding", "--db", db_path],
    )
    window = CliRunner().invoke(
        main,
        [
            "list-items",
            "--status",
            "Active",
            "--limit",
            "1",
            "--offset",
            "1",
            "--db",
            db_path,
        ],
    )
    empty = CliRunner().invoke(
        main, ["list-items", "--limit", "0", "--db", db_path]
    )

    # Only the Active Finding matches the paired filter.
    assert by_type.exit_code == 0
    assert json.loads(by_type.output)["total"] == 1
    assert [i["id"] for i in json.loads(by_type.output)["items"]] == [4]
    # Two Active items (1, 4); offset 1 skips the first, limit 1 keeps the next.
    assert window.exit_code == 0
    window_doc = json.loads(window.output)
    assert window_doc["total"] == 2
    assert [i["id"] for i in window_doc["items"]] == [4]
    # `--limit 0` is an explicit empty page, not an error; total is pre-page.
    assert empty.exit_code == 0
    assert json.loads(empty.output) == {"total": 4, "items": []}


def test_list_items_never_touches_the_database_file(db_path) -> None:
    _seed_mixed_statuses(db_path)
    before = _hash(db_path)

    for args in (
        ["list-items", "--db", db_path],
        ["list-items", "--status", "Closed", "--db", db_path],
        ["list-items", "--type", "Decision", "--db", db_path],
        ["list-items", "--limit", "2", "--offset", "1", "--db", db_path],
    ):
        result = CliRunner().invoke(main, args)
        assert result.exit_code == 0, args
        assert _hash(db_path) == before, args


# --- show-item ---------------------------------------------------------------


def test_show_item_lists_rejected_and_reversed_links_both_directions(
    db_path,
) -> None:
    _seed_links(db_path, with_reversal=True)

    result = CliRunner().invoke(main, ["show-item", "--item", "3", "--db", db_path])

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert set(document) == {"item", "source", "links_out", "links_in"}
    assert document["source"] == "note body"
    assert document["item"]["id"] == 3

    out = document["links_out"]
    assert len(out) == 1
    assert out[0]["id"] == 1
    assert out[0]["type"] == "depends_on"
    assert out[0]["status"] == "Rejected"
    assert out[0]["other_item_id"] == 1
    assert out[0]["other_item_status"] == "Active"
    assert out[0]["reversed_at"] is None

    inside = document["links_in"]
    assert len(inside) == 1
    assert inside[0]["id"] == 2
    assert inside[0]["type"] == "supersedes"
    assert inside[0]["status"] == "Confirmed"
    assert inside[0]["other_item_id"] == 2
    assert inside[0]["other_item_statement"] == "Use SQLite"
    assert inside[0]["reversed_at"] == FIXED_TIME


def test_show_item_never_touches_the_database_file(db_path) -> None:
    _seed_links(db_path, with_reversal=True)
    before = _hash(db_path)

    result = CliRunner().invoke(main, ["show-item", "--item", "3", "--db", db_path])

    assert result.exit_code == 0
    assert _hash(db_path) == before


def test_list_items_and_show_item_work_on_a_v10_file_never_migrating(
    db_path,
) -> None:
    """A genuine pre-011 v10 file: no `reversed_at` column exists at all.

    Both reads succeed, every link reports `reversed_at: null`, the file
    stays at version 10, and its bytes never change (bridge step 02 §2,
    L2 §5.3).
    """
    _build_v10_db(db_path)
    before = _hash(db_path)

    listed = CliRunner().invoke(main, ["list-items", "--db", db_path])
    shown = CliRunner().invoke(main, ["show-item", "--item", "3", "--db", db_path])

    assert listed.exit_code == 0, listed.output
    assert shown.exit_code == 0, shown.output
    document = json.loads(shown.stdout)
    assert document["item"]["id"] == 3
    assert [link["id"] for link in document["links_out"]] == [1]
    assert document["links_out"][0]["status"] == "Rejected"
    assert [link["id"] for link in document["links_in"]] == [2]
    assert all(link["reversed_at"] is None for link in document["links_out"])
    assert all(link["reversed_at"] is None for link in document["links_in"])
    assert _version(db_path) == 10
    assert _hash(db_path) == before
    # And the live-column file: `show-item` succeeds with a `null` there too.
    live = str(Path(db_path).with_suffix(".live.db"))
    _seed_links(live, with_reversal=False)
    result = CliRunner().invoke(main, ["show-item", "--item", "3", "--db", live])
    assert result.exit_code == 0
    live_document = json.loads(result.stdout)
    assert live_document["links_in"][0]["reversed_at"] is None


def test_show_item_unknown_id_exits_1_with_query_001_on_stderr(db_path) -> None:
    _seed_links(db_path, with_reversal=False)

    result = CliRunner().invoke(
        main, ["show-item", "--item", "99", "--db", db_path]
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "error: QUERY-001 QueryItemNotFound" in (result.stderr or "")


def test_list_items_bad_status_exits_1_with_query_006_field_status(db_path) -> None:
    _seed_mixed_statuses(db_path)

    result = CliRunner().invoke(
        main, ["list-items", "--status", "bogus", "--db", db_path]
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    combined = result.output + (result.stderr or "")
    assert "error: QUERY-006 QueryFilterInvalid" in combined
    assert "field=status" in combined
    assert "bogus" not in (result.stderr or "")


@pytest.mark.parametrize(
    "args, field",
    [
        (["--limit", "-1"], "field=limit"),
        (["--offset", "-2"], "field=offset"),
    ],
)
def test_list_items_negative_page_values_exit_1_with_query_006(
    db_path, args, field
) -> None:
    _seed_mixed_statuses(db_path)

    result = CliRunner().invoke(main, ["list-items", *args, "--db", db_path])

    assert result.exit_code == 1
    assert field in result.output + (result.stderr or "")


@pytest.mark.parametrize(
    "args",
    [
        ["list-items", "--limit", "abc"],
        ["list-items", "--pagesize", "2"],
        ["show-item"],  # missing the required --item
        ["show-item", "--item", "abc"],
    ],
)
def test_click_rejected_input_exits_2_with_no_house_error_line(db_path, args) -> None:
    _seed_mixed_statuses(db_path)

    result = CliRunner().invoke(main, [*args, "--db", db_path])

    assert result.exit_code == 2
    stderr = result.stderr or ""
    assert "error:" not in stderr
    assert "QUERY-" not in stderr


def test_show_item_stdout_is_json_only(db_path) -> None:
    _seed_links(db_path, with_reversal=False)

    result = CliRunner().invoke(main, ["show-item", "--item", "1", "--db", db_path])

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    assert json.loads(result.stdout)["item"]["id"] == 1

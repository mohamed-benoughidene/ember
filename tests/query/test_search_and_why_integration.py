"""Integration: `topic-search` and `why` on a real v10 database."""

from __future__ import annotations

import json

import pytest

from ember.adapters.sqlite import SqliteQueryContext, open_query_database
from ember.query.run_query import run_topic_search, run_why
from tests.fakes import insert_item, insert_link, insert_source
from tests.query.fakes import make_v10


def _seed(db_path: str) -> None:
    """Item 1 depends_on item 2. Item 3 is unrelated."""
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            statement="Use SQLite for storage",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=2,
            item_type="Assumption",
            statement="SQLite is good enough for a solo project",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=3,
            statement="Postgres scales further",
        )
        insert_link(conn, 1, 2, "depends_on")
        conn.commit()
    finally:
        conn.close()


def test_topic_search_finds_the_expected_item_with_its_score(db_path) -> None:
    _seed(db_path)
    conn = open_query_database(db_path)
    try:
        document = json.loads(
            run_topic_search(SqliteQueryContext(conn), "sqlite")
        )
    finally:
        conn.close()

    assert document["count"] == 2
    assert [hit["item_id"] for hit in document["results"]] == [1, 2]
    # Same formula as the golden fixture, re-derived by hand for this corpus:
    # N = 3, avgdl = 5, idf('sqlite') = 0.47000362924573563. Item 1 has 4
    # tokens (term ratio 2.2/2.02) and item 2 has 8 (2.2/2.74).
    assert [hit["score"] for hit in document["results"]] == pytest.approx(
        [0.5118851408, 0.3773751768], abs=1e-6
    )


def test_topic_search_on_a_missing_term_exits_with_an_empty_list(db_path) -> None:
    _seed(db_path)
    conn = open_query_database(db_path)
    try:
        document = json.loads(
            run_topic_search(SqliteQueryContext(conn), "kubernetes")
        )
    finally:
        conn.close()

    assert document["count"] == 0
    assert document["results"] == []


def test_why_returns_the_premise_over_a_real_link(db_path) -> None:
    _seed(db_path)
    conn = open_query_database(db_path)
    try:
        document = json.loads(run_why(SqliteQueryContext(conn), 1))
    finally:
        conn.close()

    assert document["item"]["id"] == 1
    assert [reason["item_id"] for reason in document["reasons"]] == [2]
    assert document["reasons"][0]["via_link_type"] == "depends_on"


def test_why_on_an_item_with_no_reasons_is_not_an_error(db_path) -> None:
    _seed(db_path)
    conn = open_query_database(db_path)
    try:
        document = json.loads(run_why(SqliteQueryContext(conn), 3))
    finally:
        conn.close()

    assert document["count"] == 0

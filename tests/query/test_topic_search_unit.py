"""Unit tests for the BM25 scorer, including the hand-computed golden fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ember.query.topic_search import topic_search
from tests.query.fakes import make_item

GOLDEN = json.loads(
    (
        Path(__file__).resolve().parents[1] / "fixtures" / "query" / "bm25_golden.json"
    ).read_text(encoding="utf-8")
)


def _items_from(rows: list[dict]) -> list:
    return [make_item(row["item_id"], statement=row["statement"]) for row in rows]


def test_scores_match_the_hand_computed_golden_fixture() -> None:
    items = _items_from(GOLDEN["corpus"])

    hits = topic_search(items, GOLDEN["query"])

    expected = GOLDEN["expected"]
    assert [hit.item_id for hit in hits] == [row["item_id"] for row in expected]
    assert [hit.score for hit in hits] == pytest.approx(
        [row["score"] for row in expected], abs=1e-6
    )


def test_golden_fixture_ties_are_broken_by_item_id() -> None:
    expected = GOLDEN["expected"]
    tied = [row for row in expected if row["score"] == expected[-1]["score"]]

    assert len(tied) == 2
    assert tied[0]["item_id"] < tied[1]["item_id"]


def test_term_present_in_every_document_still_scores_above_zero() -> None:
    items = [make_item(i, statement="alpha") for i in (1, 2, 3)]

    hits = topic_search(items, "alpha")

    assert len(hits) == 3
    assert all(hit.score > 0 for hit in hits)


def test_every_statement_tokenizing_to_nothing_returns_empty() -> None:
    items = [make_item(1, statement="!!!"), make_item(2, statement="???")]

    assert topic_search(items, "alpha") == []


def test_empty_corpus_returns_an_empty_list() -> None:
    assert topic_search([], "alpha") == []


def test_item_without_a_query_token_is_not_a_result() -> None:
    items = [
        make_item(1, statement="beta gamma"),
        make_item(2, statement="alpha delta"),
    ]

    hits = topic_search(items, "alpha")

    assert [hit.item_id for hit in hits] == [2]


def test_repeated_query_terms_are_counted_once() -> None:
    items = [make_item(1, statement="alpha beta")]

    once = topic_search(items, "alpha")
    twice = topic_search(items, "alpha alpha")

    assert once[0].score == pytest.approx(twice[0].score)


def test_hit_carries_the_item_fields() -> None:
    items = [make_item(7, statement="alpha", status="Closed", item_type="Question")]

    hit = topic_search(items, "alpha")[0]

    assert hit.item_id == 7
    assert hit.status == "Closed"
    assert hit.type == "Question"
    assert hit.statement == "alpha"

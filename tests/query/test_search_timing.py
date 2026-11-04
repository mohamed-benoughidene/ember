"""Timing and equivalence tests for `topic-search` (finding 4.7 #3, D-15). NEW.

The timing test seeds 10,000 items on a temp database and fails if the
old per-item-per-term rescoring ever comes back (story 1, story 9). The
equivalence test pins that the fast scorer picks the same top hits as a
slow reference implementation of the same BM25 formula.
"""

from __future__ import annotations

import json
import time

from click.testing import CliRunner

from ember.cli import main
from ember.query.tokenize import tokenize
from ember.query.topic_search import B, K1, _idf, topic_search
from tests.fakes import insert_item, insert_source
from tests.query.fakes import make_item, make_v10

QUERY = "gateway rewrite cache"

# Short statements that mix the query words `gateway`, `rewrite`, `cache`
# in different positions (and lengths), so every item matches but the
# ranking has real work to do.
STATEMENTS = [
    "gateway rewrite cache",
    "rewrite cache gateway alpha",
    "cache gateway rewrite beta",
    "cache gateway alpha beta",
    "rewrite gamma gateway",
    "gateway cache rewrite alpha beta gamma",
    "alpha beta cache",
    "rewrite gateway delta",
    "cache rewrite gateway alpha beta gamma",
]


def _statement(index: int) -> str:
    """Return one statement for item `index`, rotating the word positions."""
    return STATEMENTS[index % len(STATEMENTS)]


def _slow_reference_scores(items: list, query: str) -> list[tuple[int, float]]:
    """Score `items` the slow way the old code did, and rank the hits.

    Same BM25 formula as the `ember.query.topic_search` module docstring:
    per query term, walk every item again (`sum(... if term in other)`).
    Returns the scored hits as `(item_id, score)` in the same order the
    core sorts: score descending, then `item_id` ascending.
    """
    query_terms = list(dict.fromkeys(tokenize(query)))
    tokens_per_item = [tokenize(item.statement) for item in items]
    average_length = sum(len(tokens) for tokens in tokens_per_item) / len(items)
    scored: list[tuple[int, float]] = []
    for item, tokens in zip(items, tokens_per_item):
        score = 0.0
        for term in query_terms:
            frequency = tokens.count(term)
            if frequency == 0:
                continue
            document_frequency = sum(
                1 for other in tokens_per_item if term in other
            )
            length_ratio = len(tokens) / average_length
            denominator = frequency + K1 * (1 - B + B * length_ratio)
            score += _idf(len(items), document_frequency) * (
                frequency * (K1 + 1) / denominator
            )
        if score > 0:
            scored.append((item.id, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored


def test_10k_search_under_one_second(db_path) -> None:
    """A 3-word search over 10,000 items answers inside the 1 s bound."""
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        for index in range(1, 10_001):
            insert_item(
                conn,
                source_id=source_id,
                item_id=index,
                statement=_statement(index),
            )
        conn.commit()
    finally:
        conn.close()

    started = time.perf_counter()
    result = CliRunner().invoke(
        main, ["topic-search", "--query", QUERY, "--limit", "10", "--db", db_path]
    )
    elapsed = time.perf_counter() - started

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["count"] == 10
    assert elapsed < 1.0


def test_small_seed_matches_slow_reference() -> None:
    """The scorer's top ids equal the slow reference on a 9-item seed."""
    items = [
        make_item(item_id, statement=statement)
        for item_id, statement in enumerate(STATEMENTS, start=1)
    ]
    expected = _slow_reference_scores(items, QUERY)

    total, hits = topic_search(items, QUERY)

    assert (total, [hit.item_id for hit in hits]) == (
        len(expected),
        [item_id for item_id, _ in expected],
    )

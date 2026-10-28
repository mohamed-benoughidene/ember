"""BM25 scoring over item statements (the pure core of Phase 2).

No I/O, no clock, no DB, no printing. Formula, tokenizer and tie-break are
fixed by the L2 plan. `k1` and `b` are not tuned here.
"""

from __future__ import annotations

import math

from ember.query.rows import QueryItem, SearchHit
from ember.query.tokenize import tokenize

K1 = 1.2
B = 0.75


def _idf(corpus_size: int, document_frequency: int) -> float:
    """Return the BM25 inverse document frequency, always positive.

    The `ln(1 + ...)` form keeps a term that appears in more than half the
    corpus from going negative.
    """
    return math.log(
        1
        + (corpus_size - document_frequency + 0.5)
        / (document_frequency + 0.5)
    )


def topic_search(items: list[QueryItem], query: str) -> list[SearchHit]:
    """Return the items holding at least one query token, best score first.

    An item scores only on the query terms it contains, so an item with no
    query token is never a result. Order is score descending, then `item_id`
    ascending, so equal scores always come out in the same order.
    """
    query_terms = list(dict.fromkeys(tokenize(query)))
    tokens_per_item = [tokenize(item.statement) for item in items]
    if not query_terms or not items:
        return []
    average_length = sum(len(tokens) for tokens in tokens_per_item) / len(items)
    if average_length == 0:
        return []

    hits: list[SearchHit] = []
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
            hits.append(
                SearchHit(
                    item_id=item.id,
                    score=score,
                    type=item.type,
                    statement=item.statement,
                    status=item.status,
                )
            )
    return sorted(hits, key=lambda hit: (-hit.score, hit.item_id))

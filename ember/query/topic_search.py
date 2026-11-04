"""BM25 scoring over item statements (the pure core of Phase 2).

No I/O, no clock, no DB, no printing. Formula, tokenizer and tie-break are
fixed by the L2 plan. `k1` and `b` are not tuned here.
"""

from __future__ import annotations

import math
from collections import Counter

from ember.query.rows import QueryItem, SearchHit, TopicFilter
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


def topic_search(
    items: list[QueryItem],
    query: str,
    topic_filter: TopicFilter = TopicFilter(),
) -> tuple[int, list[SearchHit]]:
    """Return `(total, hits)`: the match count before any crop, then the page.

    A non-`None` `topic_filter.status` or `topic_filter.type` narrows the items
    handed to the scorer, and the filtered subset IS the corpus: `N`, `df` and
    `avgdl` recompute over it, so the remaining scores differ from an
    unfiltered run of the same query. Behind the final sort, `offset` skips
    and `topic_filter.limit` crops the top N, `0` giving an explicit empty
    result. `total` is the number of scoring hits BEFORE either crop, so a
    paged run never hides that the other pages exist. The default filter
    restricts nothing, so a call without it behaves exactly as before.

    An item scores only on the query terms it contains, so an item with no
    query token is never a result. Order is score descending, then `item_id`
    ascending, so equal scores always come out in the same order.
    """
    selected = [
        item
        for item in items
        if (topic_filter.status is None or item.status == topic_filter.status)
        and (topic_filter.type is None or item.type == topic_filter.type)
    ]
    query_terms = list(dict.fromkeys(tokenize(query)))
    tokens_per_item = [tokenize(item.statement) for item in selected]
    if not query_terms or not selected:
        return 0, []
    average_length = sum(len(tokens) for tokens in tokens_per_item) / len(selected)
    if average_length == 0:
        return 0, []

    hits: list[SearchHit] = []
    counters_per_item = [Counter(tokens) for tokens in tokens_per_item]
    token_sets = [set(tokens) for tokens in tokens_per_item]
    document_frequency = {
        term: sum(1 for token_set in token_sets if term in token_set)
        for term in query_terms
    }
    for item, tokens, counts in zip(selected, tokens_per_item, counters_per_item):
        score = 0.0
        for term in query_terms:
            frequency = counts[term]
            if frequency == 0:
                continue
            length_ratio = len(tokens) / average_length
            denominator = frequency + K1 * (1 - B + B * length_ratio)
            score += _idf(len(selected), document_frequency[term]) * (
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
    ranked = sorted(hits, key=lambda hit: (-hit.score, hit.item_id))
    total = len(ranked)
    start = 0 if topic_filter.offset is None else topic_filter.offset
    window = ranked[start:]
    if topic_filter.limit is not None:
        window = window[: topic_filter.limit]
    return total, window

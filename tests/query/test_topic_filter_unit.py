"""Unit tests for topic-search filters: the corpus narrows, the limit crops."""

from __future__ import annotations

from ember.query.rows import TopicFilter
from ember.query.topic_search import topic_search
from tests.query.fakes import make_item


def _mixed_items():
    """Item 1 Active Decision, item 2 Closed Finding, item 3 Closed Decision."""
    return [
        make_item(1, status="Active", item_type="Decision", statement="Use SQLite"),
        make_item(
            2, status="Closed", item_type="Finding", statement="Use SQLite"
        ),
        make_item(3, status="Closed", item_type="Decision", statement="Use SQLite"),
    ]


def test_default_topic_filter_scores_every_item() -> None:
    items = _mixed_items()

    with_default = topic_search(items, "sqlite", TopicFilter())
    without_arg = topic_search(items, "sqlite")

    assert [hit.item_id for hit in with_default] == [1, 2, 3]
    assert with_default == without_arg


def test_status_and_type_filter_the_items_handed_to_the_scorer() -> None:
    items = _mixed_items()
    unfiltered = topic_search(items, "sqlite")

    active = topic_search(items, "sqlite", TopicFilter(status="Active"))
    closed = topic_search(items, "sqlite", TopicFilter(status="Closed"))
    findings = topic_search(items, "sqlite", TopicFilter(type="Finding"))
    both = topic_search(
        items, "sqlite", TopicFilter(status="Closed", type="Decision")
    )

    # The Active axis: the Closed hits drop out and the score recomputes over
    # the smaller corpus, so it differs from the same item in the full run.
    assert [hit.item_id for hit in active] == [1]
    assert active[0].score != unfiltered[0].score
    # The reverse axis: only the Closed item stays.
    assert [hit.item_id for hit in closed] == [2, 3]
    # The type axis alone filters too.
    assert [hit.item_id for hit in findings] == [2]
    # Both axes combine as AND.
    assert [hit.item_id for hit in both] == [3]


def test_limit_windows_after_ranking() -> None:
    items = [
        make_item(1, statement="Use SQLite"),
        make_item(2, statement="SQLite SQLite index"),
        make_item(3, statement="SQLite plans"),
    ]

    ranked = topic_search(items, "sqlite")
    windowed = topic_search(items, "sqlite", TopicFilter(limit=2))
    empty = topic_search(items, "sqlite", TopicFilter(limit=0))

    # Item 2 mentions the term twice, so it outranks the others by score.
    assert ranked[0].item_id == 2
    assert [hit.item_id for hit in windowed] == [
        hit.item_id for hit in ranked[:2]
    ]
    assert [hit.item_id for hit in windowed] != [1, 2]
    assert empty == []

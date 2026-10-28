"""Unit tests for the `why` traversal: directions, cycles, depth, rationale."""

from __future__ import annotations

from ember.query.why import why
from ember.relate.rows import Link
from tests.fakes import FIXED_TIME
from tests.query.fakes import make_item


def _link(
    link_id: int,
    source: int,
    target: int,
    link_type: str,
    *,
    status: str = "Confirmed",
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source,
        target_item_id=target,
        link_type=link_type,
        status=status,
        created_at=FIXED_TIME,
    )


def test_depends_on_yields_the_target_as_the_premise() -> None:
    items = [make_item(1, statement="Ship it"), make_item(2, statement="It compiles")]
    links = [_link(10, 1, 2, "depends_on")]

    result = why(items, links, 1)

    assert [(r.item_id, r.depth, r.via_link_type, r.via_link_id) for r in result.reasons] == [
        (2, 1, "depends_on", 10)
    ]


def test_supports_yields_the_source_as_the_evidence() -> None:
    items = [make_item(1, statement="Evidence"), make_item(2, statement="Claim")]
    links = [_link(10, 1, 2, "supports")]

    result = why(items, links, 2)

    assert [r.item_id for r in result.reasons] == [1]
    assert result.reasons[0].via_link_type == "supports"


def test_the_start_item_is_not_a_reason() -> None:
    items = [make_item(1), make_item(2)]
    links = [_link(10, 1, 2, "depends_on")]

    result = why(items, links, 1)

    assert result.item.id == 1
    assert 1 not in [reason.item_id for reason in result.reasons]


def test_rejected_link_yields_nothing() -> None:
    items = [make_item(1), make_item(2)]
    links = [_link(10, 1, 2, "depends_on", status="Rejected")]

    assert why(items, links, 1).reasons == []


def test_depends_on_cycle_terminates_with_each_item_once() -> None:
    items = [make_item(1), make_item(2)]
    links = [_link(10, 1, 2, "depends_on"), _link(11, 2, 1, "depends_on")]

    reasons = why(items, links, 1).reasons

    assert [reason.item_id for reason in reasons] == [2]


def test_traversal_is_transitive_and_carries_depth() -> None:
    items = [make_item(1), make_item(2), make_item(3)]
    links = [_link(10, 1, 2, "depends_on"), _link(11, 3, 2, "supports")]

    reasons = why(items, links, 1).reasons

    assert [(reason.item_id, reason.depth) for reason in reasons] == [(2, 1), (3, 2)]


def test_ignores_link_types_that_are_not_reasons() -> None:
    items = [make_item(1), make_item(2)]
    links = [_link(10, 1, 2, "supersedes"), _link(11, 1, 2, "answers")]

    assert why(items, links, 1).reasons == []


def test_reason_carries_its_own_rationale_or_null() -> None:
    items = [
        make_item(1),
        make_item(2, rationale="Because the schema allows it"),
        make_item(3),
    ]
    links = [_link(10, 1, 2, "depends_on"), _link(11, 1, 3, "depends_on")]

    reasons = {reason.item_id: reason.rationale for reason in why(items, links, 1).reasons}

    assert reasons == {2: "Because the schema allows it", 3: None}


def test_item_with_no_reasons_yields_an_empty_list() -> None:
    result = why([make_item(1)], [], 1)

    assert result.reasons == []
    assert result.item.id == 1

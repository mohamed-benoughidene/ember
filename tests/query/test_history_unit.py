"""Unit tests for the `change_log` classifier and the `history` derivation."""

from __future__ import annotations

import pytest

from ember.query.history import classify_change_row, history
from ember.query.rows import ChangeRow
from ember.relate.rows import Link
from tests.fakes import FIXED_TIME
from tests.query.fakes import make_change_row, make_link


PAIR_CASES = [
    (("created", "user_confirmed"), "created"),
    (("proposed", "rejected"), "proposed_rejected"),
    (("validated", "user_set_validated"), "validated"),
    (("link_confirmed", "user_confirmed"), "link_confirmed"),
    (("link_rejected", "rejected"), "link_rejected"),
    (("status", "supersedes_confirmed"), "status_changed"),
    (("status", "answers_confirmed"), "status_changed"),
    (("status", "dependency_closed"), "status_changed"),
    (("status", "contradicts_confirmed"), "status_changed"),
    (("status", "user_closed"), "status_changed"),
    (("status", "user_set_status"), "status_changed"),
    (("status", "reversal"), "status_changed"),
    (("status_origin", "user_set_status"), "status_origin_changed"),
    (("link_reversed", "reversal"), "link_reversed"),
]


@pytest.mark.parametrize(("pair", "kind"), PAIR_CASES)
def test_each_documented_pair_maps_to_its_kind(pair, kind: str) -> None:
    row = make_change_row(field_changed=pair[0], trigger_cause=pair[1])

    assert classify_change_row(row) == kind


def test_the_seven_status_causes_are_told_apart_only_by_the_cause() -> None:
    kinds = {
        classify_change_row(
            make_change_row(field_changed="status", trigger_cause=cause)
        )
        for _, cause in [
            ("status", "supersedes_confirmed"),
            ("status", "answers_confirmed"),
            ("status", "dependency_closed"),
            ("status", "contradicts_confirmed"),
            ("status", "user_closed"),
            ("status", "user_set_status"),
            ("status", "reversal"),
        ]
    }

    assert kinds == {"status_changed"}


def test_user_set_status_is_told_apart_by_the_field() -> None:
    assert (
        classify_change_row(
            make_change_row(field_changed="status", trigger_cause="user_set_status")
        )
        == "status_changed"
    )
    assert (
        classify_change_row(
            make_change_row(
                field_changed="status_origin", trigger_cause="user_set_status"
            )
        )
        == "status_origin_changed"
    )


def test_unrecognised_field_renders_as_unknown_with_raw_values() -> None:
    row = make_change_row(
        field_changed="sentiment",
        trigger_cause="ai_suggested",
        old_value="neutral",
        new_value="happy",
    )

    (event,) = history([row], [], None)

    assert event.kind == "unknown"
    assert event.field_changed == "sentiment"
    assert event.cause == "ai_suggested"
    assert (event.old_value, event.new_value) == ("neutral", "happy")
    assert event.item_id == 1


@pytest.mark.parametrize(
    ("new_value", "expected"),
    [
        ("Closed:superseded", "superseded"),
        ("Closed", None),
        ("Closed:None", None),
        ("Closed:", None),
        ("Active", None),
    ],
)
def test_close_reason_splitter(new_value: str, expected) -> None:
    row = make_change_row(
        field_changed="status", trigger_cause="user_closed", new_value=new_value
    )

    (event,) = history([row], [], None)

    assert event.close_reason == expected


def test_status_origin_and_link_reversed_have_no_close_reason() -> None:
    rows = [
        make_change_row(
            field_changed="status_origin",
            trigger_cause="user_set_status",
            new_value="manual",
        ),
        make_change_row(
            field_changed="link_reversed",
            trigger_cause="reversal",
            new_value="Reversed",
        ),
    ]

    events = history(rows, [], None)

    assert [event.kind for event in events] == [
        "status_origin_changed",
        "link_reversed",
    ]
    assert [event.close_reason for event in events] == [None, None]


def test_rejected_proposal_row_belongs_to_no_item_but_shows_globally() -> None:
    row = make_change_row(
        item_id=None, field_changed="proposed", trigger_cause="rejected"
    )

    assert history([row], [], 1) == []
    assert len(history([row], [], None)) == 1


def test_row_is_included_when_its_item_id_matches() -> None:
    row = make_change_row(item_id=7, field_changed="created")

    events = history([row], [], 7)

    assert [event.item_id for event in events] == [7]


def test_row_is_included_when_the_link_touches_the_item_as_target() -> None:
    # Engine B writes item_id = the link's SOURCE, so item 2 is reached by link.
    row = make_change_row(
        item_id=1,
        link_id=10,
        field_changed="link_confirmed",
        trigger_cause="user_confirmed",
    )
    link = make_link(10, 1, 2)

    events = history([row], [link], 2)

    assert len(events) == 1
    assert events[0].link_target_item_id == 2
    assert events[0].link_type == "depends_on"


def test_unrelated_item_and_unrelated_link_are_excluded() -> None:
    row = make_change_row(item_id=1, link_id=10)
    row_other = make_change_row(row_id=2, item_id=5, link_id=11)

    events = history([row, row_other], [make_link(10, 1, 2), make_link(11, 5, 6)], 3)

    assert events == []


def test_row_matching_both_conditions_appears_once() -> None:
    row = make_change_row(
        item_id=1,
        link_id=10,
        field_changed="link_confirmed",
        trigger_cause="user_confirmed",
    )

    events = history([row], [make_link(10, 1, 2)], 1)

    assert len(events) == 1


def test_events_are_ordered_by_timestamp_then_id() -> None:
    rows = [
        make_change_row(
            row_id=3, new_value="c", timestamp="2026-01-01T00:00:02+00:00"
        ),
        make_change_row(
            row_id=1, new_value="a", timestamp="2026-01-01T00:00:01+00:00"
        ),
        make_change_row(
            row_id=2, new_value="b", timestamp="2026-01-01T00:00:01+00:00"
        ),
    ]

    events = history(rows, [], None)

    assert [event.new_value for event in events] == ["a", "b", "c"]


def test_link_fields_are_filled_from_the_named_link() -> None:
    row = make_change_row(link_id=10)

    (event,) = history([row], [make_link(10, 4, 9)], None)

    assert (event.link_source_item_id, event.link_target_item_id) == (4, 9)
    assert event.link_type == "depends_on"


def test_link_fields_are_null_when_the_row_names_no_link() -> None:
    (event,) = history([make_change_row(link_id=None)], [], None)

    assert event.link_source_item_id is None
    assert event.link_target_item_id is None
    assert event.link_type is None

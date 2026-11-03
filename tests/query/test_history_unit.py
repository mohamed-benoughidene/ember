"""Unit tests for the `change_log` classifier and the `history` derivation."""

from __future__ import annotations

import pytest

from ember.query.history import classify_change_row, history
from ember.query.rows import HistoryPage
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
    (("status_origin", "sweep_rearm"), "status_origin_changed"),
    (("link_reversed", "reversal"), "link_reversed"),
]


@pytest.mark.parametrize(("pair", "kind"), PAIR_CASES)
def test_each_documented_pair_maps_to_its_kind(pair, kind: str) -> None:
    row = make_change_row(field_changed=pair[0], trigger_cause=pair[1])

    assert classify_change_row(row) == kind


def test_the_edit_and_remove_link_pairs_have_kinds() -> None:
    """The real writer causes (Batch 6, finding 4.7 #4): `user_edit_item`
    writes the `rationale` field row and `user_remove_link` writes the
    `link_removed` row. Neither may fall to `unknown`."""
    assert (
        classify_change_row(
            make_change_row(
                field_changed="rationale", trigger_cause="user_edit_item", item_id=1
            )
        )
        == "item_edited"
    )
    assert (
        classify_change_row(
            make_change_row(
                field_changed="link_removed",
                trigger_cause="user_remove_link",
                item_id=1,
            )
        )
        == "link_removed"
    )


def test_a_source_edit_row_maps_to_the_same_item_edited_kind() -> None:
    """Issue #44: `edit-item --field source` writes the OTHER pair the
    real edit-item writer produces (`ember/maintain/human_actions.py`
    writes `field='rationale'` or `field='source'` with cause
    `user_edit_item`). It must map to the SAME kind as the rationale
    pair, `item_edited`, not fall to the `unknown` fallback."""
    assert (
        classify_change_row(
            make_change_row(
                field_changed="source", trigger_cause="user_edit_item", item_id=1
            )
        )
        == "item_edited"
    )
    assert (
        classify_change_row(
            make_change_row(field_changed="rationale", trigger_cause="user_edit_item")
        )
        == "item_edited"
    )


def test_history_read_newest_first() -> None:
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

    # Newest first: the later write first; the same-instant rows by id,
    # the higher id first.
    assert [(event.timestamp, event.new_value) for event in events] == [
        ("2026-01-01T00:00:02+00:00", "c"),
        ("2026-01-01T00:00:01+00:00", "b"),
        ("2026-01-01T00:00:01+00:00", "a"),
    ]


def test_offset_pages_back_in_time() -> None:
    rows = [
        make_change_row(
            row_id=1, new_value="a", timestamp="2026-01-01T00:00:00+00:00"
        ),
        make_change_row(
            row_id=2, new_value="b", timestamp="2026-01-01T00:00:01+00:00"
        ),
        make_change_row(
            row_id=3, new_value="c", timestamp="2026-01-01T00:00:02+00:00"
        ),
    ]

    # The FIRST page holds the newest lines; walking the offset forward
    # walks BACK in time.
    first_page = history(rows, [], None, HistoryPage(offset=0, limit=2))
    second_page = history(rows, [], None, HistoryPage(offset=2, limit=2))

    assert [event.new_value for event in first_page] == ["c", "b"]
    assert [event.new_value for event in second_page] == ["a"]


def test_a_closed_status_renders_the_derived_status_and_reason_not_the_raw_encoding() -> None:
    """Batch 6, 4.7 #14: the event shows `Closed` + `expired`, never the
    raw `Closed:expired` writer encoding — that stays only in the ledger."""
    row = make_change_row(
        field_changed="status", trigger_cause="user_closed", new_value="Closed:expired"
    )

    (event,) = history([row], [], None)

    assert event.close_reason == "expired"
    assert event.new_value == "Closed"
    assert event.new_value != "Closed:expired"


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
        (None, None),
    ],
)
def test_close_reason_splitter(new_value, expected) -> None:
    row = make_change_row(
        field_changed="status", trigger_cause="user_closed", new_value=new_value
    )

    (event,) = history([row], [], None)

    assert event.close_reason == expected


def test_a_closed_item_with_a_null_close_reason_renders_without_failing() -> None:
    """Issue #23: nothing ties `status = 'Closed'` to a non-null reason.

    A row whose new value is a bare `Closed`, and a NULL value with no status
    at all, both render as `close_reason: None` instead of failing.
    """
    rows = [
        make_change_row(
            row_id=1,
            field_changed="status",
            trigger_cause="user_closed",
            new_value="Closed",
        ),
        make_change_row(
            row_id=2,
            field_changed="status",
            trigger_cause="user_closed",
            new_value=None,
        ),
    ]

    events = history(rows, [], None)

    # Newest first: the id-2 NULL row shares the id-1 row's timestamp, so
    # the higher id renders first. Values still decode safely:
    # `Closed` renders as `Closed` with reason None, NULL stays NULL.
    assert [(event.new_value, event.close_reason) for event in events] == [
        (None, None),
        ("Closed", None),
    ]


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


def test_events_are_ordered_newest_first() -> None:
    """Batch 6 (4.7 #13): `(timestamp, id)` DESCENDING — the newest
    write first, the same-instant rows by the higher id first."""
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

    assert [event.new_value for event in events] == ["c", "b", "a"]


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


# ---------------------------------------------------------------------------
# Undo step 05: every undo/redo pair keeps its kind (L2 §5.6) — nothing the
# undo engine writes may fall to `unknown`.
# ---------------------------------------------------------------------------

UNDO_REDO_KIND_BY_PAIR = [
    (("status", "user_undo"), "status_changed"),
    (("status", "user_redo"), "status_changed"),
    (("validated", "user_undo"), "validated"),
    (("validated", "user_redo"), "validated"),
    (("link_removed", "user_undo"), "link_confirmed"),
    (("link_removed", "user_redo"), "link_removed"),
    (("rationale", "user_undo"), "item_edited"),
    (("rationale", "user_redo"), "item_edited"),
    (("source", "user_undo"), "item_edited"),
    (("source", "user_redo"), "item_edited"),
    (("status_origin", "user_undo"), "status_origin_changed"),
    (("status_origin", "user_redo"), "status_origin_changed"),
    (("link_reversed", "user_undo"), "link_reversed"),
    (("link_reversed", "user_redo"), "link_reversed"),
]


@pytest.mark.parametrize(("pair", "kind"), UNDO_REDO_KIND_BY_PAIR)
def test_no_undo_or_redo_row_of_a_human_pair_is_unknown(pair, kind: str) -> None:
    row = make_change_row(field_changed=pair[0], trigger_cause=pair[1])

    assert classify_change_row(row) == kind
    assert classify_change_row(row) != "unknown"


def test_the_undo_redo_pointers_and_the_unreversal_marker_have_kinds() -> None:
    assert (
        classify_change_row(
            make_change_row(field_changed="undo_of", trigger_cause="user_undo")
        )
        == "undone"
    )
    assert (
        classify_change_row(
            make_change_row(field_changed="redo_of", trigger_cause="user_redo")
        )
        == "redone"
    )
    assert (
        classify_change_row(
            make_change_row(
                field_changed="link_unreversed", trigger_cause="user_undo"
            )
        )
        == "link_unreversed"
    )


def test_a_redone_close_keeps_its_close_reason_and_an_undone_one_has_none() -> None:
    """The close reason rides the status value, so an inverse status row of
    the SAME kind (`status_changed`) keeps it (L2 §5.6)."""
    rows = [
        make_change_row(
            row_id=1,
            field_changed="status",
            trigger_cause="user_undo",
            new_value="Active",
        ),
        make_change_row(
            row_id=2,
            field_changed="status",
            trigger_cause="user_redo",
            new_value="Closed:invalidated",
        ),
    ]

    # Same timestamp on both rows, so the redo (id 2) renders first.
    (redo_event, undo_event) = history(rows, [], None)

    assert (undo_event.kind, undo_event.close_reason) == ("status_changed", None)
    assert (redo_event.kind, redo_event.close_reason) == (
        "status_changed",
        "invalidated",
    )


def test_the_unknown_fallback_covers_even_an_undo_cause() -> None:
    row = make_change_row(field_changed="sentiment", trigger_cause="user_undo")

    assert classify_change_row(row) == "unknown"

"""Unit tests for the pure Phase-2 derivation, no DB."""

from __future__ import annotations

import pytest

from ember.maintain.derive import derive_status_changes, merge_and_filter
from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange
from ember.relate.rows import Link
from tests.maintain.fakes import FakeMaintainLookup

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _item(
    item_id: int,
    item_type: str = "Decision",
    status: str = "Active",
    close_reason: str | None = None,
    status_origin: str = "derived",
) -> ItemState:
    return ItemState(
        id=item_id,
        type=item_type,
        status=status,
        close_reason=close_reason,
        status_origin=status_origin,
    )


def _link(
    link_id: int,
    source_id: int,
    target_id: int,
    link_type: str,
    status: str = "Confirmed",
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_id,
        target_item_id=target_id,
        link_type=link_type,
        status=status,
        created_at=FIXED_TIME,
    )


def _snap(
    items: list[ItemState],
    links: list[Link] | None = None,
    reversed_ids: set[int] | None = None,
) -> MaintainSnapshot:
    lookup = FakeMaintainLookup(
        items=items, links=links, reversed_link_ids=reversed_ids
    )
    return MaintainSnapshot(
        items=lookup.list_items(),
        links=lookup.list_confirmed_links(),
        reversed_link_ids=lookup.list_reversed_link_ids(),
    )


def test_rule1_supersedes_closes_target_superseded() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision")],
        [_link(10, 1, 2, "supersedes")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    change = changes[0]
    assert change.item_id == 2
    assert change.old_status == "Active"
    assert change.new_status == "Closed"
    assert change.close_reason == "superseded"
    assert change.trigger_cause == "supersedes_confirmed"
    assert change.link_id == 10


@pytest.mark.parametrize("reason", ["invalidated", "superseded", "reversed"])
def test_rule2_dependency_closed_flags_dependent(reason: str) -> None:
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(2, "Decision", status="Closed", close_reason=reason),
        ],
        [_link(10, 1, 2, "depends_on")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 1
    assert changes[0].new_status == "Challenged"
    assert changes[0].trigger_cause == "dependency_closed"
    assert changes[0].link_id == 10


@pytest.mark.parametrize("reason", ["answered", "expired"])
def test_rule2_non_flagging_reasons_do_not_challenge(reason: str) -> None:
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(2, "Decision", status="Closed", close_reason=reason),
        ],
        [_link(10, 1, 2, "depends_on")],
    )

    assert derive_status_changes(snapshot) == []


def test_rule2_same_sweep_close_flags_dependent() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision"), _item(3, "Decision")],
        [_link(10, 2, 3, "supersedes"), _link(11, 1, 3, "depends_on")],
    )

    changes = {change.item_id: change for change in derive_status_changes(snapshot)}

    assert set(changes) == {1, 3}
    assert changes[3].new_status == "Closed"
    assert changes[3].close_reason == "superseded"
    assert changes[1].new_status == "Challenged"
    assert changes[1].trigger_cause == "dependency_closed"


def test_rule2_is_single_step_only() -> None:
    # 3 is Closed/invalidated; 2 depends on 3 -> challenged; 1 depends on 2.
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(2, "Decision"),
            _item(3, "Decision", status="Closed", close_reason="invalidated"),
        ],
        [_link(10, 2, 3, "depends_on"), _link(11, 1, 2, "depends_on")],
    )

    changes = derive_status_changes(snapshot)

    assert [change.item_id for change in changes] == [2]
    assert changes[0].new_status == "Challenged"


def test_rule3_contradicts_challenges_target() -> None:
    snapshot = _snap(
        [_item(1, "Finding"), _item(2, "Decision")],
        [_link(10, 1, 2, "contradicts")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Challenged"
    assert changes[0].trigger_cause == "contradicts_confirmed"
    assert changes[0].link_id == 10


def test_rule4_answers_closes_question() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Question")],
        [_link(10, 1, 2, "answers")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Closed"
    assert changes[0].close_reason == "answered"
    assert changes[0].trigger_cause == "answers_confirmed"
    assert changes[0].link_id == 10


def test_tie_break_superseded_beats_answered() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Question"), _item(3, "Question")],
        [_link(10, 3, 2, "supersedes"), _link(11, 1, 2, "answers")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].close_reason == "superseded"
    assert changes[0].trigger_cause == "supersedes_confirmed"
    assert changes[0].link_id == 10


def test_one_change_per_item_superseded_beats_contradicted() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision"), _item(3, "Finding")],
        [_link(10, 1, 2, "supersedes"), _link(11, 3, 2, "contradicts")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Closed"
    assert changes[0].close_reason == "superseded"


def test_one_change_per_item_rule2_and_rule3_agree_on_challenged() -> None:
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(3, "Finding"),
            _item(4, "Decision", status="Closed", close_reason="invalidated"),
        ],
        [_link(10, 3, 1, "contradicts"), _link(11, 1, 4, "depends_on")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 1
    assert changes[0].new_status == "Challenged"


def test_one_change_per_item_rule1_beats_rule2() -> None:
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(2, "Decision"),
            _item(3, "Decision", status="Closed", close_reason="invalidated"),
        ],
        [_link(10, 2, 1, "supersedes"), _link(11, 1, 3, "depends_on")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 1
    assert changes[0].new_status == "Closed"
    assert changes[0].close_reason == "superseded"


def test_reversed_supersedes_link_is_not_live() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision")],
        [_link(10, 1, 2, "supersedes")],
        {10},
    )

    assert derive_status_changes(snapshot) == []


def test_rejected_links_are_ignored() -> None:
    snapshot = MaintainSnapshot(
        items=[
            _item(1, "Finding"),
            _item(2, "Decision"),
            _item(3, "Decision"),
            _item(4, "Decision"),
            _item(5, "Question"),
            _item(6, "Decision", status="Closed", close_reason="invalidated"),
        ],
        links=[
            _link(10, 1, 2, "contradicts", status="Rejected"),
            _link(11, 3, 4, "supersedes", status="Rejected"),
            _link(12, 2, 5, "answers", status="Rejected"),
            _link(13, 3, 6, "depends_on", status="Rejected"),
        ],
        reversed_link_ids=set(),
    )

    assert derive_status_changes(snapshot) == []


def test_escalation_only_never_reopens_challenged_to_active() -> None:
    snapshot = _snap([_item(1, "Decision", status="Challenged")])
    candidate = StatusChange(
        item_id=1,
        old_status="Challenged",
        new_status="Active",
        close_reason=None,
        trigger_cause="user_set_status",
        link_id=None,
    )

    assert merge_and_filter([candidate], snapshot) == []


def test_escalation_only_never_recloses_and_keeps_human_reason() -> None:
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(2, "Decision", status="Closed", close_reason="invalidated"),
        ],
        [_link(10, 1, 2, "supersedes")],
    )

    assert derive_status_changes(snapshot) == []


def test_manual_shield_skips_derived_change() -> None:
    snapshot = _snap(
        [
            _item(1, "Decision"),
            _item(2, "Decision", status_origin="manual"),
        ],
        [_link(10, 1, 2, "supersedes")],
    )

    assert derive_status_changes(snapshot) == []


def test_old_status_is_observed_not_constant() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision", status="Challenged")],
        [_link(10, 1, 2, "supersedes")],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].old_status == "Challenged"
    assert changes[0].new_status == "Closed"


def test_unknown_target_id_is_skipped() -> None:
    snapshot = _snap([_item(1, "Decision")], [_link(10, 1, 99, "supersedes")])

    assert derive_status_changes(snapshot) == []


def test_empty_snapshot_returns_empty() -> None:
    snapshot = MaintainSnapshot(items=[], links=[], reversed_link_ids=set())

    assert derive_status_changes(snapshot) == []


def test_exempt_change_bypasses_ladder_and_manual_shield() -> None:
    snapshot = _snap(
        [_item(1, "Decision", status="Challenged", status_origin="manual")]
    )
    primary = StatusChange(
        item_id=1,
        old_status="Challenged",
        new_status="Active",
        close_reason=None,
        trigger_cause="user_set_status",
        link_id=None,
    )

    assert merge_and_filter([primary], snapshot) == []
    assert merge_and_filter([primary], snapshot, exempt=primary) == [primary]

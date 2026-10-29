"""Unit tests for the pure Phase-2 derivation, no DB."""

from __future__ import annotations

import pytest

from ember.maintain.derive import derive_status_changes, merge_and_filter
from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange
from ember.relate.rows import ChangeLogEntry, Link
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
    created_at: str = FIXED_TIME,
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_id,
        target_item_id=target_id,
        link_type=link_type,
        status=status,
        created_at=created_at,
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
    # Still passes byte-for-byte under the timestamp-scoped shield: the
    # snapshot carries no `shield_log`, so this is the fail-closed branch
    # (no clear row visible), not the old blanket veto.
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


# --- Timestamp-scoped manual shield (L2 maintain plan §13, step 06) ---
#
# The snapshot's default `shield_log` is empty, so the old blanket-shield
# tests above now exercise the fail-closed branch (no clear row visible).

T1 = "2026-01-01T00:00:00+00:00"
T2 = "2027-01-01T00:00:00+00:00"
T3 = "2028-01-01T00:00:00+00:00"


def _snap_shielded(
    items: list[ItemState],
    links: list[Link] | None = None,
    shield_log: list[ChangeLogEntry] | None = None,
) -> MaintainSnapshot:
    """A snapshot that carries the Phase-1 `shield_log` ledger slice."""
    lookup = FakeMaintainLookup(
        items=items, links=links, shield_log=shield_log
    )
    return MaintainSnapshot(
        items=lookup.list_items(),
        links=lookup.list_confirmed_links(),
        reversed_link_ids=lookup.list_reversed_link_ids(),
        shield_log=lookup.list_shield_log(),
    )


def _clear_row(item_id: int, timestamp: str, row_id: int) -> ChangeLogEntry:
    """A manual-clear ledger row, the shape `apply_status_origin` writes."""
    return ChangeLogEntry(
        id=row_id,
        item_id=item_id,
        link_id=None,
        field_changed="status_origin",
        old_value="manual",
        new_value="manual",
        timestamp=timestamp,
        trigger_cause="user_set_status",
    )


def _evidence_row(
    link_id: int, item_id: int, timestamp: str, row_id: int
) -> ChangeLogEntry:
    """A link-confirmation ledger row, the shape the relate gatekeeper
    writes at confirm time (new_value typed to the contradicts case)."""
    return ChangeLogEntry(
        id=row_id,
        item_id=item_id,
        link_id=link_id,
        field_changed="link_confirmed",
        old_value=None,
        new_value=f"contradicts:{item_id}",
        timestamp=timestamp,
        trigger_cause="user_confirmed",
    )


def _evidence_row_for(
    link_type: str, link_id: int, item_id: int, timestamp: str, row_id: int
) -> ChangeLogEntry:
    """Same as `_evidence_row` with a different `new_value` link type."""
    return _evidence_row(
        link_id, item_id, timestamp, row_id
    ).model_copy(update={"new_value": f"{link_type}:{item_id}"})


def test_newer_contradicts_passes_manual_shield() -> None:
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T2)],
        [_clear_row(2, T1, 1), _evidence_row(10, 1, T2, 2)],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Challenged"
    assert changes[0].trigger_cause == "contradicts_confirmed"


def test_older_contradicts_stays_silent() -> None:
    # Evidence predates the clear: silent whether the human saw it or not.
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T1)],
        [_clear_row(2, T2, 2), _evidence_row(10, 1, T1, 1)],
    )

    assert derive_status_changes(snapshot) == []


def test_newer_supersedes_closes_shielded_item() -> None:
    # Full scope: a derived close also fires on a shielded card.
    snapshot = _snap_shielded(
        [_item(1, "Decision"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "supersedes", created_at=T2)],
        [
            _clear_row(2, T1, 1),
            _evidence_row_for("supersedes", 10, 1, T2, 2),
        ],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Closed"
    assert changes[0].close_reason == "superseded"


def test_newer_answers_closes_shielded_question() -> None:
    snapshot = _snap_shielded(
        [_item(1, "Decision"), _item(2, "Question", status_origin="manual")],
        [_link(10, 1, 2, "answers", created_at=T2)],
        [
            _clear_row(2, T1, 1),
            _evidence_row_for("answers", 10, 1, T2, 2),
        ],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Closed"
    assert changes[0].close_reason == "answered"


def test_same_timestamp_tie_older_evidence_id_stays_silent() -> None:
    # Equal timestamps resolve by the higher change_log id. The evidence
    # row lost the tie (id 2 < clear id 3), so it stays silent.
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T1)],
        [_clear_row(2, T1, 3), _evidence_row(10, 1, T1, 2)],
    )

    assert derive_status_changes(snapshot) == []


def test_same_timestamp_tie_newer_evidence_id_passes() -> None:
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T1)],
        [_clear_row(2, T1, 2), _evidence_row(10, 1, T1, 3)],
    )

    changes = derive_status_changes(snapshot)

    assert len(changes) == 1
    assert changes[0].item_id == 2
    assert changes[0].new_status == "Challenged"


def test_newest_clear_sets_the_boundary() -> None:
    # Clear T1, evidence T2, clear T3: the newest clear is THE boundary.
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T2)],
        [
            _clear_row(2, T1, 1),
            _evidence_row(10, 1, T2, 2),
            _clear_row(2, T3, 3),
        ],
    )

    assert derive_status_changes(snapshot) == []


def test_newest_clear_wins_on_equal_timestamps() -> None:
    # Two clears at the same timestamp: the higher id is the boundary. If
    # the older clear (id 1) won, the evidence (id 2) would pass.
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T1)],
        [
            _clear_row(2, T1, 1),
            _evidence_row(10, 1, T1, 2),
            _clear_row(2, T1, 3),
        ],
    )

    assert derive_status_changes(snapshot) == []


def test_rearm_is_stamped_on_passing_shield_changes() -> None:
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T2)],
        [_clear_row(2, T1, 1), _evidence_row(10, 1, T2, 2)],
    )

    changes = derive_status_changes(snapshot)

    assert changes == [
        StatusChange(
            item_id=2,
            old_status="Active",
            new_status="Challenged",
            close_reason=None,
            old_close_reason=None,
            trigger_cause="contradicts_confirmed",
            link_id=10,
            rearm=True,
        )
    ]


def test_exempt_change_does_not_rearm() -> None:
    # The human path is exempt: the shield check is bypassed and rearm is
    # never stamped, even when the shield_log would let evidence pass.
    snapshot = _snap_shielded(
        [_item(1, "Decision", status="Challenged", status_origin="manual")],
        shield_log=[_clear_row(1, T1, 1)],
    )
    primary = StatusChange(
        item_id=1,
        old_status="Challenged",
        new_status="Active",
        close_reason=None,
        trigger_cause="user_set_status",
        link_id=None,
    )

    result = merge_and_filter([primary], snapshot, exempt=primary)

    assert result == [primary]
    assert result[0].rearm is False


def test_links_created_at_is_not_the_evidence_clock() -> None:
    # The pinned evidence source is the `link_confirmed` ledger row, not
    # `links.created_at`: here created_at (T3) says the link is newer than
    # the clear (T2), but the ledger row (T1) says older, and the ledger
    # row decides: silent.
    snapshot = _snap_shielded(
        [_item(1, "Finding"), _item(2, "Decision", status_origin="manual")],
        [_link(10, 1, 2, "contradicts", created_at=T3)],
        [_clear_row(2, T2, 2), _evidence_row(10, 1, T1, 1)],
    )

    assert derive_status_changes(snapshot) == []

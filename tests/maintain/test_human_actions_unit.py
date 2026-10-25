"""Unit tests for the pure human-command validators, no DB."""

from __future__ import annotations

import pytest

from ember.maintain.errors import (
    CloseReasonInvalid,
    CloseReasonMismatch,
    ItemAlreadyClosed,
    MaintainItemNotFound,
    ReversalPreconditionFailed,
    StatusTransitionInvalid,
)
from ember.maintain.human_actions import (
    validate_close_item,
    validate_reverse_supersedes,
    validate_set_status,
)
from ember.maintain.rows import ItemState, MaintainSnapshot
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


# --------------------------------------------------------------------------
# validate_close_item
# --------------------------------------------------------------------------


def test_close_item_invalidated_happy_path() -> None:
    snapshot = _snap([_item(1)])

    changes = validate_close_item(snapshot, 1, "invalidated")

    assert len(changes) == 1
    change = changes[0]
    assert change.item_id == 1
    assert change.old_status == "Active"
    assert change.new_status == "Closed"
    assert change.close_reason == "invalidated"
    assert change.old_close_reason is None
    assert change.trigger_cause == "user_closed"
    assert change.link_id is None


def test_close_item_expired_happy_path() -> None:
    snapshot = _snap([_item(1)])

    changes = validate_close_item(snapshot, 1, "expired")

    assert len(changes) == 1
    assert changes[0].close_reason == "expired"


def test_close_item_bogus_reason_raises_002() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(CloseReasonInvalid) as exc:
        validate_close_item(snapshot, 1, "bogus")

    assert exc.value.code == "MAINTAIN-002"


@pytest.mark.parametrize("reason", ["superseded", "answered", "reversed"])
def test_close_item_machine_reason_raises_003(reason: str) -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(CloseReasonMismatch) as exc:
        validate_close_item(snapshot, 1, reason)

    assert exc.value.code == "MAINTAIN-003"


def test_close_item_already_closed_raises_004() -> None:
    snapshot = _snap([_item(1, status="Closed", close_reason="invalidated")])

    with pytest.raises(ItemAlreadyClosed) as exc:
        validate_close_item(snapshot, 1, "invalidated")

    assert exc.value.code == "MAINTAIN-004"
    assert exc.value.context["item_id"] == 1


def test_close_item_missing_item_raises_001() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(MaintainItemNotFound) as exc:
        validate_close_item(snapshot, 99, "invalidated")

    assert exc.value.code == "MAINTAIN-001"
    assert exc.value.context["item_id"] == 99


def test_close_item_fanout_challenges_source() -> None:
    # 1 depends_on 2; human closes 2 invalidated -> 2 Closed, 1 Challenged.
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision")],
        [_link(10, 1, 2, "depends_on")],
    )

    changes = {
        change.item_id: change
        for change in validate_close_item(snapshot, 2, "invalidated")
    }

    assert set(changes) == {1, 2}
    assert changes[2].new_status == "Closed"
    assert changes[2].close_reason == "invalidated"
    assert changes[2].trigger_cause == "user_closed"
    assert changes[1].new_status == "Challenged"
    assert changes[1].trigger_cause == "dependency_closed"
    assert changes[1].link_id == 10


def test_close_item_expired_does_not_challenge_dependent() -> None:
    # expired is not a flagging reason (step-01 §4.2 rule 2) -> no fan-out.
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision")],
        [_link(10, 1, 2, "depends_on")],
    )

    changes = validate_close_item(snapshot, 2, "expired")

    assert [change.item_id for change in changes] == [2]
    assert changes[0].new_status == "Closed"


def test_close_item_dependent_already_challenged_not_rechallenged() -> None:
    snapshot = _snap(
        [_item(1, "Decision", status="Challenged"), _item(2, "Decision")],
        [_link(10, 1, 2, "depends_on")],
    )

    changes = validate_close_item(snapshot, 2, "invalidated")

    assert [change.item_id for change in changes] == [2]
    assert changes[0].new_status == "Closed"


def test_close_item_dependent_closed_not_rechallenged() -> None:
    snapshot = _snap(
        [_item(1, "Decision", status="Closed", close_reason="answered"), _item(2, "Decision")],
        [_link(10, 1, 2, "depends_on")],
    )

    changes = validate_close_item(snapshot, 2, "invalidated")

    assert [change.item_id for change in changes] == [2]


def test_close_item_ignores_rejected_depends_on_link() -> None:
    snapshot = _snap(
        [_item(1, "Decision"), _item(2, "Decision")],
        [_link(10, 1, 2, "depends_on", status="Rejected")],
    )

    changes = validate_close_item(snapshot, 2, "invalidated")

    assert [change.item_id for change in changes] == [2]


# --------------------------------------------------------------------------
# validate_set_status
# --------------------------------------------------------------------------


def test_set_status_to_bogus_raises_006() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(StatusTransitionInvalid) as exc:
        validate_set_status(snapshot, 1, "Bogus")

    assert exc.value.code == "MAINTAIN-006"


def test_set_status_to_closed_raises_006() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(StatusTransitionInvalid) as exc:
        validate_set_status(snapshot, 1, "Closed")

    assert exc.value.code == "MAINTAIN-006"


def test_set_status_on_closed_item_raises_006() -> None:
    snapshot = _snap([_item(1, status="Closed", close_reason="invalidated")])

    with pytest.raises(StatusTransitionInvalid) as exc:
        validate_set_status(snapshot, 1, "Active")

    assert exc.value.code == "MAINTAIN-006"


def test_set_status_noop_returns_empty() -> None:
    snapshot = _snap([_item(1, status="Active")])

    assert validate_set_status(snapshot, 1, "Active") == []


def test_set_status_missing_item_raises_001() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(MaintainItemNotFound) as exc:
        validate_set_status(snapshot, 99, "Active")

    assert exc.value.code == "MAINTAIN-001"


def test_set_status_challenge_active_item() -> None:
    snapshot = _snap([_item(1)])

    changes = validate_set_status(snapshot, 1, "Challenged")

    assert len(changes) == 1
    assert changes[0].old_status == "Active"
    assert changes[0].new_status == "Challenged"
    assert changes[0].trigger_cause == "user_set_status"
    assert changes[0].close_reason is None


# --------------------------------------------------------------------------
# validate_reverse_supersedes
# --------------------------------------------------------------------------


def test_reverse_missing_item_raises_001() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(MaintainItemNotFound) as exc:
        validate_reverse_supersedes(snapshot, 99, 1)

    assert exc.value.code == "MAINTAIN-001"
    assert exc.value.context["item_id"] == 99
    assert exc.value.context["link_id"] == 1


def test_reverse_active_item_raises_005() -> None:
    snapshot = _snap([_item(1)])

    with pytest.raises(ReversalPreconditionFailed) as exc:
        validate_reverse_supersedes(snapshot, 1, 10)

    assert exc.value.code == "MAINTAIN-005"


def test_reverse_wrong_reason_raises_005() -> None:
    snapshot = _snap([_item(1, status="Closed", close_reason="invalidated")])

    with pytest.raises(ReversalPreconditionFailed) as exc:
        validate_reverse_supersedes(snapshot, 1, 10)

    assert exc.value.code == "MAINTAIN-005"


def test_reverse_wrong_link_raises_005() -> None:
    # Item 1 Closed superseded by link 10; asking to reverse link 11 fails.
    snapshot = _snap(
        [_item(1, "Decision", status="Closed", close_reason="superseded"), _item(2, "Decision")],
        [_link(10, 2, 1, "supersedes")],
    )

    with pytest.raises(ReversalPreconditionFailed) as exc:
        validate_reverse_supersedes(snapshot, 1, 11)

    assert exc.value.code == "MAINTAIN-005"


def test_reverse_link_pointing_elsewhere_raises_005() -> None:
    # Link 10 is supersedes but targets item 2, not the item being reversed.
    snapshot = _snap(
        [_item(1, "Decision", status="Closed", close_reason="superseded"), _item(2, "Decision")],
        [_link(10, 3, 2, "supersedes")],
    )

    with pytest.raises(ReversalPreconditionFailed) as exc:
        validate_reverse_supersedes(snapshot, 1, 10)

    assert exc.value.code == "MAINTAIN-005"


def test_reverse_happy_path_returns_active() -> None:
    snapshot = _snap(
        [_item(2, "Decision"), _item(1, "Decision", status="Closed", close_reason="superseded")],
        [_link(10, 2, 1, "supersedes")],
    )

    changes = validate_reverse_supersedes(snapshot, 1, 10)

    assert len(changes) == 1
    change = changes[0]
    assert change.item_id == 1
    assert change.old_status == "Closed"
    assert change.new_status == "Active"
    assert change.close_reason is None
    assert change.old_close_reason == "superseded"
    assert change.trigger_cause == "reversal"
    assert change.link_id == 10


# --------------------------------------------------------------------------
# Ladder regression: the human commands move an item DOWN.
# --------------------------------------------------------------------------


def test_ladder_set_status_challenged_to_active_not_dropped() -> None:
    snapshot = _snap([_item(1, status="Challenged")])

    changes = validate_set_status(snapshot, 1, "Active")

    assert len(changes) == 1
    assert changes[0].old_status == "Challenged"
    assert changes[0].new_status == "Active"


def test_ladder_set_status_challenged_manual_shield_not_dropped() -> None:
    snapshot = _snap([_item(1, status="Challenged", status_origin="manual")])

    changes = validate_set_status(snapshot, 1, "Active")

    assert len(changes) == 1
    assert changes[0].old_status == "Challenged"
    assert changes[0].new_status == "Active"


def test_ladder_reverse_closed_to_active_not_dropped() -> None:
    snapshot = _snap(
        [_item(1, "Decision", status="Closed", close_reason="superseded"), _item(2, "Decision")],
        [_link(10, 2, 1, "supersedes")],
    )

    changes = validate_reverse_supersedes(snapshot, 1, 10)

    assert changes[0].old_status == "Closed"
    assert changes[0].new_status == "Active"


def test_ladder_close_item_challenged_to_closed_not_dropped() -> None:
    snapshot = _snap([_item(1, status="Challenged")])

    changes = validate_close_item(snapshot, 1, "invalidated")

    assert len(changes) == 1
    assert changes[0].old_status == "Challenged"
    assert changes[0].new_status == "Closed"

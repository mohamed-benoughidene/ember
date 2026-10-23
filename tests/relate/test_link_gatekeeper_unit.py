"""Unit tests for relate phase 4 (link gatekeeper), no DB and no model.

Each test drives `validate_add_link` through a `FakeLinkLookup` and reads the
returned `RejectedLink.code` (or checks the `ValidatedLink` shape on the pass
path). Nothing here imports a private helper: the observable contract is the
gatekeeper result plus the two rows it builds (Constitution T6).
"""

from __future__ import annotations

from ember.relate.link_gatekeeper import (
    LinkDraft,
    RejectedLink,
    ValidatedLink,
    validate_add_link,
)
from ember.relate.rows import Link, NewItem
from tests.fakes import FIXED_TIME
from tests.relate.fakes import FakeLinkLookup


def _item(item_id: int, item_type: str) -> NewItem:
    return NewItem(id=item_id, type=item_type, statement="s", created_at=FIXED_TIME)


def _draft(source=1, target=2, link_type="depends_on", rationale=None):
    return LinkDraft(
        source_item_id=source,
        target_item_id=target,
        link_type=link_type,
        rationale=rationale,
    )


def _validate(draft, lookup):
    return validate_add_link(draft, lookup, clock=lambda: FIXED_TIME)


def test_rule1_source_missing():
    lookup = FakeLinkLookup(items=[_item(2, "Decision")])

    result = _validate(_draft(source=1, target=2), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-026"


def test_rule2_target_missing():
    lookup = FakeLinkLookup(items=[_item(1, "Decision")])

    result = _validate(_draft(source=1, target=2), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-027"


def test_rule3_self_link():
    lookup = FakeLinkLookup(items=[_item(1, "Decision")])

    result = _validate(_draft(source=1, target=1), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-010"


def test_rule4_bad_link_type():
    lookup = FakeLinkLookup(items=[_item(1, "Decision"), _item(2, "Decision")])

    result = _validate(_draft(link_type="invalid"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-005"


def test_rule5_pair_incompatible():
    lookup = FakeLinkLookup(items=[_item(1, "Decision"), _item(2, "Decision")])

    result = _validate(_draft(link_type="answers"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-006"


def test_rule6_supersedes_closed_target():
    lookup = FakeLinkLookup(
        items=[_item(1, "Decision"), _item(2, "Decision")],
        statuses={2: "Closed"},
    )

    result = _validate(_draft(link_type="supersedes"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-007"


def test_rule6_supersedes_active_target_passes():
    lookup = FakeLinkLookup(
        items=[_item(1, "Decision"), _item(2, "Decision")],
        statuses={2: "Active"},
    )

    result = _validate(_draft(link_type="supersedes"), lookup)

    assert isinstance(result, ValidatedLink)


def test_rule7_premise_violated():
    lookup = FakeLinkLookup(items=[_item(1, "Assumption"), _item(2, "Finding")])

    result = _validate(_draft(link_type="supports"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-008"


def test_rule7_decision_supporting_finding_incompatible():
    lookup = FakeLinkLookup(items=[_item(1, "Decision"), _item(2, "Finding")])

    result = _validate(_draft(link_type="supports"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-006"


def test_rule8_cycle_direction_a():
    link = Link(
        id=100,
        source_item_id=1,
        target_item_id=2,
        link_type="supersedes",
        status="Confirmed",
        created_at=FIXED_TIME,
    )
    lookup = FakeLinkLookup(
        items=[_item(1, "Decision"), _item(2, "Decision")],
        links=[link],
        statuses={1: "Active", 2: "Active"},
    )

    result = _validate(_draft(source=1, target=2, link_type="supersedes"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-028"


def test_rule8_cycle_direction_b():
    link = Link(
        id=100,
        source_item_id=1,
        target_item_id=2,
        link_type="supersedes",
        status="Confirmed",
        created_at=FIXED_TIME,
    )
    lookup = FakeLinkLookup(
        items=[_item(1, "Decision"), _item(2, "Decision")],
        links=[link],
        statuses={1: "Active", 2: "Active"},
    )

    result = _validate(_draft(source=2, target=1, link_type="supersedes"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-028"


def test_rule9_duplicate():
    link = Link(
        id=50,
        source_item_id=1,
        target_item_id=2,
        link_type="depends_on",
        status="Confirmed",
        created_at=FIXED_TIME,
    )
    lookup = FakeLinkLookup(
        items=[_item(1, "Decision"), _item(2, "Decision")],
        links=[link],
    )

    result = _validate(_draft(source=1, target=2, link_type="depends_on"), lookup)

    assert isinstance(result, RejectedLink)
    assert result.code == "RELATE-009"


def test_pass_shape():
    lookup = FakeLinkLookup(items=[_item(1, "Decision"), _item(2, "Decision")])

    result = _validate(_draft(source=1, target=2, link_type="depends_on", rationale="why"), lookup)

    assert isinstance(result, ValidatedLink)
    assert result.link_row.status == "Confirmed"
    assert result.link_row.id is None
    assert result.link_row.created_at == FIXED_TIME
    assert result.link_row.link_type == "depends_on"
    assert result.change_log_row.field_changed == "link_confirmed"
    assert result.change_log_row.trigger_cause == "user_confirmed"
    assert result.change_log_row.new_value == "depends_on:2"
    assert result.change_log_row.link_id is None
    assert result.change_log_row.item_id == 1
    assert result.rationale == "why"

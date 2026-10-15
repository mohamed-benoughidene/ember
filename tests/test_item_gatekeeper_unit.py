"""Unit tests for phase 3 core (gatekeeper checks, no DB)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ember.capture.errors import ItemSourceMissing
from ember.capture.item_gatekeeper import (
    NEAR_DUP_THRESHOLD,
    STATUS_ACTIVE,
    ExistingItem,
    GatekeeperRun,
    ProposalDraft,
    RejectedProposal,
    ValidatedItem,
    is_allowed_type,
    load_source_text,
    validate_add_item,
    validate_proposals,
)
from ember.capture.item_proposal import ItemProposal, ItemType

RAW_TEXT = "The team decided to use SQLite for local storage."
SOURCE_ID = 7
FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _run(
    *,
    existing: list[ExistingItem] | None = None,
    ids: tuple[int, ...] = (10, 11, 12),
    source_text: str = RAW_TEXT,
) -> GatekeeperRun:
    counter = iter(ids)
    return GatekeeperRun(
        source_id=SOURCE_ID,
        source_text=source_text,
        existing=existing or [],
        next_id=lambda: next(counter),
        clock=lambda: FIXED_TIME,
    )


def _draft(**overrides) -> ProposalDraft:
    base = ProposalDraft(
        type="Decision",
        statement="Use SQLite for local storage",
        source_quote="use SQLite",
        confidence=0.9,
    )
    return replace(base, **overrides)


def _proposal(**overrides) -> ItemProposal:
    base = ItemProposal(
        type=ItemType.DECISION,
        statement="Use SQLite for local storage",
        source_quote="use SQLite",
        confidence=0.9,
    )
    return base.model_copy(update=overrides)


class _FakeSources:
    def __init__(self, rows: dict[int, str]) -> None:
        self.rows = rows

    def full_text_for(self, source_id: int) -> str | None:
        return self.rows.get(source_id)


# --- the 4 checks ---------------------------------------------------------


def test_all_checks_pass_generates_id_time_and_active() -> None:
    outcome = validate_add_item(_draft(), _run())

    assert isinstance(outcome, ValidatedItem)
    assert outcome.id == 10
    assert outcome.created_at == FIXED_TIME
    assert outcome.status == STATUS_ACTIVE
    assert outcome.source_id == SOURCE_ID
    assert outcome.near_dup_warning is None


def test_bad_type_is_dropped() -> None:
    outcome = validate_add_item(_draft(type="Risk"), _run())

    assert isinstance(outcome, RejectedProposal)
    assert outcome.rule == "type"


def test_empty_statement_is_dropped() -> None:
    outcome = validate_add_item(_draft(statement="   "), _run())

    assert isinstance(outcome, RejectedProposal)
    assert outcome.rule == "statement"


def test_quote_not_in_source_is_dropped() -> None:
    outcome = validate_add_item(_draft(source_quote="Postgres"), _run())

    assert isinstance(outcome, RejectedProposal)
    assert outcome.rule == "quote"


def test_near_dup_attaches_warning_but_still_validates() -> None:
    existing = [ExistingItem(3, "Use SQLite for local storage")]

    outcome = validate_add_item(_draft(), _run(existing=existing))

    assert isinstance(outcome, ValidatedItem)
    assert outcome.near_dup_warning is not None
    assert outcome.near_dup_warning.matching_item_id == 3
    assert outcome.near_dup_warning.similarity == pytest.approx(1.0)


def test_unrelated_existing_item_makes_no_warning() -> None:
    existing = [ExistingItem(3, "Ship the onboarding screen")]

    outcome = validate_add_item(_draft(), _run(existing=existing))

    assert outcome.near_dup_warning is None


def test_warning_picks_the_closest_item() -> None:
    existing = [
        ExistingItem(1, "Use SQLite for local storage"),
        ExistingItem(2, "Use SQLite for local storag"),
    ]

    outcome = validate_add_item(_draft(), _run(existing=existing))

    assert outcome.near_dup_warning is not None
    assert outcome.near_dup_warning.matching_item_id == 1


# --- batch loop -----------------------------------------------------------


def test_validate_proposals_splits_good_and_bad() -> None:
    good = _proposal()
    bad = _proposal(source_quote="Postgres")

    result = validate_proposals([good, bad], _run())

    assert [item.statement for item in result.validated] == [
        "Use SQLite for local storage"
    ]
    assert [reject.rule for reject in result.rejected] == ["quote"]


def test_validate_proposals_maps_proposal_fields_onto_the_item() -> None:
    proposal = _proposal(
        type=ItemType.ASSUMPTION,
        statement="Team ships weekly",
        confidence=0.4,
    )

    result = validate_proposals([proposal], _run())

    item = result.validated[0]
    assert item.type == "Assumption"
    assert item.statement == "Team ships weekly"
    assert item.confidence == 0.4


def test_validate_proposals_gives_each_item_its_own_id() -> None:
    result = validate_proposals([_proposal(), _proposal()], _run(ids=(4, 5)))

    assert [item.id for item in result.validated] == [4, 5]


# --- small helpers --------------------------------------------------------


def test_is_allowed_type_accepts_the_four_and_rejects_junk() -> None:
    for item_type in ItemType:
        assert is_allowed_type(item_type.value)
    assert not is_allowed_type("Risk")


def test_threshold_is_a_fraction() -> None:
    assert 0.0 < NEAR_DUP_THRESHOLD < 1.0


def test_load_source_text_returns_the_stored_text() -> None:
    assert load_source_text(_FakeSources({SOURCE_ID: "body"}), SOURCE_ID) == "body"


def test_load_source_text_raises_when_missing() -> None:
    with pytest.raises(ItemSourceMissing) as excinfo:
        load_source_text(_FakeSources({}), SOURCE_ID)

    assert excinfo.value.code == "CAPTURE-012"

"""Unit tests for relate phase 4 core (confirm loop + atomic link write)."""

from __future__ import annotations

from ember.relate.confirm_write import (
    PROMPT,
    Choice,
    ConfirmResult,
    confirm_links,
    format_link_block,
    parse_choice,
)
from ember.relate.errors import UserAbort as RelateUserAbort
from ember.relate.link_gatekeeper import ValidatedLink
from ember.relate.rows import ChangeLogEntry, Link
from tests.fakes import FIXED_TIME, FakeConfirm
from tests.relate.fakes import FakeLinkStore


def _validated(
    target: int = 2, link_type: str = "depends_on", rationale: str | None = "why"
):
    link = Link(
        id=None,
        source_item_id=1,
        target_item_id=target,
        link_type=link_type,
        status="Confirmed",
        created_at=FIXED_TIME,
    )
    log = ChangeLogEntry(
        id=None,
        item_id=1,
        link_id=None,
        field_changed="link_confirmed",
        old_value=None,
        new_value=f"{link_type}:{target}",
        timestamp=FIXED_TIME,
        trigger_cause="user_confirmed",
    )
    return ValidatedLink(link_row=link, change_log_row=log, rationale=rationale)


# --- answer parsing -------------------------------------------------------


def test_parse_choice() -> None:
    assert parse_choice("y") is Choice.YES
    assert parse_choice("yes") is Choice.YES
    assert parse_choice("Y") is Choice.YES
    assert parse_choice(" n ") is Choice.NO
    assert parse_choice("no") is Choice.NO
    assert parse_choice("No") is Choice.NO
    assert parse_choice(" s ") is Choice.SKIP
    assert parse_choice("skip") is Choice.SKIP
    assert parse_choice("q") is Choice.QUIT
    assert parse_choice("QUIT") is Choice.QUIT
    assert parse_choice("x") is None


# --- the write paths ------------------------------------------------------


def test_yes_writes_and_prints_block() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm(["y"])

    result = confirm_links([_validated()], store=store, confirm=confirm)

    assert result == ConfirmResult([5], 0, 0, False)
    assert store.rows[0][0].status == "Confirmed"
    printed = "\n".join(confirm.written)
    assert "- link_id: 5" in printed
    assert '  status: "Confirmed"' in printed


def test_no_writes_rejected_variant() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm(["n"])

    result = confirm_links([_validated()], store=store, confirm=confirm)

    assert result.rejected == 1
    assert result.accepted == []
    assert result.skipped == 0
    assert store.rows[0][0].status == "Rejected"
    assert store.rows[0][1].field_changed == "link_rejected"
    assert store.rows[0][1].trigger_cause == "rejected"
    assert not any("- link_id:" in line for line in confirm.written)


def test_skip_no_write() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm(["s"])

    result = confirm_links([_validated()], store=store, confirm=confirm)

    assert result.skipped == 1
    assert store.rows == []


def test_quit_aborts() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm(["q"])

    result = confirm_links([_validated()], store=store, confirm=confirm)

    assert result.aborted is True
    assert store.rows == []


def test_unknown_input_reprompts() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm(["x", "y"])

    result = confirm_links([_validated()], store=store, confirm=confirm)

    assert len(result.accepted) == 1
    assert len(confirm.prompts) == 2


def test_preview_never_contains_link_id() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm(["y"])

    confirm_links([_validated()], store=store, confirm=confirm)

    assert "link_id:" not in confirm.written[0]
    assert any("link_id:" in line for line in confirm.written[1:])


def test_end_of_input_aborts() -> None:
    store = FakeLinkStore(start_id=5)
    confirm = FakeConfirm([], abort_error=RelateUserAbort)

    result = confirm_links([_validated()], store=store, confirm=confirm)

    assert result.aborted is True


# --- block formatting -----------------------------------------------------


def test_block_format() -> None:
    assert "  rationale: null" in format_link_block(_validated(rationale=None))
    assert '  rationale: "why"' in format_link_block(_validated(rationale="why"))

"""Unit tests for phase 4 core (confirm loop, fake user + fake commit)."""

from __future__ import annotations

from ember.capture.confirm_write import (
    PROMPT,
    Choice,
    format_block,
    parse_choice,
    run_confirm_loop,
)
from ember.capture.item_gatekeeper import (
    NearDupWarning,
    ProposalDraft,
    RejectedProposal,
)
from tests.fakes import FakeConfirm, FakeItemCommit, make_item


def _never_called(draft: ProposalDraft):
    raise AssertionError("revalidate should not run")


def run(items, answers, revalidate=_never_called):
    confirm = FakeConfirm(answers)
    commit = FakeItemCommit()
    result = run_confirm_loop(
        items, confirm=confirm, commit=commit, revalidate=revalidate
    )
    return result, confirm, commit


# --- answer parsing -------------------------------------------------------


def test_parse_choice_maps_short_and_long_forms() -> None:
    assert parse_choice("y") is Choice.YES
    assert parse_choice("YES") is Choice.YES
    assert parse_choice(" n ") is Choice.NO
    assert parse_choice("Edit") is Choice.EDIT
    assert parse_choice("q") is Choice.QUIT
    assert parse_choice("quit") is Choice.QUIT


def test_parse_choice_rejects_unknown_input() -> None:
    assert parse_choice("") is None
    assert parse_choice("maybe") is None


# --- block formatting -----------------------------------------------------


def test_format_block_names_every_field() -> None:
    text = format_block(make_item())

    assert "- id: 1" in text
    assert 'type: "Decision"' in text
    assert 'statement: "Use SQLite"' in text
    assert 'source_quote: "use SQLite"' in text
    assert "confidence: 0.9" in text
    assert "near_dup_warning: null" in text


def test_format_block_shows_the_warning_flow_map() -> None:
    warning = NearDupWarning(matching_item_id=5, similarity=0.912)

    text = format_block(make_item(warning=warning))

    assert "near_dup_warning: {matching_item_id: 5, similarity: 0.91}" in text


# --- the write paths ------------------------------------------------------


def test_yes_writes_item_then_change_log() -> None:
    result, _, commit = run([make_item()], ["y"])

    assert result.accepted_ids == [1]
    assert result.rejected_count == 0
    assert result.aborted is False
    assert commit.items == [(make_item(), None)]
    assert commit.created == [make_item()]
    assert commit.rejected == []


def test_yes_on_assumption_sets_validated_false() -> None:
    item = make_item(item_type="Assumption")

    _, _, commit = run([item], ["y"])

    assert commit.items == [(item, False)]


def test_no_logs_a_rejection_without_an_item_row() -> None:
    result, _, commit = run([make_item()], ["n"])

    assert result.accepted_ids == []
    assert result.rejected_count == 1
    assert commit.items == []
    assert commit.created == []
    assert commit.rejected == [make_item()]


def test_mixed_answers_are_counted_separately() -> None:
    items = [make_item(1), make_item(2), make_item(3)]

    result, _, commit = run(items, ["n", "y", "n"])

    assert result.accepted_ids == [2]
    assert result.rejected_count == 2
    assert result.aborted is False
    assert [item.id for item, _ in commit.items] == [2]


# --- abort paths ----------------------------------------------------------


def test_quit_stops_the_loop_and_reports_abort() -> None:
    items = [make_item(1), make_item(2), make_item(3)]

    result, _, commit = run(items, ["y", "q"])

    assert result.aborted is True
    assert result.accepted_ids == [1]
    assert [item.id for item, _ in commit.items] == [1]
    assert commit.rejected == []


def test_end_of_input_stops_the_loop_and_reports_abort() -> None:
    result, _, commit = run([make_item(1), make_item(2)], [])

    assert result.aborted is True
    assert result.accepted_ids == []
    assert commit.items == []


def test_unknown_answer_re_prompts() -> None:
    result, confirm, _ = run([make_item()], ["maybe", "x", "y"])

    assert result.accepted_ids == [1]
    assert confirm.prompts.count(PROMPT) == 3


# --- near-dup warning -----------------------------------------------------


def test_near_dup_warning_is_written_and_counted() -> None:
    warning = NearDupWarning(matching_item_id=5, similarity=0.95)

    result, confirm, _ = run([make_item(warning=warning)], ["y"])

    assert result.warning_count == 1
    assert any("near-duplicate of item 5" in line for line in confirm.written)


# --- edit path ------------------------------------------------------------


def test_edit_re_validates_and_accepts() -> None:
    seen: list[ProposalDraft] = []

    def revalidate(draft: ProposalDraft):
        seen.append(draft)
        return make_item(item_type=draft.type, statement=draft.statement)

    result, _, commit = run(
        [make_item(item_type="Finding")],
        ["e", "Decision", "Use SQLite", "", "y"],
        revalidate=revalidate,
    )

    assert seen == [
        ProposalDraft(
            type="Decision",
            statement="Use SQLite",
            source_quote="use SQLite",
            confidence=0.9,
        )
    ]
    assert result.accepted_ids == [1]
    assert commit.created[0].type == "Decision"


def test_edit_re_prompts_until_the_type_is_allowed() -> None:
    def revalidate(draft: ProposalDraft):
        return make_item(item_type=draft.type, statement=draft.statement)

    _, confirm, commit = run(
        [make_item(item_type="Finding")],
        ["e", "Risk", "Decision", "New statement", "", "y"],
        revalidate=revalidate,
    )

    assert "invalid type" in confirm.written
    assert sum("new type?" in prompt for prompt in confirm.prompts) == 2
    assert commit.created[0].statement == "New statement"


def test_edit_dropped_by_the_gatekeeper_writes_nothing() -> None:
    def revalidate(draft: ProposalDraft):
        return RejectedProposal(rule="quote")

    result, confirm, commit = run(
        [make_item(1)], ["e", "Decision", "x", ""], revalidate=revalidate
    )

    assert result.accepted_ids == []
    assert commit.items == []
    assert commit.created == []
    assert any("dropped proposal: quote" in line for line in confirm.written)


# --- the metadata line and the metadata edit prompt (ticket 11, step 05a) ---


def test_format_block_shows_the_metadata_line() -> None:
    labeled = format_block(make_item(metadata="auth-network")).splitlines()
    plain = format_block(make_item()).splitlines()

    assert '  metadata: "auth-network"' in labeled
    assert "  metadata: null" in plain
    # The line sits between confidence and near_dup_warning.
    assert labeled.index("  confidence: 0.9") + 1 == labeled.index(
        '  metadata: "auth-network"'
    )
    assert labeled.index('  metadata: "auth-network"') + 1 == labeled.index(
        "  near_dup_warning: null"
    )


def test_edit_re_asks_metadata_with_the_ai_default() -> None:
    def revalidate(draft: ProposalDraft):
        return make_item(metadata=draft.metadata)

    result, confirm, commit = run(
        [make_item(metadata="auth-network")],
        ["e", "", "", "", "y"],
        revalidate=revalidate,
    )

    assert "new metadata? (default auth-network)" in confirm.prompts
    assert result.accepted_ids == [1]
    assert commit.created[0].metadata == "auth-network"


def test_edit_dash_clears_metadata_to_none() -> None:
    def revalidate(draft: ProposalDraft):
        return make_item(metadata=draft.metadata)

    _, confirm, commit = run(
        [make_item(metadata="auth-network")],
        ["e", "", "", "-", "y"],
        revalidate=revalidate,
    )

    assert "new metadata? (default auth-network)" in confirm.prompts
    assert commit.created[0].metadata is None
    assert any("  metadata: null" in line for line in confirm.written)

"""Unit tests for phase 2 core logic (fake AI port and fake item reader)."""

from __future__ import annotations

import json

import pytest

from ember.capture.errors import (
    AiCallError,
    AiSchemaError,
    ContextModeInvalid,
)
from ember.capture.item_proposal import (
    CONTEXT_WINDOW,
    SYSTEM_PROMPT,
    ContextItem,
    ContextMode,
    ItemProposal,
    ItemType,
    build_context,
    parse_proposals,
    propose_items,
    read_context_mode,
)
from tests.fakes import FakeItemContext, FakeItemProposer

RAW_TEXT = "The team decided to use SQLite."


def _entry(**overrides) -> dict:
    entry = {
        "type": "Decision",
        "statement": "Use SQLite",
        "source_quote": "SQLite",
        "confidence": 0.9,
    }
    entry.update(overrides)
    return entry


def _response(*entries: dict) -> str:
    return json.dumps(list(entries))


def _good_proposal() -> ItemProposal:
    return ItemProposal(
        type=ItemType.DECISION,
        statement="Use SQLite",
        source_quote="SQLite",
        confidence=0.9,
    )


def _context_items(count: int) -> list[ContextItem]:
    return [
        ContextItem(id=index, type=ItemType.FINDING, statement=f"item {index}")
        for index in range(count)
    ]


# --- context mode (plan step 1) -------------------------------------------


def test_mode_defaults_to_b_when_env_is_empty() -> None:
    assert read_context_mode({}) is ContextMode.B


def test_mode_reads_a_case_insensitively() -> None:
    env = {"EMBER_CAPTURE_CONTEXT_MODE": "a"}
    assert read_context_mode(env) is ContextMode.A


def test_bad_mode_raises_context_mode_invalid() -> None:
    with pytest.raises(ContextModeInvalid) as excinfo:
        read_context_mode({"EMBER_CAPTURE_CONTEXT_MODE": "C"})

    assert excinfo.value.code == "CAPTURE-010"


# --- context building (plan step 2) ---------------------------------------


def test_mode_a_reads_no_context() -> None:
    reader = FakeItemContext(_context_items(60))

    context = build_context(reader, ContextMode.A)

    assert context == []
    assert reader.limits == []


def test_mode_b_reads_the_last_50_items() -> None:
    reader = FakeItemContext(_context_items(60))

    context = build_context(reader, ContextMode.B)

    assert reader.limits == [CONTEXT_WINDOW]
    assert CONTEXT_WINDOW == 50
    assert len(context) == CONTEXT_WINDOW


def test_mode_b_context_is_passed_to_the_ai() -> None:
    reader = FakeItemContext(_context_items(60))
    context = build_context(reader, ContextMode.B)
    proposer = FakeItemProposer([[_good_proposal()]])

    propose_items(proposer, raw_text=RAW_TEXT, context=context)

    _, sent_context = proposer.calls[0]
    assert len(sent_context) == CONTEXT_WINDOW
    assert sent_context == context


# --- system prompt (plan step 3) ------------------------------------------


def test_system_prompt_names_all_four_types() -> None:
    for item_type in ItemType:
        assert item_type.value in SYSTEM_PROMPT


def test_system_prompt_asks_for_quote_and_confidence() -> None:
    assert "source_quote" in SYSTEM_PROMPT
    assert "confidence" in SYSTEM_PROMPT


# --- retry policy (plan section 5) ----------------------------------------


def test_first_call_fail_makes_a_second_call() -> None:
    proposer = FakeItemProposer([AiCallError("ai call fail"), [_good_proposal()]])

    result = propose_items(proposer, raw_text=RAW_TEXT, context=[])

    assert len(proposer.calls) == 2
    assert result == [_good_proposal()]


def test_second_call_fail_raises() -> None:
    proposer = FakeItemProposer(
        [AiCallError("ai call fail"), AiCallError("ai call fail again")]
    )

    with pytest.raises(AiCallError):
        propose_items(proposer, raw_text=RAW_TEXT, context=[])

    assert len(proposer.calls) == 2


def test_unreadable_response_also_retries_once() -> None:
    proposer = FakeItemProposer(
        [AiSchemaError("ai response not json"), [_good_proposal()]]
    )

    result = propose_items(proposer, raw_text=RAW_TEXT, context=[])

    assert len(proposer.calls) == 2
    assert result == [_good_proposal()]


def test_raw_text_is_handed_to_the_ai() -> None:
    proposer = FakeItemProposer([[_good_proposal()]])

    propose_items(proposer, raw_text=RAW_TEXT, context=[])

    assert proposer.calls[0][0] == RAW_TEXT


# --- validation (plan steps 5 and 6) --------------------------------------


def test_valid_entry_is_kept_with_typed_fields() -> None:
    batch = parse_proposals(_response(_entry()), RAW_TEXT)

    assert len(batch.dropped) == 0
    assert len(batch.proposals) == 1
    proposal = batch.proposals[0]
    assert isinstance(proposal.type, ItemType)
    assert proposal.type is ItemType.DECISION
    assert proposal.statement == "Use SQLite"
    assert proposal.source_quote == "SQLite"
    assert proposal.confidence == 0.9


def test_bad_type_is_dropped() -> None:
    batch = parse_proposals(_response(_entry(type="Risk")), RAW_TEXT)

    assert batch.proposals == []
    assert [drop.rule for drop in batch.dropped] == ["type"]


def test_non_substring_quote_is_dropped() -> None:
    batch = parse_proposals(_response(_entry(source_quote="Postgres")), RAW_TEXT)

    assert batch.proposals == []
    assert [drop.rule for drop in batch.dropped] == ["quote"]


def test_out_of_range_confidence_is_dropped() -> None:
    batch = parse_proposals(_response(_entry(confidence=1.4)), RAW_TEXT)

    assert batch.proposals == []
    assert [drop.rule for drop in batch.dropped] == ["confidence"]


def test_empty_statement_is_dropped() -> None:
    batch = parse_proposals(_response(_entry(statement="")), RAW_TEXT)

    assert batch.proposals == []
    assert [drop.rule for drop in batch.dropped] == ["statement"]


def test_good_entries_survive_next_to_bad_ones() -> None:
    batch = parse_proposals(
        _response(_entry(type="Risk"), _entry(), _entry(confidence=-0.1)), RAW_TEXT
    )

    assert len(batch.proposals) == 1
    assert [drop.rule for drop in batch.dropped] == ["type", "confidence"]


def test_all_invalid_returns_empty_without_raising() -> None:
    batch = parse_proposals(
        _response(_entry(type="Risk"), _entry(source_quote="nope")), RAW_TEXT
    )

    assert batch.proposals == []
    assert len(batch.dropped) == 2


def test_whole_response_that_is_not_json_raises_schema_error() -> None:
    with pytest.raises(AiSchemaError) as excinfo:
        parse_proposals("the model said hello", RAW_TEXT)

    assert excinfo.value.code == "CAPTURE-009"


def test_whole_response_that_is_not_a_list_raises_schema_error() -> None:
    with pytest.raises(AiSchemaError):
        parse_proposals(json.dumps({"proposals": []}), RAW_TEXT)


def test_ai_call_error_code_is_stable() -> None:
    assert AiCallError("ai call fail").code == "CAPTURE-008"

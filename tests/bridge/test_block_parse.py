"""`ember/bridge/block_parse.py` round trips against the REAL formatters (T1).

Every block here is built by the engine's own formatter exactly as the/
confirm loop writes it, so these tests fail first if a formatter ever
changes shape. Covered per the step file: a non-null near-duplicate
warning, values containing `: `, emoji, very long text, the decline shape,
and the `parsed=False` fallback on a deliberately broken block (raw text
always kept).
"""

from __future__ import annotations

import dataclasses

from ember.bridge.block_parse import (
    parse_capture_block,
    parse_close_proposal_block,
    parse_link_block,
    parse_link_preview,
)
from ember.capture.confirm_write import format_block
from ember.capture.item_gatekeeper import NearDupWarning, ValidatedItem
from ember.maintain.close_proposer import (
    CloseProposal,
    StaleCandidate,
    format_proposal_block,
)
from ember.relate.confirm_write import _preview_line, format_link_block
from ember.relate.link_gatekeeper import ValidatedLink
from ember.relate.rows import ChangeLogEntry, Link

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _validated_item(**overrides: object) -> ValidatedItem:
    item = ValidatedItem(
        id=3,
        type="Decision",
        statement="Use SQLite",
        source_quote="use SQLite",
        confidence=0.9,
        source_id=1,
        created_at=FIXED_TIME,
        status="Active",
        near_dup_warning=None,
        metadata="auth-network",
    )
    return dataclasses.replace(item, **overrides)  # type: ignore[arg-type]


def _link(link_id: int = 3, rationale: str | None = None) -> ValidatedLink:
    return ValidatedLink(
        link_row=Link(
            id=link_id,
            source_item_id=1,
            target_item_id=4,
            link_type="depends_on",
            status="Confirmed",
            created_at=FIXED_TIME,
        ),
        change_log_row=ChangeLogEntry(
            item_id=1,
            link_id=link_id,
            field_changed="link_confirmed",
            old_value=None,
            new_value="depends_on:4",
            timestamp=FIXED_TIME,
            trigger_cause="user_confirmed",
        ),
        rationale=rationale,
    )


# --- capture block -----------------------------------------------------------


def test_capture_block_round_trip_plain() -> None:
    parsed = parse_capture_block(format_block(_validated_item()))

    assert parsed.parsed is True
    assert parsed.fields == {
        "id": 3,
        "type": "Decision",
        "statement": "Use SQLite",
        "source_quote": "use SQLite",
        "confidence": 0.9,
        "metadata": "auth-network",
        "near_dup_warning": None,
    }
    assert parsed.text == format_block(_validated_item())


def test_capture_block_round_trip_with_near_dup_warning() -> None:
    warning = NearDupWarning(matching_item_id=3, similarity=0.91)
    parsed = parse_capture_block(format_block(_validated_item(near_dup_warning=warning)))

    assert parsed.parsed is True
    assert parsed.fields["near_dup_warning"] == {
        "matching_item_id": 3,
        "similarity": 0.91,
    }


def test_capture_block_round_trip_colon_in_quotes_and_emoji_and_long_text() -> None:
    long_statement = ("note: emoji 🚀 here, colon inside quotes; " * 40).strip()
    parsed = parse_capture_block(
        format_block(
            _validated_item(
                statement=long_statement,
                source_quote="quoted: with colon and \"double\" quotes",
                metadata=None,
            )
        )
    )

    assert parsed.parsed is True
    assert parsed.fields["statement"] == long_statement
    assert parsed.fields["source_quote"] == 'quoted: with colon and "double" quotes'
    assert parsed.fields["metadata"] is None


def test_capture_block_broken_returns_unparsed_with_raw_text() -> None:
    broken = '- id: 1\n  type: "Decision"\n  statement is missing here\n'

    parsed = parse_capture_block(broken)

    assert parsed.parsed is False
    assert parsed.fields == {}
    assert parsed.text == broken


def test_capture_block_fails_on_drifted_key_set() -> None:
    drifted = format_block(_validated_item()).replace("\n  confidence: 0.9", "")

    assert parse_capture_block(drifted).parsed is False


# --- relate preview ----------------------------------------------------------


def test_link_preview_round_trip_with_rationale() -> None:
    preview = _preview_line(2, 3, _link(rationale="because item 4 extends it"))

    parsed = parse_link_preview(preview)

    assert parsed.parsed is True
    assert parsed.fields == {
        "index": 2,
        "total": 3,
        "source_item_id": 1,
        "target_item_id": 4,
        "link_type": "depends_on",
        "rationale": "because item 4 extends it",
    }
    assert parsed.text == preview


def test_link_preview_round_trip_dash_means_no_rationale() -> None:
    parsed = parse_link_preview(_preview_line(1, 3, _link(rationale=None)))

    assert parsed.parsed is True
    assert parsed.fields["rationale"] is None


def test_link_preview_emoji_and_long_rationale() -> None:
    rationale = "🔗 " + "very: long rationale " * 200
    parsed = parse_link_preview(_preview_line(1, 3, _link(rationale=rationale)))

    assert parsed.parsed is True
    assert parsed.fields["rationale"] == rationale


def test_link_preview_broken_returns_unparsed_with_raw_text() -> None:
    broken = "Proposal 1/3: item 1 -> [missing]\n  rationale: -"

    parsed = parse_link_preview(broken)

    assert parsed.parsed is False
    assert parsed.fields == {}
    assert parsed.text == broken


# --- relate link block -------------------------------------------------------


def test_link_block_round_trip_plain() -> None:
    parsed = parse_link_block(format_link_block(_link()))

    assert parsed.parsed is True
    assert parsed.fields == {
        "link_id": 3,
        "source_item_id": 1,
        "target_item_id": 4,
        "link_type": "depends_on",
        "status": "Confirmed",
        "rationale": None,
    }
    assert parsed.text == format_link_block(_link())


def test_link_block_round_trip_with_value_rationale() -> None:
    parsed = parse_link_block(format_link_block(_link(rationale="why: not")))

    assert parsed.parsed is True
    assert parsed.fields["rationale"] == "why: not"


def test_link_block_emoji_link_type_round_trip() -> None:
    parsed = parse_link_block(format_link_block(_link(rationale="🔗 支持说明")))

    assert parsed.parsed is True
    assert parsed.fields["rationale"] == "🔗 支持说明"


def test_link_block_broken_returns_unparsed_with_raw_text() -> None:
    broken = '- link_id: 3\n  source_item_id: 1\n  target: gone\n  status: "Confirmed"\n'

    parsed = parse_link_block(broken)

    assert parsed.parsed is False
    assert parsed.text == broken


# --- maintain proposal block -------------------------------------------------


def _candidate(statement: str = "should we cache tokens?") -> StaleCandidate:
    return StaleCandidate(
        item_id=7,
        item_type="Question",
        statement=statement,
        newest_answers_link_id=11,
        answered_by_item_id=5,
        newest_answer_created_at="2026-01-01T00:00:00+00:00",
    )


def _join(lines: list[str]) -> str:
    return "\n".join(lines)


def test_close_proposal_block_round_trip_proposal() -> None:
    lines = format_proposal_block(
        _candidate(),
        CloseProposal(
            reason="expired", confidence=0.8, rationale="answered long ago"
        ),
        index=1,
        total=2,
    )
    parsed = parse_close_proposal_block(_join(lines))

    assert parsed.parsed is True
    assert parsed.fields == {
        "index": 1,
        "total": 2,
        "item_id": 7,
        "item_type": "Question",
        "statement": "should we cache tokens?",
        "newest_answers_link_id": 11,
        "newest_answer_created_at": "2026-01-01T00:00:00+00:00",
        "reason": "expired",
        "confidence": 0.8,
        "rationale": "answered long ago",
    }


def test_close_proposal_block_round_trip_decline() -> None:
    lines = format_proposal_block(_candidate(), None, index=2, total=2)
    parsed = parse_close_proposal_block(_join(lines))

    assert parsed.parsed is True
    assert parsed.fields["statement"] == "should we cache tokens?"
    assert "reason" not in parsed.fields
    assert "confidence" not in parsed.fields
    assert "rationale" not in parsed.fields


def test_close_proposal_block_null_rationale_and_emoji_statement() -> None:
    lines = format_proposal_block(
        _candidate(statement="🚀 should we 🚀 launch?"),
        CloseProposal(reason="invalidated", confidence=0.5, rationale=None),
        index=1,
        total=1,
    )
    parsed = parse_close_proposal_block(_join(lines))

    assert parsed.parsed is True
    assert parsed.fields["statement"] == "🚀 should we 🚀 launch?"
    assert parsed.fields["reason"] == "invalidated"
    assert parsed.fields["rationale"] is None


def test_close_proposal_block_statement_with_commas_and_brackets() -> None:
    lines = format_proposal_block(
        _candidate(statement="wait: [x], then y, then z"),
        CloseProposal(reason="expired", confidence=0.8, rationale="-"),
        index=1,
        total=1,
    )
    parsed = parse_close_proposal_block(_join(lines))

    assert parsed.parsed is True
    assert parsed.fields["statement"] == "wait: [x], then y, then z"
    # The formatter prints `-` for a null rationale, so a literal `-` reads
    # back as None (the preview parser shares the convention).
    assert parsed.fields["rationale"] is None


def test_close_proposal_block_broken_returns_unparsed_with_raw_text() -> None:
    broken = (
        "Proposal 1/2: item 7 [Question] q?\n"
        "  newest answers link gone, confirmed 2026-01-01T00:00:00+00:00\n"
        "  no close proposed\n"
    )

    parsed = parse_close_proposal_block(broken)

    assert parsed.parsed is False
    assert parsed.fields == {}
    assert parsed.text == broken


def test_close_proposal_block_all_values_round_trip_via_json_text() -> None:
    """A value containing `: ` rides the non-quoted reason/rationale shapes."""
    lines = format_proposal_block(
        _candidate(),
        CloseProposal(
            reason="expired", confidence=1.0, rationale="time: it passed"
        ),
        index=1,
        total=1,
    )
    parsed = parse_close_proposal_block(_join(lines))

    assert parsed.parsed is True
    assert parsed.fields["reason"] == "expired"
    assert parsed.fields["confidence"] == 1.0
    assert parsed.fields["rationale"] == "time: it passed"


def test_all_parsers_never_return_none() -> None:
    """I4: a named `ParsedBlock`, never a bare `None`, on any input."""
    for parse in (
        parse_capture_block,
        parse_link_preview,
        parse_link_block,
        parse_close_proposal_block,
    ):
        for text in ("", "garbage\nlines"):
            parsed = parse(text)
            assert parsed is not None
            assert parsed.text == text
            if not parsed.parsed:
                assert parsed.fields == {}

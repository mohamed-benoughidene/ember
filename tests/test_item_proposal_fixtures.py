"""Parser tests on saved AI answers (Rule T7: assert schema and types, not prose).

The fixtures are hand-written sample answers that match the shape the provider
is asked for. No real provider adapter exists yet (plan section 7), so they are
representative rather than captured from a live call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ember.capture.item_proposal import ItemType, parse_proposals

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ai_responses"

# case name -> (kept proposals, dropped proposals). Counts only, never prose.
EXPECTED = {"case_01": (3, 0), "case_02": (1, 3)}


def _cases() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("*.response.json"))


def _raw_text_for(response_path: Path) -> str:
    raw_path = response_path.with_name(
        response_path.name.replace(".response.json", ".raw_text.txt")
    )
    return raw_path.read_text(encoding="utf-8")


def test_at_least_one_fixture_exists() -> None:
    assert _cases(), "no saved AI response fixtures found"


@pytest.mark.parametrize("case_path", _cases(), ids=lambda path: path.name)
def test_saved_answer_parses_to_the_expected_schema(case_path: Path) -> None:
    raw_text = _raw_text_for(case_path)
    response = case_path.read_text(encoding="utf-8")

    batch = parse_proposals(response, raw_text)

    for proposal in batch.proposals:
        assert isinstance(proposal.type, ItemType)
        assert proposal.statement.strip() != ""
        assert proposal.source_quote in raw_text
        assert 0.0 <= proposal.confidence <= 1.0

    kept, dropped = EXPECTED[case_path.name.split(".", 1)[0]]
    assert len(batch.proposals) == kept
    assert len(batch.dropped) == dropped

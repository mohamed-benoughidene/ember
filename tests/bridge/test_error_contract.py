"""The app-side stderr parsing rule as a live contract (bridge L2 §5.2).

`log_line()` is unchanged. The app reads stderr and matches the regex in the
shared fixture file `tests/fixtures/bridge/error_parsing_rule.txt` with
`re.S`, so a newline or a `|` inside a free-text value (for example a raw
`--reason`) cannot break the parse: further lines are continuation of
`rest`. Later steps (the app tests) read the same fixture file.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.bridge import harness

RULE_FILE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "bridge"
    / "error_parsing_rule.txt"
)


def _rule() -> re.Pattern[str]:
    return re.compile(RULE_FILE.read_text(encoding="utf-8"), re.S)


def test_fixture_holds_the_pinned_pattern() -> None:
    assert _rule().pattern == (
        r"\Aerror: (?P<code>[A-Z]+-\d{3}) (?P<name>\w+)"
        r" \| (?P<where>[^|\n]+) \| (?P<rest>.*)\Z"
    )


def test_a_pipe_in_a_reason_value_cannot_break_the_rule(db_path: str) -> None:
    harness.seed_pair(db_path)

    result = harness.invoke(
        ["close-item", "--item", "1", "--reason", "a | b", "--db", db_path]
    )

    assert result.exit_code == 1
    match = _rule().match(result.stderr)
    assert match is not None
    assert match["code"] == "MAINTAIN-002"
    assert match["name"] == "CloseReasonInvalid"
    assert "a | b" in match["rest"]


def test_a_newline_in_a_reason_value_cannot_break_the_rule(db_path: str) -> None:
    harness.seed_pair(db_path)

    result = harness.invoke(
        ["close-item", "--item", "1", "--reason", "two\nlines", "--db", db_path]
    )

    assert result.exit_code == 1
    match = _rule().match(result.stderr)
    assert match is not None
    assert match["code"] == "MAINTAIN-002"
    assert "two\nlines" in match["rest"]
    assert "\n" not in match["where"]

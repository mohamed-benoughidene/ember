"""The shared event-schema fixture, checked against the engine's REAL events.

`tests/fixtures/bridge/event_schema.json` is ONE file both sides read: it is
written FROM the real `--confirm json` event stream (the `JsonSink` emitters
in ember/adapters/json_confirm.py and the three summary field dicts passed
to `sink.summary()` in ember/cli.py). This module proves the engine half.

Three real scripted sessions (the tests/bridge confirm seams — capture,
relate, maintain — real temp knowledge bases, faked AI at the production
seams) run under `--confirm json`, and every stdout line must:

- be one JSON object naming a schema event,
- carry every required key, well typed (and every listed key that IS
  present well typed),
- carry NO key the fixture does not list.

The last two directions together pin the fixture to the engine both ways:
every schema key must also occur in at least one real event, so a required
key dropped from the fixture makes a real event carry an unlisted key and
this file FAILS against real engine output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.bridge.confirm_scenarios import (
    capture_session,
    maintain_session,
    relate_session,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "bridge"
    / "event_schema.json"
)

# command -> (session fn, the scripted JSON answer lines on stdin)
SESSIONS = {
    "capture": (capture_session, '{"answer": "y"}\n{"answer": "n"}\n'),
    "relate": (
        relate_session,
        '{"answer": "y"}\n{"answer": "n"}\n{"answer": "s"}\n',
    ),
    "maintain": (maintain_session, '{"answer": "y"}\n{"answer": "n"}\n'),
}

# The exact summary key set each command emits (the engine's own
# arithmetic — pinned per command so the fixture cannot drift). `line` is
# the human summary line every command carries next to its fields
# (4.3 #26, additive D5).
EXPECTED_SUMMARY_KEYS = {
    "capture": {"event", "line", "accepted", "rejected", "warnings", "aborted"},
    "relate": {"event", "line", "accepted", "rejected", "skipped", "aborted"},
    "maintain": {
        "event",
        "line",
        "stale",
        "proposed",
        "accepted",
        "rejected",
        "aborted",
    },
}

# Every event seen in the three real sessions, per event name (the
# fixture-coverage test reads this; the shape tests above run first).
_SEEN: dict[str, list[dict]] = {}


def _schema() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _events(result) -> list[dict]:
    """Every STDOUT line must be one JSON object (click 8.2+ mixes stderr
    into `result.output`; the event stream lives on stdout only)."""
    return [json.loads(line) for line in result.stdout.splitlines()]


def _matches(value: object, allowed: list[str]) -> bool:
    """One JSON value satisfies one event-schema type list."""
    if "null" in allowed and value is None:
        return True
    if "boolean" in allowed and isinstance(value, bool):
        return True
    if (
        "number" in allowed
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return True
    if "array" in allowed and isinstance(value, list):
        return True
    if "object" in allowed and isinstance(value, dict):
        return True
    if "string" in allowed and isinstance(value, str):
        return True
    return False


def assert_satisfies_schema(event: dict, schema: dict) -> None:
    entry = schema[event["event"]]
    allowed = {**entry["required"], **entry["optional"]}
    missing = [key for key in entry["required"] if key not in event]
    assert missing == [], (event, f"missing required keys {missing}")
    unknown = [key for key in event if key not in allowed]
    assert unknown == [], (event, f"keys the fixture does not list: {unknown}")
    for key, types in allowed.items():
        if key in event:
            assert _matches(event[key], types), (key, event[key], types)


def test_the_fixture_lists_the_four_pinned_events_with_valid_types() -> None:
    schema = _schema()
    names = {key for key in schema if not key.startswith("$")}
    assert names == {"block", "prompt", "message", "summary"}
    for name in ("block", "prompt", "message", "summary"):
        entry = schema[name]
        assert set(entry) == {"required", "optional"}, (name, set(entry))
        for section in ("required", "optional"):
            for key, types in entry[section].items():
                assert isinstance(types, list) and types, (name, key)
                assert set(types) <= {
                    "string",
                    "number",
                    "boolean",
                    "array",
                    "object",
                    "null",
                }, (name, key, types)


@pytest.mark.parametrize(
    ("command", "answers"),
    [(name, session[1]) for name, session in SESSIONS.items()],
)
def test_every_real_event_line_satisfies_the_shared_schema(
    tmp_path: Path, command: str, answers: str
) -> None:
    session = SESSIONS[command][0]
    result = session(tmp_path, input_text=answers, extra_args=("--confirm", "json"))

    assert result.exit_code == 0, (command, result.exit_code, result.output)
    schema = _schema()
    events = _events(result)
    assert events, f"{command}: the session emitted no events"
    for event in events:
        assert event["event"] in schema, (command, event)
        assert_satisfies_schema(event, schema)
        _SEEN.setdefault(event["event"], []).append(event)
    summary = events[-1]
    assert summary["event"] == "summary"
    assert set(summary) == EXPECTED_SUMMARY_KEYS[command], summary


def test_every_schema_key_occurs_in_a_real_event() -> None:
    """The fixture is written FROM the engine's events, not from memory:
    every required and optional key of every event entry is seen in one of
    the three real sessions above. A required key dropped from the fixture
    makes the real event carry an unlisted key, so the shape tests above
    fail against real events (and this file fails the coverage too)."""
    schema = _schema()
    assert _SEEN, "the sessions above must have run"
    for name in ("block", "prompt", "message", "summary"):
        entry = schema[name]
        for key in {**entry["required"], **entry["optional"]}:
            assert any(
                key in event for event in _SEEN.get(name, [])
            ), (name, key, "never seen in the real sessions")

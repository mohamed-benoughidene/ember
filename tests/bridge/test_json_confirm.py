"""Unit tests for `ember/adapters/json_confirm.py` on in-memory pipes (T3).

No subprocess and no real stdin: the events go to a `io.StringIO` injected
into the `JsonSink`, the answers come from a `io.StringIO` injected into the
confirm class. Covers the answer protocol (BRIDGE-001 re-ask once, then the
engine's own `UserAbort`), the prompt kinds, the choices parsed from each
engine's real PROMPT constant, and the block routing/buffering per engine.
"""

from __future__ import annotations

import io
import json

import pytest

from ember.adapters.errors import AnswerLineInvalid
from ember.adapters.json_confirm import (
    JsonCaptureConfirm,
    JsonMaintainConfirm,
    JsonRelateConfirm,
    JsonSink,
    _parse_answer,
    choices_from_prompt,
)
from ember.capture.confirm_write import PROMPT as CAPTURE_PROMPT
from ember.capture.errors import UserAbort as CaptureUserAbort
from ember.maintain.close_proposer import PROMPT as MAINTAIN_PROMPT
from ember.maintain.errors import UserAbort as MaintainUserAbort
from ember.relate.confirm_write import (
    PROMPT as RELATE_PROMPT,
    _preview_line,
    format_link_block,
)
from ember.relate.errors import UserAbort as RelateUserAbort
from ember.relate.link_gatekeeper import ValidatedLink
from ember.relate.rows import ChangeLogEntry, Link

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _sink() -> tuple[JsonSink, io.StringIO]:
    stream = io.StringIO()
    return JsonSink(stream), stream


def _capture(stdin_text: str) -> tuple[JsonCaptureConfirm, io.StringIO]:
    sink, stream = _sink()
    return JsonCaptureConfirm(sink, stdin=io.StringIO(stdin_text)), stream


def _events(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_choices_are_parsed_from_the_real_prompt_constants() -> None:
    assert choices_from_prompt(CAPTURE_PROMPT) == ["y", "n", "e", "q"]
    assert choices_from_prompt(RELATE_PROMPT) == ["y", "n", "s", "q"]
    assert choices_from_prompt(MAINTAIN_PROMPT) == ["y", "n", "q"]


def test_answer_line_returns_the_text_and_emits_one_prompt_event() -> None:
    confirm, stream = _capture('{"answer": "y"}\n')

    assert confirm.ask(CAPTURE_PROMPT) == "y"
    assert _events(stream) == [
        {
            "event": "prompt",
            "kind": "choice",
            "text": CAPTURE_PROMPT,
            "choices": ["y", "n", "e", "q"],
        }
    ]
    assert stream.getvalue().endswith("\n")  # one flushed line


def test_every_line_is_flushed_as_it_is_written() -> None:
    sink, stream = _sink()
    sink.echo("hello")
    # Flushed immediately: visible before any second call.
    assert stream.getvalue() == json.dumps({"event": "message", "text": "hello"}) + "\n"
    sink.summary("ignored line", {"accepted": 1, "aborted": False})
    assert _events(stream) == [
        {"event": "message", "text": "hello"},
        {"event": "summary", "accepted": 1, "aborted": False},
    ]


@pytest.mark.parametrize(
    ("prompt", "kind"),
    [
        ("new type? (default Decision)", "type"),
        ("new statement? (default Use SQLite)", "statement"),
        ("new metadata? (default none)", "metadata"),
    ],
)
def test_capture_edit_sub_prompt_kinds(prompt: str, kind: str) -> None:
    confirm, stream = _capture('{"answer": ""}\n')

    confirm.ask(prompt)

    event = _events(stream)[0]
    assert event["event"] == "prompt"
    assert event["kind"] == kind
    assert event["text"] == prompt
    assert event["choices"] == []


def test_first_bad_line_reasks_once_then_accepts_the_good_answer() -> None:
    confirm, stream = _capture('not json at all\n{"answer": "e"}\n')

    assert confirm.ask(CAPTURE_PROMPT) == "e"

    # The prompt event fired twice: the original ask and the ONE re-ask.
    assert [event["event"] for event in _events(stream)] == ["prompt", "prompt"]


def test_second_bad_line_raises_the_engine_user_abort() -> None:
    confirm, _ = _capture('{"answer": 5}\nnot json\n')

    with pytest.raises(CaptureUserAbort):
        confirm.ask(CAPTURE_PROMPT)


def test_valid_but_unknown_answer_is_returned_untouched() -> None:
    confirm, _ = _capture('{"answer": "maybe"}\n')

    assert confirm.ask(CAPTURE_PROMPT) == "maybe"


def test_empty_answer_string_is_a_valid_line() -> None:
    confirm, _ = _capture('{"answer": ""}\n')

    assert confirm.ask("new type? (default Decision)") == ""


def test_extra_keys_in_the_answer_line_are_refused_then_reasked() -> None:
    confirm, stream = _capture('{"answer": "y", "extra": 1}\n{"answer": "y"}\n')

    assert confirm.ask(CAPTURE_PROMPT) == "y"
    assert len(_events(stream)) == 2  # original prompt + one re-ask


# --- the D4 edge validation itself (BRIDGE-001) ------------------------------


def test_answer_line_invalid_carries_the_bridge_001_code() -> None:
    with pytest.raises(AnswerLineInvalid) as excinfo:
        _parse_answer("garbage\n")

    assert excinfo.value.log_line().startswith("BRIDGE-001 AnswerLineInvalid")


def test_answer_line_refuses_a_non_string_answer() -> None:
    with pytest.raises(AnswerLineInvalid):
        _parse_answer('{"answer": 5}\n')


def test_answer_line_refuses_a_non_object_line() -> None:
    with pytest.raises(AnswerLineInvalid):
        _parse_answer('["y"]\n')


# --- end of input and engine-specific aborts ---------------------------------


@pytest.mark.parametrize(
    ("confirm_cls", "abort_cls"),
    [
        (JsonCaptureConfirm, CaptureUserAbort),
        (JsonRelateConfirm, RelateUserAbort),
        (JsonMaintainConfirm, MaintainUserAbort),
    ],
)
def test_end_of_input_raises_that_engine_user_abort(
    confirm_cls: type, abort_cls: type[Exception]
) -> None:
    sink, _ = _sink()
    confirm = confirm_cls(sink, stdin=io.StringIO(""))

    with pytest.raises(abort_cls):
        confirm.ask(CAPTURE_PROMPT)


# --- relate write routing ----------------------------------------------------


def _link(rationale: str | None) -> ValidatedLink:
    return ValidatedLink(
        link_row=Link(
            id=3,
            source_item_id=1,
            target_item_id=4,
            link_type="depends_on",
            status="Confirmed",
            created_at=FIXED_TIME,
        ),
        change_log_row=ChangeLogEntry(
            item_id=1,
            link_id=3,
            field_changed="link_confirmed",
            old_value=None,
            new_value="depends_on:4",
            timestamp=FIXED_TIME,
            trigger_cause="user_confirmed",
        ),
        rationale=rationale,
    )


def test_relate_preview_is_a_link_preview_block_event_before_the_prompt() -> None:
    sink, stream = _sink()
    confirm = JsonRelateConfirm(sink, stdin=io.StringIO('{"answer": "y"}\n'))
    preview = _preview_line(1, 2, _link(rationale="why: this"))

    confirm.write(preview)
    confirm.ask(RELATE_PROMPT)

    events = _events(stream)
    assert [event["event"] for event in events] == ["block", "prompt"]
    assert events[0]["kind"] == "link-preview"
    assert events[0]["fields"]["link_type"] == "depends_on"
    assert events[0]["text"] == preview


def test_relate_link_block_is_a_link_block_event() -> None:
    sink, stream = _sink()
    confirm = JsonRelateConfirm(sink, stdin=io.StringIO(""))

    confirm.write(format_link_block(_link(rationale=None)))

    (event,) = _events(stream)
    assert event["event"] == "block"
    assert event["kind"] == "link"
    assert event["fields"]["link_id"] == 3
    assert event["fields"]["rationale"] is None


def test_relate_other_writes_are_message_events() -> None:
    sink, stream = _sink()
    confirm = JsonRelateConfirm(sink, stdin=io.StringIO(""))

    confirm.write("some plain line")
    confirm.write(
        format_link_block(_link(rationale=None)).replace("- link_id:", "- gone:")
    )

    events = _events(stream)
    assert [event["event"] for event in events] == ["message", "message"]
    assert events[0]["text"] == "some plain line"


# --- maintain buffering ------------------------------------------------------


def test_maintain_decline_block_emits_one_close_event_without_asking() -> None:
    sink, stream = _sink()
    confirm = JsonMaintainConfirm(sink, stdin=io.StringIO(""))

    confirm.write("Proposal 1/1: item 7 [Question] q?")
    confirm.write("  newest answers link 11, confirmed " + FIXED_TIME)
    confirm.write("  no close proposed")

    (event,) = _events(stream)
    assert event["event"] == "block"
    assert event["kind"] == "close"
    assert event["fields"]["item_id"] == 7
    assert "reason" not in event["fields"]


def test_maintain_proposal_block_is_flushed_at_its_rationale_line() -> None:
    sink, stream = _sink()
    confirm = JsonMaintainConfirm(sink, stdin=io.StringIO('{"answer": "n"}\n'))

    confirm.write("Proposal 1/1: item 7 [Question] q?")
    confirm.write("  newest answers link 11, confirmed " + FIXED_TIME)
    confirm.write("  reason: expired, confidence 0.8")
    confirm.write("  rationale: settled by tests")
    # The `rationale:` line ends the block: one flushed `close` event, no
    # prompt yet.
    events = _events(stream)
    assert [event["event"] for event in events] == ["block"]
    assert events[0]["kind"] == "close"
    assert events[0]["fields"]["reason"] == "expired"

    confirm.ask(MAINTAIN_PROMPT)
    events = _events(stream)
    assert [event["event"] for event in events] == ["block", "prompt"]
    assert events[1]["kind"] == "choice"
    assert events[1]["choices"] == ["y", "n", "q"]


def test_maintain_next_proposal_starts_after_the_flushed_previous_block() -> None:
    sink, stream = _sink()
    confirm = JsonMaintainConfirm(sink, stdin=io.StringIO(""))

    confirm.write("Proposal 1/2: item 7 [Question] q?")
    confirm.write("  newest answers link 11, confirmed " + FIXED_TIME)
    confirm.write("  no close proposed")
    # The decline block is complete (terminator seen), so it is already out.
    confirm.write("Proposal 2/2: item 9 [Question] later?")

    events = _events(stream)
    # Block 7 flushed; the head of block 9 is buffered (its event waits for
    # the block to end) — exactly one event so far.
    assert len(events) == 1
    assert events[0]["kind"] == "close"
    assert events[0]["fields"]["item_id"] == 7

    # The prompt flushes whatever is pending first (here: the lone head of
    # block 9, which no longer parses -> `fields: null`, raw text kept).
    with pytest.raises(MaintainUserAbort):
        confirm.ask(MAINTAIN_PROMPT)
    events = _events(stream)
    assert [event["event"] for event in events] == ["block", "block", "prompt"]
    assert events[1]["fields"] is None
    assert events[1]["text"] == "Proposal 2/2: item 9 [Question] later?"


def test_maintain_report_lines_are_message_events() -> None:
    sink, stream = _sink()
    confirm = JsonMaintainConfirm(sink, stdin=io.StringIO(""))

    confirm.write("item 9: Active -> Closed (expired)")
    confirm.write("closed: 1, challenged: 0, reopened: 0, unchanged: 3")

    events = _events(stream)
    assert [event["event"] for event in events] == ["message", "message"]
    assert events[0]["text"] == "item 9: Active -> Closed (expired)"


def test_maintain_drifted_block_still_emits_the_raw_text() -> None:
    sink, stream = _sink()
    confirm = JsonMaintainConfirm(sink, stdin=io.StringIO(""))

    confirm.write("Proposal broken head")
    confirm.write("  missing answers link line")
    confirm.write("  no close proposed")

    (event,) = _events(stream)
    assert event["event"] == "block"
    assert event["kind"] == "close"
    assert event["fields"] is None
    assert (
        event["text"]
        == "Proposal broken head\n  missing answers link line\n  no close proposed"
    )

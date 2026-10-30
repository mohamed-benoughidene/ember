"""The JSON-lines confirm adapter (bridge step 03, L2 §5.4, P4/T2).

`--confirm json` replaces the terminal user I/O of `capture`, `relate` and
`maintain` with a pipe protocol, chosen HERE at the composition root call in
`ember/cli.py` (P4: a real choice of adapter for the engines' existing
`ConfirmPort` protocols — the engines are untouched):

- stdout carries EVENTS, one JSON object per line, flushed after every line:
  `{"event": "block", "kind": ..., "fields": ...|null, "text": ...}`,
  `{"event": "prompt", "kind": ..., "text": ..., "choices": [...]}`,
  `{"event": "message", "text": ...}` and the final
  `{"event": "summary", ...}`.
- stdin carries ANSWERS, one JSON object per line: `{"answer": "<text>"}`.
  stdin data is untrusted and is validated ONCE here (D4): a line that is
  not exactly `{"answer": <string>}` raises `BRIDGE-001 AnswerLineInvalid`
  internally and the prompt is re-asked ONCE; a second bad line, or the end
  of input, raises the engine's own `UserAbort` (exit 2), exactly as the
  terminal classes do on a closed stdin.

The output sink sits beside the confirm classes because several printed
lines BYPASS the confirm port today (the capture drops/gatekeeper prints,
the relate rejection lines, the maintain sweep report and the stale-cap
note). Every stdout line of the three bodies flows through one sink:
terminal mode echoes byte for byte as before; JSON mode wraps each line as
a `message` event and turns the bodies' final summary lines into `summary`
events. stderr lines (`source already stored`, the relate pool warning and
every `error: ...` line) stay on stderr in both modes (I12).

Block events: each engine's pre-formatted blocks are recognized here and
parsed by `ember/bridge/block_parse.py` (T9: the pure parser imports no
adapter). `fields` is null whenever a parse fails; `text` always carries
the raw block. The relate preview is a `link-preview` event BEFORE its
prompt; the YAML link block a `link` event AFTER the write; the maintain
proposal lines are buffered into one `close` event (the engine writes them
one line at a time) — a block ends at `no close proposed`, at its
`rationale:` line, at the next proposal's head, or at the first prompt.

The `prompt` `choices` are parsed out of each engine's real `PROMPT`
constant (never re-typed here), and the `kind` picks the pinned event kinds
(`choice` for a main confirm prompt, `type`/`statement`/`metadata` for the
capture edit sub-prompts).
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, TextIO

import click

from ember.adapters.errors import AnswerLineInvalid
from ember.bridge.block_parse import (
    ParsedBlock,
    parse_capture_block,
    parse_close_proposal_block,
    parse_link_block,
    parse_link_preview,
)
from ember.capture.confirm_write import PROMPT as CAPTURE_PROMPT
from ember.capture.errors import UserAbort as CaptureUserAbort
from ember.maintain.errors import UserAbort as MaintainUserAbort
from ember.relate.errors import UserAbort as RelateUserAbort

# The capture edit sub-prompts are built inline by the engine
# (`ask_type` / `ask_statement` / `ask_metadata`); only their finished text
# reaches this port, so the kind is classified from the prompt text.
_EDIT_KIND_PREFIXES = (
    ("new type?", "type"),
    ("new statement?", "statement"),
    ("new metadata?", "metadata"),
)

# One bracketed letter per choice segment: "[y]es / [n]o / [e]dit / [q]uit".
_CHOICE_LETTER = re.compile(r"\[([a-z])\]")


def choices_from_prompt(prompt: str) -> list[str]:
    """The choice letters parsed out of a PROMPT constant's text."""
    return _CHOICE_LETTER.findall(prompt)


def _parse_answer(line: str) -> str:
    """Validate one stdin answer line at the edge (D4, BRIDGE-001)."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AnswerLineInvalid("answer line is not JSON") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"answer"}
        or not isinstance(data["answer"], str)
    ):
        raise AnswerLineInvalid('answer line is not exactly {"answer": <string>}')
    return data["answer"]


# --- the output sink ---------------------------------------------------------


class TerminalSink:
    """`--confirm terminal` output: plain `click.echo`, byte-identical to
    the pre-bridge bodies. `summary` still echoes the summary line; the
    `fields` argument is ignored here (one source for the numbers, though:
    both the line and the fields are built from the same result object)."""

    def echo(self, text: str) -> None:
        click.echo(text)

    def summary(self, line: str, fields: dict[str, Any]) -> None:
        click.echo(line)


class JsonSink:
    """`--confirm json` output: one JSON event object per line, written to
    stdout and flushed immediately (the window may be reading line by
    line). Key order is the events' natural order (event first), matching
    the step file's samples; `ensure_ascii=False` keeps text verbatim."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = sys.stdout if stream is None else stream

    def _emit(self, event: dict[str, Any]) -> None:
        self._stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._stream.flush()

    def echo(self, text: str) -> None:
        self._emit({"event": "message", "text": text})

    def summary(self, line: str, fields: dict[str, Any]) -> None:
        self._emit({"event": "summary", **fields})

    def prompt(self, kind: str, text: str, choices: list[str]) -> None:
        self._emit(
            {"event": "prompt", "kind": kind, "text": text, "choices": choices}
        )

    def block(self, kind: str, parsed: ParsedBlock) -> None:
        self._emit(
            {
                "event": "block",
                "kind": kind,
                "fields": parsed.fields if parsed.parsed else None,
                "text": parsed.text,
            }
        )


# --- the three JSON ConfirmPort classes --------------------------------------


class _JsonConfirm:
    """Base for the three JSON confirm ports: emits the prompt event, reads
    one `{"answer": ...}` line, re-asks ONCE on a bad line, then aborts with
    the engine's own `UserAbort` (a second bad line or end of input)."""

    user_abort: type[Exception]

    def __init__(self, sink: JsonSink, *, stdin: TextIO | None = None) -> None:
        self._sink = sink
        self._stdin = sys.stdin if stdin is None else stdin

    def ask(self, prompt: str) -> str:
        self._emit_prompt(prompt)
        try:
            return self._read_answer()
        except AnswerLineInvalid:
            pass  # first bad line: re-ask ONCE
        self._emit_prompt(prompt)
        try:
            return self._read_answer()
        except AnswerLineInvalid as exc:
            raise self.user_abort("invalid answer line") from exc

    def _read_answer(self) -> str:
        line = self._stdin.readline()
        if line == "":
            raise self.user_abort("input ended")
        return _parse_answer(line)

    def write(self, text: str) -> None:
        self._sink.echo(text)

    def _emit_prompt(self, prompt: str) -> None:
        kind = self._prompt_kind(prompt)
        choices = choices_from_prompt(prompt) if kind == "choice" else []
        self._sink.prompt(kind, prompt, choices)

    def _prompt_kind(self, prompt: str) -> str:
        raise NotImplementedError


class JsonCaptureConfirm(_JsonConfirm):
    """JSON confirm port for the capture loop (raises CAPTURE-014). The
    engine's pre-prompt YAML block is an `item` block event (fields parsed
    from the real `format_block` shape, null on drift); every other engine
    write (the near-duplicate warning line, `invalid type`, `statement is
    empty`, a revalidated `dropped proposal`) is a message event."""

    user_abort = CaptureUserAbort

    def _prompt_kind(self, prompt: str) -> str:
        if prompt == CAPTURE_PROMPT:
            return "choice"
        return self._edit_kind(prompt)

    @staticmethod
    def _edit_kind(prompt: str) -> str:
        for prefix, kind in _EDIT_KIND_PREFIXES:
            if prompt.startswith(prefix):
                return kind
        return "statement"  # unreachable while the engine texts hold

    def write(self, text: str) -> None:
        if text.startswith("- id: "):
            self._sink.block("item", parse_capture_block(text))
        else:
            self._sink.echo(text)


class JsonRelateConfirm(_JsonConfirm):
    """JSON confirm port for the relate loop (raises RELATE-031). The
    preview is a `link-preview` block event before the prompt; the YAML
    link block a `link` block event after the accepted write."""

    user_abort = RelateUserAbort

    def _prompt_kind(self, prompt: str) -> str:
        return "choice"

    def write(self, text: str) -> None:
        if text.startswith("Proposal "):
            self._sink.block("link-preview", parse_link_preview(text))
        elif text.startswith("- link_id: "):
            self._sink.block("link", parse_link_block(text))
        else:
            self._sink.echo(text)


class JsonMaintainConfirm(_JsonConfirm):
    """JSON confirm port for the maintain proposal loop (raises
    MAINTAIN-022). The engine writes the proposal block one line at a time,
    so the lines are buffered here into ONE `close` block event. A block
    ends at `no close proposed` (a decline, which is followed by no
    prompt), at its `rationale:` line, at the next proposal's head, or at
    the first prompt. The accepted-close report lines after a `y` are
    message events."""

    user_abort = MaintainUserAbort

    def __init__(self, sink: JsonSink, *, stdin: TextIO | None = None) -> None:
        super().__init__(sink, stdin=stdin)
        self._pending: list[str] = []

    def ask(self, prompt: str) -> str:
        self._flush()
        return super().ask(prompt)

    def write(self, text: str) -> None:
        if text.startswith("Proposal "):
            self._flush()
            self._pending.append(text)
        elif text.startswith("  ") and self._pending:
            self._pending.append(text)
            if text == "  no close proposed" or text.startswith("  rationale: "):
                self._flush()
        else:
            self._flush()
            self._sink.echo(text)

    def _prompt_kind(self, prompt: str) -> str:
        return "choice"

    def _flush(self) -> None:
        if not self._pending:
            return
        self._sink.block(
            "close", parse_close_proposal_block("\n".join(self._pending))
        )
        self._pending.clear()

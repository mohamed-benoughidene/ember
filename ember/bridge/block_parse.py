"""Pure block parsers for the JSON event stream (bridge step 03, L2 §5.4).

One parser per engine formatter, each reading the REAL output shape (L2 §2):
the capture `format_block` (including the bare `confidence` and the NON-JSON
`near_dup_warning: {matching_item_id: N, similarity: X}` dict), the relate
preview line, the relate `format_link_block` YAML, and the maintain
`format_proposal_block` (whose values are NOT JSON-quoted).

Pure (T1): string in, named `ParsedBlock` out, no I/O, no clock, no click.
`ParsedBlock` is never `None` (I4). On any drift a parser returns
`parsed=False` with an empty `fields` dict; the caller (the JSON confirm
adapter) then emits `"fields": null` and keeps `text` — the raw block — so a
parse failure never loses data. Round-trip tests
(`tests/bridge/test_block_parse.py`) build every block with the REAL
formatters and fail first if a formatter ever changes shape.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel


class ParsedBlock(BaseModel):
    """One formatted block. `fields` is a dict (empty when `parsed` is
    False; the event stream maps a failed parse to `fields: null`) and
    `text` always carries the raw block verbatim (I4)."""

    parsed: bool
    fields: dict[str, Any]
    text: str


def _failed(text: str) -> ParsedBlock:
    return ParsedBlock(parsed=False, fields={}, text=text)


# --- capture: `ember.capture.confirm_write.format_block` ---------------------
#
# - id: 1
#   type: "Decision"
#   statement: "Use SQLite"
#   source_quote: "use SQLite"
#   confidence: 0.9          (bare, NOT JSON-quoted)
#   metadata: "auth-network" (a JSON string, or null)
#   near_dup_warning: null   (or {matching_item_id: 3, similarity: 0.91} —
#                             deliberately NOT valid JSON)

_CAPTURE_CAPTURE_KEYS = {
    "id",
    "type",
    "statement",
    "source_quote",
    "confidence",
    "metadata",
    "near_dup_warning",
}
_CAPTURE_ID_LINE = re.compile(r"\A- id: (\d+)\Z")
_CAPTURE_FIELD_LINE = re.compile(r"\A  (\w+): (.*)\Z")
_CAPTURE_TEXT_KEYS = {"type", "statement", "source_quote"}
_NEAR_DUP = re.compile(r"\{matching_item_id: (\d+), similarity: (\d+(?:\.\d+)?)\}")


def parse_capture_block(text: str) -> ParsedBlock:
    """Parse the capture confirm block. JSON-quoted values go through
    `json.loads` (so a quote containing `: ` survives); `confidence` is a
    bare float; `near_dup_warning` reads the formatter's own non-JSON dict
    shape. Any drift (wrong keys, extra/missing lines, unparseable value)
    returns `parsed=False`."""
    lines = text.split("\n")
    id_match = _CAPTURE_ID_LINE.match(lines[0]) if lines else None
    if id_match is None or len(lines) != len(_CAPTURE_CAPTURE_KEYS):
        return _failed(text)
    fields: dict[str, Any] = {"id": int(id_match.group(1))}
    try:
        for line in lines[1:]:
            field = _CAPTURE_FIELD_LINE.match(line)
            if field is None:
                raise ValueError(line)
            key, raw = field.group(1), field.group(2)
            if key not in _CAPTURE_CAPTURE_KEYS or key in fields:
                raise ValueError(line)
            if key == "confidence":
                value: Any = float(raw)
            elif key == "near_dup_warning":
                value = _parse_near_dup(raw)
            else:  # type, statement, source_quote, metadata are JSON values
                value = json.loads(raw)
            if key in _CAPTURE_TEXT_KEYS and not isinstance(value, str):
                raise ValueError(line)
            if key == "metadata" and not isinstance(value, (str, type(None))):
                raise ValueError(line)
            fields[key] = value
    except (ValueError, json.JSONDecodeError):
        return _failed(text)
    if set(fields) != _CAPTURE_CAPTURE_KEYS:
        return _failed(text)
    return ParsedBlock(parsed=True, fields=fields, text=text)


def _parse_near_dup(raw: str) -> dict[str, Any] | None:
    if raw == "null":
        return None
    warning = _NEAR_DUP.fullmatch(raw)
    if warning is None:
        raise ValueError(raw)
    return {
        "matching_item_id": int(warning.group(1)),
        "similarity": float(warning.group(2)),
    }


# --- relate: the preview written before each prompt (`_preview_line`) --------
#
# Proposal 1/3: item 1 -> item 4 [depends_on]
#   rationale: -            (or the rationale text; `-` means none)

_PREVIEW_HEAD = re.compile(
    r"\AProposal (\d+)/(\d+): item (\d+) -> item (\d+) \[(.+)\]\Z"
)
_PREVIEW_RATIONALE = "  rationale: "


def parse_link_preview(text: str) -> ParsedBlock:
    """Parse one relate preview (BEFORE its prompt). The head line carries
    the proposal index, both endpoints and the link type; every remaining
    line is the rationale (`-` alone means no rationale)."""
    lines = text.split("\n")
    head = _PREVIEW_HEAD.match(lines[0]) if lines else None
    if head is None or len(lines) < 2 or not lines[1].startswith(_PREVIEW_RATIONALE):
        return _failed(text)
    rationale = "\n".join(lines[1:])[len(_PREVIEW_RATIONALE):]
    fields: dict[str, Any] = {
        "index": int(head.group(1)),
        "total": int(head.group(2)),
        "source_item_id": int(head.group(3)),
        "target_item_id": int(head.group(4)),
        "link_type": head.group(5),
        "rationale": None if rationale == "-" else rationale,
    }
    return ParsedBlock(parsed=True, fields=fields, text=text)


# --- relate: `ember.relate.confirm_write.format_link_block` ------------------
#
# - link_id: 3
#   source_item_id: 1
#   target_item_id: 4
#   link_type: "depends_on"
#   status: "Confirmed"
#   rationale: "..."         (a JSON string, or null)

_LINK_KEYS = (
    "link_id",
    "source_item_id",
    "target_item_id",
    "link_type",
    "status",
    "rationale",
)
_LINK_ID_LINE = re.compile(r"\A- link_id: (\d+)\Z")
_STRING_FIELDS = {"link_type", "status"}
_NULLABLE_STRING_FIELDS = {"rationale"}


def parse_link_block(text: str) -> ParsedBlock:
    """Parse the YAML link block written AFTER an accepted link. Three bare
    int ids and three JSON-quoted strings, in the formatter's fixed order."""
    lines = text.split("\n")
    id_match = _LINK_ID_LINE.match(lines[0]) if lines else None
    if id_match is None or len(lines) != len(_LINK_KEYS):
        return _failed(text)
    fields: dict[str, Any] = {"link_id": int(id_match.group(1))}
    try:
        for key, line in zip(_LINK_KEYS[1:], lines[1:]):
            field = re.fullmatch(rf"  {key}: (.*)", line)
            if field is None:
                raise ValueError(line)
            value = json.loads(field.group(1))
            if key in _STRING_FIELDS and not isinstance(value, str):
                raise ValueError(line)
            if key in _NULLABLE_STRING_FIELDS and not isinstance(
                value, (str, type(None))
            ):
                raise ValueError(line)
            fields[key] = value
    except (ValueError, json.JSONDecodeError):
        return _failed(text)
    if set(fields) != set(_LINK_KEYS):
        return _failed(text)
    return ParsedBlock(parsed=True, fields=fields, text=text)


# --- maintain: `ember.maintain.close_proposer.format_proposal_block` ---------
#
# Proposal 1/2: item 7 [Question] should we cache tokens?
#   newest answers link 11, confirmed 2026-01-01T00:00:00+00:00
#   no close proposed                          <- a decline ends the block here
# OR
#   reason: expired, confidence 0.8            (values NOT JSON-quoted)
#   rationale: answered long ago, ...          (`-` when the rationale is null)

_CLOSE_HEAD = re.compile(r"\AProposal (\d+)/(\d+): item (\d+) \[([^\]]+)\] (.*)\Z")
_CLOSE_ANSWERS = re.compile(r"\A  newest answers link (\d+), confirmed (.+)\Z")
_CLOSE_REASON = re.compile(r"\A  reason: (.*), confidence (\d+(?:\.\d+)?)\Z")
_CLOSE_RATIONALE = "  rationale: "
_NO_CLOSE = "  no close proposed"


def parse_close_proposal_block(text: str) -> ParsedBlock:
    """Parse one maintain proposal block (the lines the confirm port writes
    before the prompt, joined by the adapter). A decline block ends at
    `no close proposed` and carries no `reason`/`confidence`/`rationale`
    keys; a proposal block ends at its rationale line."""
    lines = text.split("\n")
    head = _CLOSE_HEAD.match(lines[0]) if lines else None
    if head is None or len(lines) < 3:
        return _failed(text)
    answers = _CLOSE_ANSWERS.match(lines[1])
    if answers is None:
        return _failed(text)
    fields: dict[str, Any] = {
        "index": int(head.group(1)),
        "total": int(head.group(2)),
        "item_id": int(head.group(3)),
        "item_type": head.group(4),
        "statement": head.group(5),
        "newest_answers_link_id": int(answers.group(1)),
        "newest_answer_created_at": answers.group(2),
    }
    if len(lines) == 3 and lines[2] == _NO_CLOSE:
        return ParsedBlock(parsed=True, fields=fields, text=text)
    if len(lines) < 4 or not lines[2].startswith("  reason: "):
        return _failed(text)
    reason = _CLOSE_REASON.match(lines[2])
    if reason is None or not lines[3].startswith(_CLOSE_RATIONALE):
        return _failed(text)
    fields["reason"] = reason.group(1)
    fields["confidence"] = float(reason.group(2))
    rationale = "\n".join(lines[3:])[len(_CLOSE_RATIONALE):]
    fields["rationale"] = None if rationale == "-" else rationale
    return ParsedBlock(parsed=True, fields=fields, text=text)

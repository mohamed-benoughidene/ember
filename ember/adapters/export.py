"""`ember export`: one readable text rendering of the whole knowledge base (L2 §5.2).

The whole job is a B1 rendering: gather every `items`, `links`, `sources`
and `change_log` row, render them as human-first plain text, emit to a
file or stdout. It is a read over the live database, never a write: the
CLI opens the store through `open_query_database` (QUERY-003/004 floors,
never migrates) and `gather_export` only runs SELECTs.

Determinism is a contract (T1): `render_export` is PURE, no I/O, no clock,
and the same `ExportData` always renders byte-identical. The header's
"as of" line is the max `change_log` timestamp, never the wall clock.
Section order is fixed: header, items, links, sources, ledger. Items are
in id order, links in id order, sources in id order, ledger in
`(timestamp, id)` order. Every column of every row is exported, removed
and reversed links carry their state, ledger values are never truncated.
`item_embeddings` and `ai_responses` are deliberately excluded: derived,
rebuildable data (D2), declared in the header.

Source text marker design (D1, verbatim): each source's `full_text` is
written raw between two marker lines. The end marker names the source id,
the exact UTF-8 byte count, and the sha256 of those bytes:

    ----- source 4 text begin -----
    (verbatim text, leading whitespace and non-ASCII preserved)
    ----- source 4 text end (bytes=512, sha256=<64 hex chars>) -----

A bare line like `----- source 4 text end -----` inside the text can
NEVER close the block: only the real id plus byte count plus digest
matches, and a source cannot carry its own digest without inverting
SHA-256. Another source's end line fails the id check. The raw bytes are
written exactly as stored, with exactly one newline added before the end
marker when the text does not end with one, so the marker always starts
its own line. Each source is timestamped in its header (the
grieving-reader check).

Markdown rule for this file: plain `---` lines would be ambiguous next to
the markers, so sections start with `== name (count) ==` lines and the
header lines start with `# `, matching the L2 §4 samples.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3

from pydantic import BaseModel

from ember.adapters.errors import OverwriteRefused, OutputWriteFailed
from ember.adapters.paths import same_path
from ember.query.rows import ChangeRow
from ember.relate.rows import Link

_NULL = "(null)"
_VALUE_COLUMN = 20  # every aligned field line puts its value at this column


class ExportItem(BaseModel):
    """One `items` row: every column, in the export field order."""

    id: int
    type: str
    statement: str
    status: str
    status_origin: str
    created_at: str
    validated: int | None
    close_reason: str | None
    metadata: str | None
    rationale: str | None
    source: str | None
    source_id: int


class ExportSource(BaseModel):
    """One `sources` row: every column, raw `full_text` included (D1)."""

    id: int
    timestamp: str
    title: str
    content_hash: str
    full_text: str


class ExportData(BaseModel):
    """The gathered snapshot render_export consumes (I4, named not a tuple).

    Rows arrive in the fixed gather order: items by id, links by id,
    sources by id, ledger by `(timestamp, id)`. Render trusts that order.
    """

    schema_version: int
    items: list[ExportItem]
    links: list[Link]
    sources: list[ExportSource]
    ledger: list[ChangeRow]


def gather_export(conn: sqlite3.Connection) -> ExportData:
    """Phase 1. Read the whole store in fixed order into an ExportData.

    Input: a read-only connection opened by the CLI through
    `open_query_database` (floors QUERY-003/004 already enforced, never
    migrated). Output: an `ExportData` with the schema version, items,
    links, sources and the full ledger. Side effects: none, SELECT only
    (`item_embeddings` and `ai_responses` are never read, D2). Raised
    codes: none of its own. An unexpected read failure propagates (I7,
    fail fast, no swallowed errors).
    """
    version = int(conn.execute("SELECT version FROM schema_version").fetchone()["version"])
    items = [
        ExportItem(
            id=row["id"],
            type=row["type"],
            statement=row["statement"],
            status=row["status"],
            status_origin=row["status_origin"],
            created_at=row["created_at"],
            validated=row["validated"],
            close_reason=row["close_reason"],
            metadata=row["metadata"],
            rationale=row["rationale"],
            source=row["source"],
            source_id=row["source_id"],
        )
        for row in conn.execute(
            "SELECT id, type, statement, source_id, status, created_at,"
            " validated, rationale, source, close_reason, status_origin,"
            " metadata FROM items ORDER BY id"
        )
    ]
    links = [
        Link(
            id=row["id"],
            source_item_id=row["source_item_id"],
            target_item_id=row["target_item_id"],
            link_type=row["link_type"],
            status=row["status"],
            created_at=row["created_at"],
            reversed_at=row["reversed_at"],
        )
        for row in conn.execute(
            "SELECT id, source_item_id, target_item_id, link_type, status,"
            " created_at, reversed_at FROM links ORDER BY id"
        )
    ]
    sources = [
        ExportSource(
            id=row["id"],
            timestamp=row["timestamp"],
            title=row["title"],
            content_hash=row["content_hash"],
            full_text=row["full_text"],
        )
        for row in conn.execute(
            "SELECT id, timestamp, title, content_hash, full_text"
            " FROM sources ORDER BY id"
        )
    ]
    ledger = [
        ChangeRow(
            id=row["id"],
            item_id=row["item_id"],
            link_id=row["link_id"],
            field_changed=row["field_changed"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            timestamp=row["timestamp"],
            trigger_cause=row["trigger_cause"],
        )
        for row in conn.execute(
            "SELECT id, item_id, link_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause FROM change_log"
            " ORDER BY timestamp, id"
        )
    ]
    return ExportData(
        schema_version=version, items=items, links=links,
        sources=sources, ledger=ledger,
    )


def render_export(data: ExportData) -> str:
    """Phase 2. Render ExportData as deterministic human-readable text.

    Input: one `ExportData`. Output: a UTF-8 `str` ending in one newline.
    PURE: no I/O, no clock, no click (T1). Two calls with equal input are
    byte-identical, so two exports of one database are byte-identical.
    Raised codes: none.
    """
    lines: list[str] = []
    lines += _header_lines(data)
    lines += _items_lines(data.items)
    lines += _links_lines(data.links)
    lines += _sources_lines(data.sources)
    lines += _ledger_lines(data.ledger)
    return "\n".join(lines) + "\n"


def refuse_self_overwrite(db_path: str, out_path: str) -> None:
    """Guard BEFORE any open-for-write: `--out` must not be the live DB.

    `open(path, "w")` truncates before anything else runs, so a plain
    overwrite of the knowledge base would erase live knowledge with a
    normal exit (the severe panel finding, L2 §5.2). The guard refuses
    when both paths name one file: `os.path.samefile` where both exist,
    resolved absolute paths otherwise. Side effects: none, the check never
    touches either file. Raised codes: EXPORT-002 OverwriteRefused.
    """
    if same_path(db_path, out_path):
        raise OverwriteRefused(
            "output path is the knowledge base file",
            db_path=db_path,
            out=out_path,
        )


def write_export(text: str, out_path: str) -> None:
    """Phase 3. Write the rendered text to `out_path` as UTF-8.

    Input: the rendered text and a validated output path (guard already
    run). Output: none. Side effects: creates or overwrites `out_path`
    with the exact text, LF endings verbatim (`newline=""`, a text-file
    transfer, S4). Raised codes: EXPORT-001 OutputWriteFailed when the
    file cannot be written.
    """
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as exc:
        raise OutputWriteFailed("output write failed", out=out_path) from exc


def _header_lines(data: ExportData) -> list[str]:
    """The pinned five header lines. "as of" = max ledger timestamp."""
    newest = max((row.timestamp for row in data.ledger), default=None)
    lines = [
        "# Ember knowledge base export",
        f"# schema version: {data.schema_version}",
        (
            "# as of (latest ledger event):"
            f" {newest if newest is not None else '(no ledger rows)'}"
        ),
        (
            f"# counts: {len(data.items)} items, {len(data.links)} links,"
            f" {len(data.ledger)} ledger rows, {len(data.sources)} sources"
        ),
        (
            "# embeddings and AI responses are derived, rebuildable data"
            " (D2) and are not exported."
        ),
    ]
    return lines


def _items_lines(items: list[ExportItem]) -> list[str]:
    """The items section: one block per row, in the given (id) order."""
    lines = ["", f"== items ({len(items)}) =="]
    for item in items:
        header = f"{item.type} {item.id} | {item.status}"
        if item.status == "Closed" and item.close_reason is not None:
            header += f" ({item.close_reason})"
        lines.append(header)
        lines += _field_lines("statement", item.statement)
        lines += _field_lines("status_origin", item.status_origin)
        lines += _field_lines("created_at", item.created_at)
        lines += _field_lines("validated", item.validated)
        lines += _field_lines("close_reason", item.close_reason)
        lines += _field_lines("metadata", item.metadata)
        lines += _field_lines("rationale", item.rationale)
        lines += _field_lines("source", item.source)
        lines += _field_lines("source_id", item.source_id)
        lines.append("")
    return lines


def _links_lines(links: list[Link]) -> list[str]:
    """The links section: kept, removed and reversed rows all render."""
    lines = ["", f"== links ({len(links)}) =="]
    for link in links:
        header = f"link {link.id} | {link.link_type} | {link.status}"
        if link.status == "Rejected":
            header += " (removed)"
        if link.reversed_at is not None:
            header += " (reversed)"
        lines.append(header)
        lines += _field_lines("source_item_id", link.source_item_id)
        lines += _field_lines("target_item_id", link.target_item_id)
        lines += _field_lines("status", link.status)
        lines += _field_lines("created_at", link.created_at)
        lines += _field_lines("reversed_at", link.reversed_at)
        lines.append("")
    return lines


def _sources_lines(sources: list[ExportSource]) -> list[str]:
    """The sources section: header, hash, then the raw text between markers."""
    lines = ["", f"== sources ({len(sources)}) =="]
    for source in sources:
        lines.append(f"source {source.id} | {source.title} | {source.timestamp}")
        lines += _field_lines("content_hash", source.content_hash)
        lines += _source_text_lines(source)
        lines.append("")
    return lines


def _source_text_lines(source: ExportSource) -> list[str]:
    """The verbatim D1 block: raw text between pinned begin and end markers.

    The end marker carries the byte count and sha256 of the raw UTF-8
    bytes (module docstring: why no source can carry its own end marker).
    The raw bytes are written exactly as stored, and exactly one newline
    is added before the end marker when the text does not end with one,
    so the marker always starts its own line. The declared byte count and
    digest make the original recoverable from the file: the reader trims
    the final newline only when the remaining length matches `bytes=`.
    Leading whitespace, blank lines and non-ASCII pass through untouched.
    """
    raw = source.full_text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    block = f"----- source {source.id} text begin -----\n{source.full_text}"
    if not source.full_text.endswith("\n"):
        block += "\n"
    block += (
        f"----- source {source.id} text end"
        f" (bytes={len(raw)}, sha256={digest}) -----"
    )
    return [block]


def _ledger_lines(ledger: list[ChangeRow]) -> list[str]:
    """The ledger section: full values, never truncated, `(timestamp, id)`."""
    lines = ["", f"== ledger ({len(ledger)}) =="]
    for row in ledger:
        lines.append(f"ledger {row.id} | {row.timestamp} | {row.trigger_cause}")
        lines += _field_lines("timestamp", row.timestamp)
        lines += _field_lines("trigger_cause", row.trigger_cause)
        lines += _field_lines("item_id", row.item_id)
        lines += _field_lines("link_id", row.link_id)
        lines += _field_lines("field_changed", row.field_changed)
        lines += _field_lines("old_value", row.old_value)
        lines += _field_lines("new_value", row.new_value)
        lines.append("")
    return lines


def _field_lines(label: str, value: object) -> list[str]:
    """One `  label: value` line, value at a fixed column 20, multi-line kind.

    A value with newlines stays one logical field: the first line sits on
    the label line, the rest continue under it, aligned to the same value
    column. NULL is the literal `(null)`. Line values are never cut.
    """
    text = _NULL if value is None else str(value)
    prefix = f"  {label}:{' ' * (_VALUE_COLUMN - len(label) - 1)}"
    parts = text.split("\n")
    lines = [prefix + parts[0]]
    lines.extend(" " * (_VALUE_COLUMN + 2) + part for part in parts[1:])
    return lines

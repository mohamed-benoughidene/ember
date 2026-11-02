"""Phase 4 core: confirm each validated item, then write it.

Pure logic. The prompts and the writes sit behind ports, so tests drive the
loop with fakes and the engine core never touches a terminal or a database.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from ember.capture.errors import TextNotEncodable, UserAbort
from ember.capture.item_gatekeeper import (
    NearDupWarning,
    ProposalDraft,
    ValidatedItem,
    is_allowed_type,
)
from ember.capture.item_proposal import ItemType

PROMPT = "[y]es / [n]o / [e]dit / [q]uit"
ASSUMPTION = ItemType.ASSUMPTION.value


class Choice(str, Enum):
    """One understood answer to the confirm prompt."""

    YES = "yes"
    NO = "no"
    EDIT = "edit"
    QUIT = "quit"


_CHOICES = {
    "y": Choice.YES,
    "yes": Choice.YES,
    "n": Choice.NO,
    "no": Choice.NO,
    "e": Choice.EDIT,
    "edit": Choice.EDIT,
    "q": Choice.QUIT,
    "quit": Choice.QUIT,
}


class ConfirmPort(Protocol):
    """User I/O boundary for the confirm loop."""

    def ask(self, prompt: str) -> str:
        """Show `prompt`, return the raw answer.

        The edge raises `UserAbort` (CAPTURE-014) when input ends (STDIN closed).
        """
        ...

    def write(self, text: str) -> None:
        """Show one line to the user."""
        ...


class ItemCommitPort(Protocol):
    """Gatekeeper commit boundary: every `items` and `change_log` write."""

    def insert_item(self, item: ValidatedItem, *, validated: bool | None) -> int | None:
        """Insert one accepted item with the Phase 3 id, timestamp and status.

        Return the id the row actually carries, or None when the commit does
        not track it (fakes). Chunk 14 (N10): on a unique-key conflict on
        `items.id` the store re-allocates the next free id inside the write
        transaction and returns THAT id — the ledger row and the reported
        id must follow the returned value, not the pre-write `item.id`.
        """
        ...

    def log_created(self, item: ValidatedItem) -> None:
        """Append the `change_log` row for an accepted item."""
        ...

    def log_rejected(self, item: ValidatedItem) -> None:
        """Append the `change_log` row for a rejected item."""
        ...


@dataclass(frozen=True)
class ConfirmResult:
    """Phase 4 output (L3 step 3, section 3)."""

    accepted_ids: list[int]
    rejected_count: int
    warning_count: int
    aborted: bool


def parse_choice(raw: str) -> Choice | None:
    """Read one answer. Unknown input returns None so the caller re-prompts."""
    return _CHOICES.get(raw.strip().lower())


def format_block(item: ValidatedItem) -> str:
    """The YAML block printed before the prompt (L3 step 3, section 4.2)."""
    return "\n".join(
        [
            f"- id: {item.id}",
            f"  type: {json.dumps(item.type)}",
            f"  statement: {json.dumps(item.statement, ensure_ascii=False)}",
            f"  source_quote: {json.dumps(item.source_quote, ensure_ascii=False)}",
            f"  confidence: {item.confidence}",
            f"  metadata: {json.dumps(item.metadata, ensure_ascii=False)}",
            f"  near_dup_warning: {_warning_text(item.near_dup_warning)}",
        ]
    )


def run_confirm_loop(
    items: list[ValidatedItem],
    *,
    confirm: ConfirmPort,
    commit: ItemCommitPort,
    revalidate: Callable[[ProposalDraft], ValidatedItem],
    unit_of_work: Callable[[], AbstractContextManager[None]] | None = None,
) -> ConfirmResult:
    """Prompt for every item until it is handled or the user quits.

    `revalidate` re-runs the Phase 3 gatekeeper for an edited draft, with a new
    timestamp and the draft's OWN id — an edit never takes a new item id
    (L3 step 3, section 4.2 `e`; chunk 14, N10 / story 33). An edit is never
    dropped (finding 4.5 #14, story 34): the loop's `revalidate` returns a
    `ValidatedItem`, because every draft an edit can produce already passes —
    `ask_type` and `ask_statement` loop until valid, and the quote is the
    item's own already-checked quote. On `q` or end of
    input the loop stops and the result carries `aborted=True`; leftover items
    are neither written nor logged. `unit_of_work` (Batch 4 chunk 8, an adapter
    factory over the write connection) makes each accepted item ONE
    transaction — the item row and its `created` ledger row all-or-nothing
    (4.3 #9); `None` keeps the accept path's per-store-commit behaviour (unit
    tests with fakes).
    """
    accepted: list[int] = []
    pending = list(items)
    rejected_count = 0
    warning_count = 0
    warned_ids: set[int] = set()
    index = 0
    try:
        while index < len(pending):
            item = pending[index]
            confirm.write(format_block(item))
            if item.near_dup_warning is not None:
                # One edit re-shows the same warning (finding 4.5 #12): an
                # item keeps its id across the edit, so count each item's
                # warning once, however often it is presented.
                if item.id not in warned_ids:
                    warned_ids.add(item.id)
                    warning_count += 1
                warning = item.near_dup_warning
                confirm.write(
                    f"warning: near-duplicate of item {warning.matching_item_id}"
                    f" (similarity {warning.similarity:.2f})"
                )
            while True:
                choice = parse_choice(confirm.ask(PROMPT))
                if choice is not None:
                    break
            if choice is Choice.YES:
                accept(
                    item,
                    commit=commit,
                    accepted=accepted,
                    unit_of_work=unit_of_work,
                )
                index += 1
            elif choice is Choice.NO:
                commit.log_rejected(item)
                rejected_count += 1
                index += 1
            elif choice is Choice.EDIT:
                pending[index] = edit_item(
                    item, confirm=confirm, revalidate=revalidate
                )
            else:
                return ConfirmResult(accepted, rejected_count, warning_count, True)
    except UserAbort:
        return ConfirmResult(accepted, rejected_count, warning_count, True)
    return ConfirmResult(accepted, rejected_count, warning_count, False)


def accept(
    item: ValidatedItem,
    *,
    commit: ItemCommitPort,
    accepted: list[int],
    unit_of_work: Callable[[], AbstractContextManager[None]] | None = None,
) -> None:
    """Write one accepted item and its `change_log` row as ONE write.

    `validated` is set only on Assumption rows (spec 3.5). A fresh assumption
    starts unvalidated, so its value is False; the other 3 types get null.
    The commit returns the id the row actually carries (chunk 14, N10): on an
    id conflict the store re-allocates the next free id inside the lock, and
    the ledger row plus the reported id follow the RETURNED id — the id shown
    in the confirm block is re-read and only the genuinely saved one is
    reported. `unit_of_work` (Batch 4 chunk 8) wraps the pair in ONE
    transaction, so a failed ledger row cannot leave the item row behind
    (4.3 #9); `None` keeps the pre-chunk per-store-commit behaviour (unit
    tests with fakes).
    """
    validated = False if item.type == ASSUMPTION else None
    if unit_of_work is None:
        item = _with_saved_id(commit.insert_item(item, validated=validated), item)
        commit.log_created(item)
    else:
        with unit_of_work():
            item = _with_saved_id(
                commit.insert_item(item, validated=validated), item
            )
            commit.log_created(item)
    accepted.append(item.id)


def _with_saved_id(saved_id: int | None, item: ValidatedItem) -> ValidatedItem:
    """Make the item's id honest with what the store actually wrote.

    The store returns the inserted id (chunk 14, N10): unchanged on a normal
    insert, the next free id after a conflict retry. On `None` (fakes that
    do not track the id) the item keeps its own.
    """
    if saved_id is None or saved_id == item.id:
        return item
    return replace(item, id=saved_id)


def _check_encodable(text: str, *, item_id: int, field: str) -> None:
    """Refuse an accepted e-answered text that cannot be written as UTF-8.

    A lone surrogate (`"\\ud800"`) arrives through a JSON answer line (a
    `\\ud800` escape survives `json.loads`) and would kill the write/echo
    path later with a raw `UnicodeEncodeError`. Checking here, at the point
    the answer is accepted, covers both confirm surfaces (terminal and
    `--confirm json`, which feed the same loop) and happens before any
    write: no item row, no `change_log` row (plan Chunk 10, decision I1).
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TextNotEncodable(
            "text cannot be written as UTF-8", item=item_id, field=field
        ) from exc


def edit_item(
    item: ValidatedItem,
    *,
    confirm: ConfirmPort,
    revalidate: Callable[[ProposalDraft], ValidatedItem],
) -> ValidatedItem:
    """Ask for a new type and statement, then re-validate the edit.

    The edit is never dropped (finding 4.5 #14, story 34): the loop's
    `revalidate` returns a `ValidatedItem` — every draft an edit can produce
    already passes the Phase 3 checks, so there is no drop branch and no
    `dropped proposal` line on this path.
    """
    new_type = ask_type(confirm, default=item.type)
    _check_encodable(new_type, item_id=item.id, field="type")
    new_statement = ask_statement(confirm, default=item.statement)
    _check_encodable(new_statement, item_id=item.id, field="statement")
    new_metadata = ask_metadata(confirm, default=item.metadata)
    if new_metadata is not None:
        _check_encodable(new_metadata, item_id=item.id, field="metadata")
    draft = ProposalDraft(
        type=new_type,
        statement=new_statement,
        metadata=new_metadata,
        source_quote=item.source_quote,
        confidence=item.confidence,
    )
    outcome = revalidate(draft)
    # Chunk 14 (N10 / story 33): an edit revalidates but never takes a new
    # item id — the edited draft stays the item the confirm block already
    # showed, so `MAX(id)` never moves for an edit.
    return replace(outcome, id=item.id)


def ask_type(confirm: ConfirmPort, *, default: str) -> str:
    """Re-prompt until the type is one of the 4 allowed types."""
    while True:
        raw = confirm.ask(f"new type? (default {default})").strip()
        value = raw or default
        if is_allowed_type(value):
            return value
        confirm.write("invalid type")


def ask_statement(confirm: ConfirmPort, *, default: str) -> str:
    """Re-prompt until the statement is non-empty."""
    while True:
        raw = confirm.ask(f"new statement? (default {default})").strip()
        value = raw or default
        if value:
            return value
        confirm.write("statement is empty")


def ask_metadata(confirm: ConfirmPort, *, default: str | None) -> str | None:
    """Ask once for the label. Blank keeps the default, a lone `-` clears.

    Every answer is valid, so there is no retry loop.
    """
    shown = default if default is not None else "none"
    raw = confirm.ask(f"new metadata? (default {shown})").strip()
    if raw == "-":
        return None
    return raw or default


def _warning_text(warning: NearDupWarning | None) -> str:
    if warning is None:
        return "null"
    return (
        "{matching_item_id: "
        f"{warning.matching_item_id}, similarity: {warning.similarity:.2f}}}"
    )

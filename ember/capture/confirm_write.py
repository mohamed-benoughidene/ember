"""Phase 4 core: confirm each validated item, then write it.

Pure logic. The prompts and the writes sit behind ports, so tests drive the
loop with fakes and the engine core never touches a terminal or a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from ember.capture.errors import UserAbort
from ember.capture.item_gatekeeper import (
    NearDupWarning,
    ProposalDraft,
    RejectedProposal,
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

    def insert_item(self, item: ValidatedItem, *, validated: bool | None) -> None:
        """Insert one accepted item with the Phase 3 id, timestamp and status."""
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
    revalidate: Callable[[ProposalDraft], ValidatedItem | RejectedProposal],
) -> ConfirmResult:
    """Prompt for every item until it is handled or the user quits.

    `revalidate` re-runs the Phase 3 gatekeeper for an edited draft, with a new
    id and timestamp (L3 step 3, section 4.2 `e`). On `q` or end of input the
    loop stops and the result carries `aborted=True`; leftover items are neither
    written nor logged.
    """
    accepted: list[int] = []
    pending = list(items)
    rejected_count = 0
    warning_count = 0
    index = 0
    try:
        while index < len(pending):
            item = pending[index]
            confirm.write(format_block(item))
            if item.near_dup_warning is not None:
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
                accept(item, commit=commit, accepted=accepted)
                index += 1
            elif choice is Choice.NO:
                commit.log_rejected(item)
                rejected_count += 1
                index += 1
            elif choice is Choice.EDIT:
                edited = edit_item(item, confirm=confirm, revalidate=revalidate)
                if edited is not None:
                    pending[index] = edited
                else:
                    index += 1
            else:
                return ConfirmResult(accepted, rejected_count, warning_count, True)
    except UserAbort:
        return ConfirmResult(accepted, rejected_count, warning_count, True)
    return ConfirmResult(accepted, rejected_count, warning_count, False)


def accept(item: ValidatedItem, *, commit: ItemCommitPort, accepted: list[int]) -> None:
    """Write one accepted item and its `change_log` row.

    `validated` is set only on Assumption rows (spec 3.5). A fresh assumption
    starts unvalidated, so its value is False; the other 3 types get null.
    """
    validated = False if item.type == ASSUMPTION else None
    commit.insert_item(item, validated=validated)
    commit.log_created(item)
    accepted.append(item.id)


def edit_item(
    item: ValidatedItem,
    *,
    confirm: ConfirmPort,
    revalidate: Callable[[ProposalDraft], ValidatedItem | RejectedProposal],
) -> ValidatedItem | None:
    """Ask for a new type and statement, then re-validate the edit.

    Returns None when the gatekeeper throws the edit away, so the loop moves on
    (same as a Phase 3 drop: no item row, no `change_log`).
    """
    draft = ProposalDraft(
        type=ask_type(confirm, default=item.type),
        statement=ask_statement(confirm, default=item.statement),
        metadata=ask_metadata(confirm, default=item.metadata),
        source_quote=item.source_quote,
        confidence=item.confidence,
    )
    outcome = revalidate(draft)
    if isinstance(outcome, RejectedProposal):
        confirm.write(f"dropped proposal: {outcome.rule}")
        return None
    return outcome


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

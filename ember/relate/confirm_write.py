"""Phase 4 core: the y/n/s/q confirm loop and the atomic link write.

Pure logic. The prompts, the writes and the storage calls sit behind ports, so
tests drive the loop with fakes and the engine core never touches a terminal or
a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from ember.relate.errors import UserAbort
from ember.relate.link_gatekeeper import RejectedLink, ValidatedLink
from ember.relate.rows import ChangeLogEntry, Link

PROMPT = "[y]es / [n]o / [s]kip / [q]uit"

REJECTED_STATUS = "Rejected"
REJECTED_FIELD_CHANGED = "link_rejected"
REJECTED_TRIGGER_CAUSE = "rejected"


class Choice(str, Enum):
    """One understood answer to the confirm prompt."""

    YES = "yes"
    NO = "no"
    SKIP = "skip"
    QUIT = "quit"


_CHOICES = {
    "y": Choice.YES,
    "yes": Choice.YES,
    "n": Choice.NO,
    "no": Choice.NO,
    "s": Choice.SKIP,
    "skip": Choice.SKIP,
    "q": Choice.QUIT,
    "quit": Choice.QUIT,
}


class ConfirmPort(Protocol):
    """User I/O boundary for the confirm loop."""

    def ask(self, prompt: str) -> str:
        """Show `prompt`, return the raw answer.

        The edge raises `UserAbort` (RELATE-031) when input ends (STDIN closed).
        """
        ...

    def write(self, text: str) -> None:
        """Show one line to the user."""
        ...


class LinkStorePort(Protocol):
    """Storage boundary: one atomic `links` + `change_log` write."""

    def insert_link_with_log(
        self, link_row: Link, change_log_row: ChangeLogEntry
    ) -> int:
        """Insert one link and its `change_log` row in one transaction.

        Returns the new link id.
        """
        ...


@dataclass(frozen=True)
class ConfirmResult:
    """Phase 4 output: what the user accepted, rejected or skipped.

    `gatekeeper_rejections` carries the rule-failure `RejectedLink`s (code and
    detail) so the CLI can print one line per rejection. The `rejected` count
    includes them plus the user's explicit `no` answers.
    """

    accepted: list[int]
    rejected: int
    skipped: int
    aborted: bool
    gatekeeper_rejections: list[RejectedLink] = field(default_factory=list)


def parse_choice(raw: str) -> Choice | None:
    """Read one answer. Unknown input returns None so the caller re-prompts."""
    return _CHOICES.get(raw.strip().lower())


def format_link_block(validated: ValidatedLink) -> str:
    """The YAML block printed after an accepted link is written."""
    link = validated.link_row
    return "\n".join(
        [
            f"- link_id: {link.id}",
            f"  source_item_id: {link.source_item_id}",
            f"  target_item_id: {link.target_item_id}",
            f"  link_type: {json.dumps(link.link_type, ensure_ascii=False)}",
            f"  status: {json.dumps(link.status, ensure_ascii=False)}",
            f"  rationale: {json.dumps(validated.rationale, ensure_ascii=False)}",
        ]
    )


def confirm_links(
    links: list[ValidatedLink],
    *,
    store: LinkStorePort,
    confirm: ConfirmPort,
) -> ConfirmResult:
    """Prompt for every link, then write it, reject it or skip it.

    A `q` answer or the end of input stops the loop and returns `aborted=True`;
    the leftover links are neither written nor logged.
    """
    accepted: list[int] = []
    rejected = 0
    skipped = 0
    try:
        for index, link in enumerate(links, start=1):
            confirm.write(_preview_line(index, len(links), link))
            choice = parse_choice(confirm.ask(PROMPT))
            while choice is None:
                choice = parse_choice(confirm.ask(PROMPT))
            if choice is Choice.YES:
                link_id = store.insert_link_with_log(
                    link.link_row, link.change_log_row
                )
                stored = ValidatedLink(
                    link_row=link.link_row.model_copy(update={"id": link_id}),
                    change_log_row=link.change_log_row,
                    rationale=link.rationale,
                )
                confirm.write(format_link_block(stored))
                accepted.append(link_id)
            elif choice is Choice.NO:
                store.insert_link_with_log(
                    link.link_row.model_copy(update={"status": REJECTED_STATUS}),
                    link.change_log_row.model_copy(
                        update={
                            "field_changed": REJECTED_FIELD_CHANGED,
                            "trigger_cause": REJECTED_TRIGGER_CAUSE,
                        }
                    ),
                )
                rejected += 1
            elif choice is Choice.SKIP:
                skipped += 1
            else:
                return ConfirmResult(accepted, rejected, skipped, True)
    except UserAbort:
        return ConfirmResult(accepted, rejected, skipped, True)
    return ConfirmResult(accepted, rejected, skipped, False)


def _preview_line(index: int, total: int, link: ValidatedLink) -> str:
    """The non-YAML preview written before each prompt.

    It deliberately never contains the text `link_id:`, so the CLI block count
    stays correct.
    """
    row = link.link_row
    return (
        f"Proposal {index}/{total}: item {row.source_item_id} "
        f"-> item {row.target_item_id} [{row.link_type}]\n"
        f"  rationale: {link.rationale or '-'}"
    )

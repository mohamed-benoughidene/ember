"""The forget-source rule (Batch 6, D-07 / D-26): validation only.

Pure decision, no SQL: given whether a raw note (a `sources` row) exists
and how many items cite it, the rule either refuses (a note WITH items is
real knowledge and is never forgotten), or answers "nothing to do"
(a missing id is already gone — delete-nothing is success, I8), or names
the ONE write the store must perform: delete the source and its raw AI
answers, append one textless ledger line (D-26). The transaction itself
lives on the adapters side (`ember/adapters/sqlite.py`,
`SqliteForgetSourceStore`), opened by the command in one `unit_of_work`
per Batch 4's one-transaction pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

from ember.capture.errors import CaptureError

# The writer's encoding of the forget on the ledger (D-26): ONE row,
# `item_id` and `link_id` NULL, no old/new text, `source_id` naming the
# forgotten note (migration 014), `group_id` NULL so undo never sees it.
FORGOTTEN_FIELD = "source_forgotten"
FORGOTTEN_CAUSE = "user_forget_source"


class SourceHasItems(CaptureError):
    """`ember forget-source` on a raw note that still has items (D-07).

    A note whose capture produced items carries real knowledge; forgetting
    it would delete what the ledger and the items still stand on. Only a
    note that produced NOTHING (zero items, any status) may be forgotten.
    """

    code = "CAPTURE-023"
    name = "SourceHasItems"


@dataclass(frozen=True)
class ForgetPlan:
    """What the one forget-source transaction must do for one source id."""

    source_id: int
    # False: the id names no source row any more. Nothing may be written —
    # not even a ledger row (I8: delete-missing is success, not history).
    existed: bool


def plan_forget_source(
    *, source_id: int, source_exists: bool, item_count: int
) -> ForgetPlan:
    """Return the write plan for one forget-source request.

    - A missing id answers `existed=False` (I8: nothing to do, exit 0).
    - A note with items refuses with `SourceHasItems` (CAPTURE-023) before
      anything is opened for writing.
    - Anything else answers `existed=True`: the store may run its ONE
      transaction (deletions + the one textless ledger line).
    """
    if not source_exists:
        return ForgetPlan(source_id=source_id, existed=False)
    if item_count > 0:
        raise SourceHasItems(
            "forget-source: the note still has items",
            source_id=source_id,
            item_count=item_count,
        )
    return ForgetPlan(source_id=source_id, existed=True)

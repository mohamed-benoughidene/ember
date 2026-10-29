"""Phase 4 core: the pure 9-rule gatekeeper for one proposed link.

The nine checks run in a fixed order and stop at the first failure (rule 5,
the premise rule, intentionally runs BEFORE rule 6, the compatibility rule:
the L2 compat table already makes Assumption -> supports unreachable, so a
distinct RELATE-008 code can only survive if the premise check fires first).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from ember.relate.compat import LINK_TYPES, allowed_link_types
from ember.relate.errors import (
    DuplicateLink,
    LinkTypeNotInClosedSet,
    PremiseRuleViolated,
    SelfLink,
    SourceItemNotFound,
    SourceTargetTypeIncompatible,
    SupersedesCycle,
    SupersedesTargetClosed,
    TargetItemNotFound,
)
from ember.relate.link_lookup import LinkLookupPort
from ember.relate.rows import ChangeLogEntry, Link

SUPERSEDES = "supersedes"
ASSUMPTION = "Assumption"
SUPPORTS = "supports"
CLOSED = "Closed"
CONFIRMED = "Confirmed"


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LinkDraft:
    source_item_id: int
    target_item_id: int
    link_type: str
    rationale: str | None = None


@dataclass(frozen=True)
class ValidatedLink:
    link_row: Link
    change_log_row: ChangeLogEntry
    rationale: str | None = None


@dataclass(frozen=True)
class RejectedLink:
    code: str
    # Human-readable cause for rules 8/9 (which link blocked, its reversal
    # state). None for every other rejection. Data only, never a decision.
    detail: str | None = None


def validate_add_link(
    draft: LinkDraft,
    lookup: LinkLookupPort,
    *,
    clock: Callable[[], str] = _utc_now,
) -> ValidatedLink | RejectedLink:
    """Run the 9 rules in order; build a ValidatedLink or a RejectedLink."""
    source = draft.source_item_id
    target = draft.target_item_id

    # 1. Source must exist.
    if not lookup.item_exists(source):
        return RejectedLink(code=SourceItemNotFound.code)

    # 2. Target must exist.
    if not lookup.item_exists(target):
        return RejectedLink(code=TargetItemNotFound.code)

    # 3. No self-links.
    if source == target:
        return RejectedLink(code=SelfLink.code)

    # 4. Link type must be in the closed set.
    if draft.link_type not in LINK_TYPES:
        return RejectedLink(code=LinkTypeNotInClosedSet.code)

    source_type = lookup.item_type(source)
    target_type = lookup.item_type(target)

    # Defensive narrowing only. Rules 1-2 already proved both items exist, so a
    # conforming port never returns None here; this keeps the types honest.
    if source_type is None:
        return RejectedLink(code=SourceItemNotFound.code)
    if target_type is None:
        return RejectedLink(code=TargetItemNotFound.code)

    # 5. Premise rule (intentionally before compat; see module docstring).
    if source_type == ASSUMPTION and draft.link_type == SUPPORTS:
        return RejectedLink(code=PremiseRuleViolated.code)

    # 6. Source/target type compatibility.
    if draft.link_type not in allowed_link_types(source_type, target_type):
        return RejectedLink(code=SourceTargetTypeIncompatible.code)

    # 7. Cannot supersede a Closed target.
    if draft.link_type == SUPERSEDES and lookup.item_status(target) == CLOSED:
        return RejectedLink(code=SupersedesTargetClosed.code)

    # 8. No supersedes cycle in either direction.
    if source in lookup.supersedes_ancestors(target) or target in lookup.supersedes_ancestors(
        source
    ):
        blocker = lookup.supersedes_blocking_link(source, target)
        detail = None
        if blocker is not None:
            detail = (
                f"blocked by link {blocker.id} "
                f"({blocker.source_item_id} -> {blocker.target_item_id})"
            )
        return RejectedLink(code=SupersedesCycle.code, detail=detail)

    # 9. No duplicate link.
    duplicate = lookup.find_existing(source, target, draft.link_type)
    if duplicate is not None:
        detail = f"link {duplicate.id} exists"
        if duplicate.reversed_at is not None:
            detail += " (reversed)"
        return RejectedLink(code=DuplicateLink.code, detail=detail)

    now = clock()
    new_value = f"{draft.link_type}:{draft.target_item_id}"
    link_row = Link(
        id=None,
        source_item_id=draft.source_item_id,
        target_item_id=draft.target_item_id,
        link_type=draft.link_type,
        status=CONFIRMED,
        created_at=now,
    )
    change_log_row = ChangeLogEntry(
        id=None,
        item_id=draft.source_item_id,
        link_id=None,
        field_changed="link_confirmed",
        old_value=None,
        new_value=new_value,
        timestamp=now,
        trigger_cause="user_confirmed",
    )
    return ValidatedLink(
        link_row=link_row,
        change_log_row=change_log_row,
        rationale=draft.rationale,
    )

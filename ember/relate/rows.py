"""Row models shared by the relate core and the storage layer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class SignalKind(str, Enum):
    dense = "dense"
    graph = "graph"
    metadata = "metadata"


class NewItem(BaseModel):
    id: int
    type: str
    statement: str
    created_at: str
    # Project label from `items.metadata` (ticket 11, step 05b). None means
    # unlabeled; read-only here, capture is the only writer.
    metadata: str | None = None


class CandidateUniverse(BaseModel):
    items: list[NewItem]


class Link(BaseModel):
    id: int | None = None
    source_item_id: int
    target_item_id: int
    link_type: str
    status: str
    created_at: str
    # Reversal timestamp from the paired maintain write (L2 hardening §6/§9).
    # NULL means the row is live and readers (rules 8/9) walk it.
    reversed_at: str | None = None


class ChangeLogEntry(BaseModel):
    """One append-only `change_log` row (L2 §4 Phase 4)."""

    id: int | None = None
    item_id: int
    link_id: int | None = None
    field_changed: str
    old_value: str | None = None
    new_value: str | None = None
    timestamp: str
    trigger_cause: str


class RankedCandidate(BaseModel):
    item: NewItem
    cosine: float | None
    source: SignalKind


class Pool(BaseModel):
    ranked: list[RankedCandidate]
    counts: dict[str, int]
    warning: str | None = None

    @classmethod
    def empty(cls, *, warning: str | None = None) -> "Pool":
        """Return an empty pool with zero signal counts."""
        return cls(
            ranked=[],
            counts={"dense": 0, "graph": 0, "metadata": 0},
            warning=warning,
        )

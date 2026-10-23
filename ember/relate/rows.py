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


class CandidateUniverse(BaseModel):
    items: list[NewItem]


class Link(BaseModel):
    id: int
    source_item_id: int
    target_item_id: int
    link_type: str
    status: str
    created_at: str


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

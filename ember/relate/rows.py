"""Row models shared by the relate core and the storage layer."""

from __future__ import annotations

from pydantic import BaseModel


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

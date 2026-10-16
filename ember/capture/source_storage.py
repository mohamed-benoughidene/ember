"""Phase 1 core: read raw input, dedup by content hash, return source id.

Pure logic. Takes a `SourceStorePort` so tests use a fake and the engine core
never imports a database driver.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

TITLE_LENGTH = 80


@dataclass(frozen=True)
class SourceRecord:
    """An existing row in the `sources` table."""

    id: int
    full_text: str
    content_hash: str


@dataclass(frozen=True)
class StoredSource:
    """Phase 1 output handed to Phase 2."""

    source_id: int
    raw_text: str
    content_hash: str
    reused: bool


class SourceStorePort(Protocol):
    """Storage boundary for `sources`. Adapter owns SQLite."""

    def find_by_hash(self, content_hash: str) -> SourceRecord | None:
        """Return the stored source with this hash, or None."""
        ...

    def insert_source(self, *, title: str, full_text: str, content_hash: str) -> int:
        """Gatekeeper write boundary. Returns the new source id."""
        ...


def compute_content_hash(raw_text: str) -> str:
    """SHA-256 hex of the raw text bytes."""
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def default_title(raw_text: str) -> str:
    """First 80 characters of the raw text."""
    return raw_text[:TITLE_LENGTH]


def store_source(port: SourceStorePort, raw_text: str) -> StoredSource:
    """Dedup by content hash, then reuse or insert a `sources` row."""
    content_hash = compute_content_hash(raw_text)
    existing = port.find_by_hash(content_hash)
    if existing is not None and existing.full_text == raw_text:
        return StoredSource(
            source_id=existing.id,
            raw_text=raw_text,
            content_hash=content_hash,
            reused=True,
        )
    source_id = port.insert_source(
        title=default_title(raw_text),
        full_text=raw_text,
        content_hash=content_hash,
    )
    return StoredSource(
        source_id=source_id,
        raw_text=raw_text,
        content_hash=content_hash,
        reused=False,
    )

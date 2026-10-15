"""In-memory stand-in for `SourceStorePort` (Rule T3: fakes over mocks)."""

from __future__ import annotations

from ember.capture.source_storage import SourceRecord


class FakeSourceStore:
    def __init__(self) -> None:
        self.rows: dict[str, SourceRecord] = {}
        self._next_id = 1

    def find_by_hash(self, content_hash: str) -> SourceRecord | None:
        return self.rows.get(content_hash)

    def insert_source(self, *, title: str, full_text: str, content_hash: str) -> int:
        source_id = self._next_id
        self._next_id += 1
        self.rows[content_hash] = SourceRecord(source_id, full_text, content_hash)
        return source_id

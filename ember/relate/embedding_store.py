"""Port for the `item_embeddings` vector cache.

The port hides whether a vector is cached or must be recomputed. The storage
adapter owns the SQL and the packed float32 format.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingStorePort(Protocol):
    def get(self, item_id: int) -> list[float] | None:
        """Return the cached vector, or None when the item has no row.

        Raise `RELATE-037 EmbeddingReadFailed` on a read failure.
        """
        ...

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        """Store or replace one vector row.

        Raise `RELATE-019 EmbeddingWriteFailed` on a write failure.
        """
        ...

    def model_name_of(self, item_id: int) -> str | None:
        """Return the cached model name, or None when the item has no row.

        Raise `RELATE-037 EmbeddingReadFailed` on a read failure.
        """
        ...

    def first_model_name(self) -> str | None:
        """Return the cached model name from any row, or None when empty.

        Raise `RELATE-037 EmbeddingReadFailed` on a read failure.
        """
        ...

    def wipe(self) -> None:
        """Delete every cached vector.

        Raise `RELATE-019 EmbeddingWriteFailed` on a write failure.
        """
        ...

    def delete(self, item_id: int) -> None:
        """Delete one cached vector row, for repairing a damaged cache.

        The candidate pool's repair use: a wrong-length vector or a row whose
        blob cannot decode is deleted, then immediately re-encoded and
        re-upserted. The cache is derived, rebuildable data, so deleting one
        row loses nothing.

        Raise `RELATE-019 EmbeddingWriteFailed` on a write failure.
        """
        ...

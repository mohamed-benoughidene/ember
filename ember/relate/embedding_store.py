"""Port for the `item_embeddings` vector cache.

The port hides whether a vector is cached or must be recomputed. The storage
adapter owns the SQL and the packed float32 format.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingStorePort(Protocol):
    def get(self, item_id: int) -> list[float] | None: ...
    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None: ...
    def model_name_of(self, item_id: int) -> str | None: ...
    def first_model_name(self) -> str | None:
        """Return the cached model name from any row, or None when empty."""
        ...
    def wipe(self) -> None: ...

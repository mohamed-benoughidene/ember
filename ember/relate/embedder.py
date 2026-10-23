"""Port for the text embedder. The model itself lives in the adapter layer."""

from __future__ import annotations

from typing import Protocol


class EmbedderPort(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per text.

        Raise `RELATE-017 EmbedderLoadFailed` when the model cannot load and
        `RELATE-018 EmbedderEncodeFailed` when encoding fails or returns the
        wrong number of vectors.
        """
        ...

    def dim(self) -> int:
        """Return the vector length for this model."""
        ...

    def model_name(self) -> str:
        """Return the stable cache key for this model."""
        ...

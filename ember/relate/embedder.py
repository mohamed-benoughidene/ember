"""Port for the text embedder. The model itself lives in the adapter layer."""

from __future__ import annotations

from typing import Protocol


class EmbedderPort(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def dim(self) -> int: ...
    def model_name(self) -> str: ...

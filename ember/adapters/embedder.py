"""`sentence-transformers` embedder adapter for the Relate `EmbedderPort`.

`sentence-transformers` is an optional extra (`.[relate]`), never a main
dependency, so the library is imported lazily: importing this module does not
import the model library, and the CLI plus the whole test suite work without it.

The engine core only knows `EmbedderPort`. The model id mapping, the lazy
import, and the load timeout policy all live at this edge (L2 section 5.4).
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Mapping

from ember.relate.embedder import EmbedderPort
from ember.relate.errors import (
    ConfigMissing,
    EmbedderEncodeFailed,
    EmbedderLoadFailed,
    RelateError,
)

DEFAULT_MODEL = "bge-base-en-v1.5"
DEFAULT_LOAD_TIMEOUT_SECONDS = 120.0
MODEL_ENV = "EMBER_EMBEDDER_MODEL"
LOAD_TIMEOUT_ENV = "EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS"
_INSTALL_HINT = "pip install -e '.[relate]'"


class SentenceTransformerEmbedder:
    """`EmbedderPort` on `sentence-transformers`, loaded on construction.

    The load runs in a daemon thread so a hung download cannot block the CLI
    past `load_timeout`; a live thread after the join raises RELATE-017. The
    model id is mapped to its Hugging Face org id for loading, while
    `model_name()` returns the configured short name unchanged so the
    `item_embeddings` cache key stays stable across environments.
    """

    def __init__(self, model_name: str, *, load_timeout: float = 120.0) -> None:
        self._model_name = model_name
        self._model = _load_model(model_name, load_timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one plain `list[float]` per text (never numpy arrays).

        Any model failure becomes `EmbedderEncodeFailed` (RELATE-018); an
        already-raised `RelateError` is re-raised unchanged.
        """
        try:
            encoded = self._model.encode(texts)
            return [[float(value) for value in row] for row in encoded]
        except RelateError:
            raise
        except Exception as exc:  # noqa: BLE001 - any model failure is an encode fail
            raise EmbedderEncodeFailed(
                "embedder encode failed",
                model=self._model_name,
                detail=_detail(exc),
            ) from exc

    def dim(self) -> int:
        """Return the model's sentence embedding dimension as int."""
        return int(self._model.get_sentence_embedding_dimension())

    def model_name(self) -> str:
        """Return the configured name unchanged (stable cache key)."""
        return self._model_name


def build_embedder(env: Mapping[str, str] | None = None) -> EmbedderPort:
    """Build the embedder from env config, once at boot (Constitution I13).

    Keys: `EMBER_EMBEDDER_MODEL` (default `bge-base-en-v1.5`) and
    `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS` (default 120).

    Raise `ConfigMissing` (RELATE-035) when the timeout is not a number. Mirrors
    the factory style of `build_item_proposer` in the LLM adapter.
    """
    values = os.environ if env is None else env
    model_name = values.get(MODEL_ENV, DEFAULT_MODEL)
    timeout = _parse_timeout(values.get(LOAD_TIMEOUT_ENV))
    return SentenceTransformerEmbedder(model_name, load_timeout=timeout)


def _parse_timeout(raw: str | None) -> float:
    if raw is None:
        return DEFAULT_LOAD_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigMissing(
            f"{LOAD_TIMEOUT_ENV} must be a number",
            var=LOAD_TIMEOUT_ENV,
            value=raw,
        ) from exc


def _load_model(model_name: str, load_timeout: float) -> Any:
    """Load the model in a daemon thread with a timeout (RELATE-017 on failure)."""
    transformer_cls = _import_sentence_transformer()
    resolved = _resolve_model_id(model_name)
    result: dict[str, Any] = {}

    def construct() -> None:
        # Catch inside the thread so the failure is ferried to the caller
        # instead of hitting threading.excepthook and printing a traceback.
        try:
            result["model"] = transformer_cls(resolved)
        except BaseException as exc:  # noqa: BLE001 - re-raised as RELATE-017 below
            result["error"] = exc

    thread = threading.Thread(target=construct, daemon=True)
    thread.start()
    thread.join(load_timeout)
    if thread.is_alive():
        raise EmbedderLoadFailed(
            "embedder load timed out",
            model=model_name,
            timeout=load_timeout,
        )
    error = result.get("error")
    if error is not None:
        raise EmbedderLoadFailed(
            "embedder load failed",
            model=model_name,
            detail=_detail(error),
        ) from error
    return result["model"]


def _import_sentence_transformer() -> Callable[..., Any]:
    """Import the optional model library lazily, naming the extra when absent."""
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as exc:
        raise EmbedderLoadFailed(
            "sentence-transformers is not installed; install the optional extra "
            f"with: {_INSTALL_HINT}",
            extra="relate",
            detail=str(exc),
        ) from exc
    return SentenceTransformer


def _resolve_model_id(model_name: str) -> str:
    """Map a short `bge-*` name to its Hugging Face org id; pass others through."""
    if "/" not in model_name and model_name.startswith("bge"):
        return f"BAAI/{model_name}"
    return model_name


def _detail(exc: BaseException) -> str:
    return str(exc)[:200]

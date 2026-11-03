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
from importlib.util import find_spec
from typing import Any, Callable, Mapping

from ember.relate.embedder import EmbedderPort
from ember.relate.errors import (
    ConfigMissing,
    EmbedderEncodeFailed,
    EmbedderLoadFailed,
    EmbedderLoadTimedOut,
    EmbedderPackageMissing,
    RelateError,
)

DEFAULT_MODEL = "bge-base-en-v1.5"
DEFAULT_LOAD_TIMEOUT_SECONDS = 120.0
MODEL_ENV = "EMBER_EMBEDDER_MODEL"
LOAD_TIMEOUT_ENV = "EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS"
OFFLINE_ENV = "HF_HUB_OFFLINE"
_INSTALL_HINT = "pip install -e '.[relate]'"


class SentenceTransformerEmbedder:
    """`EmbedderPort` on `sentence-transformers`, loaded on construction.

    The load runs in a daemon thread so a hung download cannot block the CLI
    past `load_timeout`; a live thread after the join raises
    `EmbedderLoadTimedOut` (RELATE-040). The model id is mapped to its
    Hugging Face org id for loading, while `model_name()` returns the
    configured short name unchanged so the `item_embeddings` cache key stays
    stable across environments.

    In offline mode (`HF_HUB_OFFLINE`) a model missing from the local
    cache raises `EmbedderLoadFailed` (RELATE-017) at once, so the
    load thread never starts and no download is attempted (Chunk 14).

    Raise `EmbedderLoadFailed` (RELATE-017) when the model cannot load.
    """

    def __init__(
        self,
        model_name: str,
        *,
        load_timeout: float = 120.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._model_name = model_name
        values = os.environ if env is None else env
        if _is_offline(values) and not _model_is_cached(
            model_name, _resolve_model_id(model_name)
        ):
            raise EmbedderLoadFailed(
                f"model {model_name} is missing from the local cache and the "
                f"environment is offline; no download was started",
                model=model_name,
            )
        self._model = _load_model(model_name, load_timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one plain `list[float]` per text (never numpy arrays).

        Raise `EmbedderEncodeFailed` (RELATE-018) when the model fails or
        returns a different number of vectors than texts. An already-raised
        `RelateError` is re-raised unchanged.
        """
        try:
            encoded = self._model.encode(texts)
            rows = [[float(value) for value in row] for row in encoded]
        except RelateError:
            raise
        except Exception as exc:  # noqa: BLE001 - any model failure is an encode fail
            raise EmbedderEncodeFailed(
                "embedder encode failed",
                model=self._model_name,
                detail=_detail(exc),
            ) from exc
        if len(rows) != len(texts):
            raise EmbedderEncodeFailed(
                "embedder returned the wrong vector count",
                model=self._model_name,
                expected=len(texts),
                got=len(rows),
            )
        return rows

    def dim(self) -> int:
        """Return the model's sentence embedding dimension as int.

        `sentence-transformers` 6 renamed the getter to
        `get_embedding_dimension`; use it when present and fall back to the
        older `get_sentence_embedding_dimension` for older releases.
        """
        getter = getattr(self._model, "get_embedding_dimension", None)
        if getter is None:
            getter = self._model.get_sentence_embedding_dimension
        return int(getter())

    def model_name(self) -> str:
        """Return the configured name unchanged (stable cache key)."""
        return self._model_name


def validate_embedder_config(
    env: Mapping[str, str] | None = None,
) -> float:
    """Validate embedder config and the optional packages at CLI boot.

    Input: an environment mapping (defaults to `os.environ`).
    Output: the parsed load timeout in seconds.
    Raises: `ConfigMissing` (RELATE-035) when the timeout is not a positive
    number, and
    `EmbedderPackageMissing` (RELATE-039) when `sentence_transformers` or
    `torch` is not installed.
    Side effects: none; no model is loaded and nothing is imported.
    """
    values = os.environ if env is None else env
    timeout = _parse_timeout(values.get(LOAD_TIMEOUT_ENV))
    for package in ("sentence_transformers", "torch"):
        if find_spec(package) is None:
            raise EmbedderPackageMissing(
                f"{package} is not installed; install the optional extra with: "
                f"{_INSTALL_HINT}",
                extra="relate",
                package=package,
            )
    return timeout


def build_embedder(env: Mapping[str, str] | None = None) -> EmbedderPort:
    """Build the embedder from env config, once at boot (Constitution I13).

    Keys: `EMBER_EMBEDDER_MODEL` (default `bge-base-en-v1.5`) and
    `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS` (default 120).

    Raises `ConfigMissing` (RELATE-035) for a bad (non-positive or
    non-numeric) timeout,
    `EmbedderPackageMissing` (RELATE-039) for a missing package,
    `EmbedderLoadFailed` (RELATE-017) for a failed model load, and
    `EmbedderLoadTimedOut` (RELATE-040) when the load is still running past
    the timeout. With `HF_HUB_OFFLINE` set and the model missing from the
    local cache, `EmbedderLoadFailed` raises at once — before the load
    thread starts (Chunk 14). Mirrors the factory style of
    `build_item_proposer` in the LLM adapter.

    Output: an `EmbedderPort`. Side effects: loads the model, which may
    download weights and blocks up to the configured timeout unless the
    offline fail-fast above applies first. No DB I/O.
    """
    values = os.environ if env is None else env
    timeout = _parse_timeout(values.get(LOAD_TIMEOUT_ENV))
    model_name = values.get(MODEL_ENV, DEFAULT_MODEL)
    return SentenceTransformerEmbedder(model_name, load_timeout=timeout, env=values)


def _parse_timeout(raw: str | None) -> float:
    if raw is None:
        return DEFAULT_LOAD_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ConfigMissing(
            f"{LOAD_TIMEOUT_ENV} must be a number",
            var=LOAD_TIMEOUT_ENV,
            value=raw,
        ) from exc
    if timeout <= 0:
        raise ConfigMissing(
            f"{LOAD_TIMEOUT_ENV} must be a positive number",
            var=LOAD_TIMEOUT_ENV,
            value=raw,
        )
    return timeout


def _is_offline(values: Mapping[str, str]) -> bool:
    """Return whether `HF_HUB_OFFLINE` turns the hub offline.

    The truthy words the hub library itself accepts (`1`, `on`, `yes`,
    `true`, case-insensitive); unset, `0` or any other value means online.
    """
    return values.get(OFFLINE_ENV, "").strip().lower() in ("1", "on", "yes", "true")


def _model_is_cached(model_name: str, resolved_model_id: str) -> bool:
    """Return whether the model is usable without any network access.

    A model string naming an existing local directory is cached by
    definition (`sentence-transformers` loads local paths directly). All
    other names are looked up in the local Hugging Face disk cache with
    `scan_cache_dir`, which is purely local (no network). The hub import is
    lazy, exactly like `sentence_transformers` (module docstring), so the
    suite keeps working without the `relate` extra. This function is the
    monkeypatch seam for the offline tests (Chunk 14, decisions N21).
    """
    if os.path.isdir(model_name):
        return True
    try:
        from huggingface_hub import scan_cache_dir
    except Exception:  # noqa: BLE001 - hub extra absent: there is no cache info
        return False
    try:
        cached_repos = scan_cache_dir().repos
    except Exception:  # noqa: BLE001 - an unreadable cache counts as no model
        return False
    return any(
        repo.repo_id in (resolved_model_id, model_name) for repo in cached_repos
    )


def _load_model(model_name: str, load_timeout: float) -> Any:
    """Load the model in a daemon thread with a timeout (RELATE-040 on a live
    thread after the join, RELATE-017 on a failed load)."""
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
        raise EmbedderLoadTimedOut(
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
    except RelateError:
        raise
    except Exception as exc:  # noqa: BLE001 - an import failure is RELATE-039
        missing = getattr(exc, "name", None)
        if missing:
            message = (
                f"{missing} is not installed; install the optional extra with: "
                f"{_INSTALL_HINT}"
            )
        else:
            message = (
                "sentence-transformers import failed; install the optional extra "
                f"with: {_INSTALL_HINT}"
            )
        raise EmbedderPackageMissing(
            message,
            extra="relate",
            detail=_detail(exc),
        ) from exc
    return SentenceTransformer


def _resolve_model_id(model_name: str) -> str:
    """Map a short `bge-*` name to its Hugging Face org id; pass others through."""
    if "/" not in model_name and model_name.startswith("bge"):
        return f"BAAI/{model_name}"
    return model_name


def _detail(exc: BaseException) -> str:
    return str(exc)[:200]

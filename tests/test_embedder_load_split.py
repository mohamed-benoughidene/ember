"""The embedder's load-time errors carry two dedicated codes, not RELATE-017.

Batch 6 (D-08, I17): the missing-package refusal and the load-timeout
(join-timeout / live thread) refusal are different failures with different
advice, so each gets its own code. The old shared `EmbedderLoadFailed`
(RELATE-017) stays untouched for the "model failed to load" case.
"""

from __future__ import annotations

import sys
import threading

import pytest

from ember.adapters import embedder as embedder_mod
from ember.adapters.embedder import validate_embedder_config
from ember.errors import EmberError
from ember.relate.errors import EmbedderLoadFailed

MISSING_PACKAGE_CODE = "RELATE-039"
LOAD_TIMED_OUT_CODE = "RELATE-040"


def test_missing_package_raises_its_own_code(monkeypatch) -> None:
    """`sentence_transformers`/`torch` absent at config time -> RELATE-039,
    no longer the shared RELATE-017."""
    monkeypatch.setattr(embedder_mod, "find_spec", lambda package: None)

    with pytest.raises(EmberError) as excinfo:
        validate_embedder_config({})

    assert excinfo.value.code == MISSING_PACKAGE_CODE
    assert excinfo.value.code != "RELATE-017"


def test_failed_import_raises_the_package_code(monkeypatch) -> None:
    """A broken optional-package import inside the loader -> RELATE-039 too."""
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    with pytest.raises(EmberError) as excinfo:
        embedder_mod._load_model("bge-base-en-v1.5", 5.0)

    assert excinfo.value.code == MISSING_PACKAGE_CODE


class _NeverFinishesThread:
    """A stand-in thread that never produces a model (simulates a hung load)."""

    def start(self) -> None:
        pass

    def join(self, timeout: float) -> None:
        pass

    def is_alive(self) -> bool:
        return True


def test_live_thread_after_join_timeout_raises_its_own_code(monkeypatch) -> None:
    """A load thread still alive after the join timeout -> RELATE-040, no
    longer the shared RELATE-017."""
    monkeypatch.setattr(
        threading, "Thread", lambda target, daemon: _NeverFinishesThread()
    )
    monkeypatch.setattr(
        embedder_mod, "_import_sentence_transformer", lambda: object()
    )

    with pytest.raises(EmberError) as excinfo:
        embedder_mod._load_model("bge-base-en-v1.5", 5.0)

    assert excinfo.value.code == LOAD_TIMED_OUT_CODE
    assert excinfo.value.code != MISSING_PACKAGE_CODE


def test_model_load_failure_keeps_the_old_relate_017_code(monkeypatch) -> None:
    """The untouched case: a model that raises while loading inside the
    thread keeps the shared `EmbedderLoadFailed` (RELATE-017)."""

    class _ExplodingTransformer:
        def __init__(self, model_id: str) -> None:
            raise OSError("download failed")

    monkeypatch.setattr(
        embedder_mod,
        "_import_sentence_transformer",
        lambda: _ExplodingTransformer,
    )

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        embedder_mod._load_model("bge-base-en-v1.5", 5.0)

    assert excinfo.value.code == "RELATE-017"

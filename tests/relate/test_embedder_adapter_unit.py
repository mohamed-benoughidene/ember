"""Unit tests for the `sentence-transformers` embedder adapter.

The real `sentence_transformers` package is an optional extra and is never
imported here: each test injects a fake module into `sys.modules`. No network
call is made and no real model is loaded.
"""

from __future__ import annotations

import sys
import time
import types
from typing import Any

import pytest

from ember.adapters.embedder import SentenceTransformerEmbedder, build_embedder
from ember.relate.errors import (
    ConfigMissing,
    EmbedderEncodeFailed,
    EmbedderLoadFailed,
)

MODULE = "sentence_transformers"


def install_fake(
    monkeypatch: pytest.MonkeyPatch, transformer_cls: type
) -> type:
    """Inject a fake `sentence_transformers` module with a fake class."""
    module = types.ModuleType(MODULE)
    module.SentenceTransformer = transformer_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, MODULE, module)
    return transformer_cls


def recording_transformer() -> type:
    """A fake whose `__init__` records the model id it was handed."""

    class FakeSentenceTransformer:
        load_ids: list[str] = []

        def __init__(self, model_id: str, **kwargs: Any) -> None:
            self.model_id = model_id
            FakeSentenceTransformer.load_ids.append(model_id)

        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(text)) for _ in range(3)] for text in texts]

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    return FakeSentenceTransformer


def test_bge_short_name_maps_to_bai_org_id(monkeypatch: pytest.MonkeyPatch) -> None:
    Fake = recording_transformer()
    install_fake(monkeypatch, Fake)

    embedder = SentenceTransformerEmbedder("bge-base-en-v1.5")

    assert Fake.load_ids == ["BAAI/bge-base-en-v1.5"]
    assert embedder.model_name() == "bge-base-en-v1.5"


@pytest.mark.parametrize(
    "name",
    [
        "BAAI/bge-base-en-v1.5",
        "sentence-transformers/all-MiniLM-L6-v2",
        "all-MiniLM-L6-v2",
    ],
)
def test_other_names_pass_through_unchanged(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    Fake = recording_transformer()
    install_fake(monkeypatch, Fake)

    embedder = SentenceTransformerEmbedder(name)

    assert Fake.load_ids == [name]
    assert embedder.model_name() == name


def test_embed_returns_plain_lists_of_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            pass

        def encode(self, texts: list[str]) -> list[list[int]]:
            return [[1, 2, 3], [4, 5, 6]]

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)
    embedder = SentenceTransformerEmbedder("bge-base-en-v1.5")

    vectors = embedder.embed(["a", "b"])

    assert vectors == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert all(type(row) is list for row in vectors)
    assert all(type(value) is float for row in vectors for value in row)


def test_encode_failure_raises_relate_018(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            pass

        def encode(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("boom")

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)
    embedder = SentenceTransformerEmbedder("bge-base-en-v1.5")

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        embedder.embed(["a"])

    assert excinfo.value.code == "RELATE-018"


def test_existing_relate_error_is_reraised_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = EmbedderEncodeFailed("already failed")

    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            pass

        def encode(self, texts: list[str]) -> list[list[float]]:
            raise original

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)
    embedder = SentenceTransformerEmbedder("bge-base-en-v1.5")

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        embedder.embed(["a"])

    assert excinfo.value is original


def test_constructor_failure_raises_relate_017(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            raise RuntimeError("cannot download weights")

    install_fake(monkeypatch, Fake)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        SentenceTransformerEmbedder("bge-base-en-v1.5")

    assert excinfo.value.code == "RELATE-017"


def test_missing_module_raises_relate_017_with_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # None in sys.modules makes the lazy import raise ModuleNotFoundError.
    monkeypatch.setitem(sys.modules, MODULE, None)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        SentenceTransformerEmbedder("bge-base-en-v1.5")

    assert excinfo.value.code == "RELATE-017"
    assert ".[relate]" in excinfo.value.message
    assert ".[relate]" in str(excinfo.value)


def test_slow_load_times_out_with_relate_017(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            time.sleep(0.3)

        def encode(self, texts: list[str]) -> list[list[float]]:
            return []

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        SentenceTransformerEmbedder("bge-base-en-v1.5", load_timeout=0.01)

    assert excinfo.value.code == "RELATE-017"


def test_dim_returns_int(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            pass

        def encode(self, texts: list[str]) -> list[list[float]]:
            return []

        def get_sentence_embedding_dimension(self) -> int:
            return 768

    install_fake(monkeypatch, Fake)
    embedder = SentenceTransformerEmbedder("bge-base-en-v1.5")

    dim = embedder.dim()

    assert dim == 768
    assert type(dim) is int


def test_build_embedder_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    Fake = recording_transformer()
    install_fake(monkeypatch, Fake)

    embedder = build_embedder({})

    assert embedder.model_name() == "bge-base-en-v1.5"
    assert Fake.load_ids == ["BAAI/bge-base-en-v1.5"]


def test_build_embedder_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    Fake = recording_transformer()
    install_fake(monkeypatch, Fake)

    embedder = build_embedder({"EMBER_EMBEDDER_MODEL": "all-MiniLM-L6-v2"})

    assert embedder.model_name() == "all-MiniLM-L6-v2"
    assert Fake.load_ids == ["all-MiniLM-L6-v2"]


def test_build_embedder_bad_timeout_raises_relate_035() -> None:
    # No fake installed: config is parsed before the lazy import, so this must
    # raise RELATE-035 and never reach the model library.
    with pytest.raises(ConfigMissing) as excinfo:
        build_embedder({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": "soon"})

    assert excinfo.value.code == "RELATE-035"


def test_build_embedder_timeout_env_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: Any) -> None:
            time.sleep(0.3)

        def encode(self, texts: list[str]) -> list[list[float]]:
            return []

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        build_embedder({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": "0.01"})

    assert excinfo.value.code == "RELATE-017"

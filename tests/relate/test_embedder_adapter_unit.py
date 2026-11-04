"""Unit tests for the `sentence-transformers` embedder adapter.

The real `sentence_transformers` package is an optional extra and is never
imported here: each test injects a fake module into `sys.modules`. No network
call is made and no real model is loaded.
"""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

from ember.adapters.embedder import (
    EmbedderLoadTimedOut,
    EmbedderPackageMissing,
    SentenceTransformerEmbedder,
    build_embedder,
    validate_embedder_config,
)
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
    module.SentenceTransformer = transformer_cls
    monkeypatch.setitem(sys.modules, MODULE, module)
    return transformer_cls


def patch_find_spec(
    monkeypatch: pytest.MonkeyPatch, *, missing: set[str]
) -> list[str]:
    """Patch the module-level `find_spec` so `missing` looks uninstalled.

    Returns the list `find_spec` appends to, so a test can assert which
    packages the validator probed and in what order.
    """
    probed: list[str] = []

    def fake_find_spec(name: str) -> object | None:
        probed.append(name)
        return None if name in missing else object()

    monkeypatch.setattr("ember.adapters.embedder.find_spec", fake_find_spec)
    return probed


def recording_transformer() -> type:
    """A fake whose `__init__` records the model id it was handed."""

    class FakeSentenceTransformer:
        load_ids: list[str] = []

        def __init__(self, model_id: str, **kwargs: object) -> None:
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
        def __init__(self, model_id: str, **kwargs: object) -> None:
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
        def __init__(self, model_id: str, **kwargs: object) -> None:
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


def test_wrong_vector_count_raises_relate_018(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: object) -> None:
            pass

        def encode(self, texts: list[str]) -> list[list[float]]:
            # One vector for two texts: the model dropped a row.
            return [[1.0, 2.0, 3.0]]

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)
    embedder = SentenceTransformerEmbedder("bge-base-en-v1.5")

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        embedder.embed(["a", "b"])

    assert excinfo.value.code == "RELATE-018"
    assert excinfo.value.context == {
        "model": "bge-base-en-v1.5",
        "expected": 2,
        "got": 1,
    }


def test_existing_relate_error_is_reraised_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = EmbedderEncodeFailed("already failed")

    class Fake:
        def __init__(self, model_id: str, **kwargs: object) -> None:
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
        def __init__(self, model_id: str, **kwargs: object) -> None:
            raise RuntimeError("cannot download weights")

    install_fake(monkeypatch, Fake)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        SentenceTransformerEmbedder("bge-base-en-v1.5")

    assert excinfo.value.code == "RELATE-017"


def test_missing_module_raises_relate_039_with_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # None in sys.modules makes the lazy import raise ModuleNotFoundError.
    monkeypatch.setitem(sys.modules, MODULE, None)

    with pytest.raises(EmbedderPackageMissing) as excinfo:
        SentenceTransformerEmbedder("bge-base-en-v1.5")

    assert excinfo.value.code == "RELATE-039"
    assert ".[relate]" in excinfo.value.message
    assert ".[relate]" in str(excinfo.value)


def test_slow_load_times_out_with_relate_040(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: object) -> None:
            time.sleep(0.3)

        def encode(self, texts: list[str]) -> list[list[float]]:
            return []

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)

    with pytest.raises(EmbedderLoadTimedOut) as excinfo:
        SentenceTransformerEmbedder("bge-base-en-v1.5", load_timeout=0.01)

    assert excinfo.value.code == "RELATE-040"


def test_dim_returns_int(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self, model_id: str, **kwargs: object) -> None:
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
        def __init__(self, model_id: str, **kwargs: object) -> None:
            time.sleep(0.3)

        def encode(self, texts: list[str]) -> list[list[float]]:
            return []

        def get_sentence_embedding_dimension(self) -> int:
            return 3

    install_fake(monkeypatch, Fake)

    with pytest.raises(EmbedderLoadTimedOut) as excinfo:
        build_embedder({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": "0.01"})

    assert excinfo.value.code == "RELATE-040"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, 120.0),
        ({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": "7.5"}, 7.5),
    ],
)
def test_validate_embedder_config_returns_the_parsed_timeout(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: float
) -> None:
    probed = patch_find_spec(monkeypatch, missing=set())

    timeout = validate_embedder_config(env)

    assert timeout == expected
    assert type(timeout) is float
    assert probed == ["sentence_transformers", "torch"]


@pytest.mark.parametrize("missing", ["sentence_transformers", "torch"])
def test_validate_embedder_config_missing_package_raises_relate_039(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    patch_find_spec(monkeypatch, missing={missing})

    with pytest.raises(EmbedderPackageMissing) as excinfo:
        validate_embedder_config({})

    assert excinfo.value.code == "RELATE-039"
    assert excinfo.value.context["package"] == missing
    assert missing in excinfo.value.message
    assert ".[relate]" in excinfo.value.message


def test_validate_embedder_config_bad_timeout_raises_relate_035(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _must_not_probe(name: str) -> object:
        raise AssertionError("the timeout is parsed before the packages are probed")

    monkeypatch.setattr("ember.adapters.embedder.find_spec", _must_not_probe)

    with pytest.raises(ConfigMissing) as excinfo:
        validate_embedder_config({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": "soon"})

    assert excinfo.value.code == "RELATE-035"


@pytest.mark.parametrize("value", ["0", "-1"])
def test_validate_embedder_config_refuses_non_positive_timeout(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    def _must_not_probe(name: str) -> object:
        raise AssertionError("the timeout is parsed before the packages are probed")

    monkeypatch.setattr("ember.adapters.embedder.find_spec", _must_not_probe)

    with pytest.raises(ConfigMissing) as excinfo:
        validate_embedder_config({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": value})

    assert excinfo.value.code == "RELATE-035"
    assert excinfo.value.context["var"] == "EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS"
    assert excinfo.value.context["value"] == value


@pytest.mark.parametrize("value", ["0", "-1"])
def test_build_embedder_refuses_non_positive_timeout(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    # No fake installed: a refused timeout must raise before the lazy import,
    # the offline cache check and the model-load thread.
    with pytest.raises(ConfigMissing) as excinfo:
        build_embedder({"EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS": value})

    assert excinfo.value.code == "RELATE-035"


def test_offline_with_no_cached_model_fails_at_once_and_the_thread_never_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_calls: list[str] = []

    def not_cached(model_name: str, resolved_model_id: str) -> bool:
        return False

    def must_not_load(model_name: str, load_timeout: float) -> object:
        load_calls.append(model_name)
        raise AssertionError(
            "the model-load path must never run for a missing offline cache"
        )

    # The seam helper answers "not cached" (Chunk 14 seam: the cache read
    # is a module-level function so tests can patch it without the network).
    monkeypatch.setattr("ember.adapters.embedder._model_is_cached", not_cached)
    monkeypatch.setattr("ember.adapters.embedder._load_model", must_not_load)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        build_embedder({"HF_HUB_OFFLINE": "1"})

    assert excinfo.value.code == "RELATE-017"
    assert excinfo.value.context["model"] == "bge-base-en-v1.5"
    assert load_calls == []


def test_offline_with_a_local_model_directory_loads_without_the_hub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A model string naming an existing local directory is "cached" by
    # definition: it passes the offline check and the real directory scan
    # never runs, so no hub call of any kind is made.
    Fake = recording_transformer()
    install_fake(monkeypatch, Fake)
    local_model = tmp_path / "my-model"
    local_model.mkdir()

    embedder = build_embedder(
        {"HF_HUB_OFFLINE": "1", "EMBER_EMBEDDER_MODEL": str(local_model)}
    )

    assert Fake.load_ids == [str(local_model)]
    assert embedder.model_name() == str(local_model)

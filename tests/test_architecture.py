"""Architecture test: engine core never imports an adapter (Rule T9)."""

from __future__ import annotations

from pathlib import Path

import ember.capture.confirm_write as confirm_write
import ember.capture.input_reader as input_reader
import ember.capture.item_gatekeeper as item_gatekeeper
import ember.capture.item_proposal as item_proposal
import ember.capture.source_storage as source_storage

FORBIDDEN = ("sqlite3", "openai", "anthropic", "ember.adapters")
FORBIDDEN_RELATE = (*FORBIDDEN, "sentence_transformers", "numpy")


def test_capture_core_does_not_import_adapters() -> None:
    for module in (
        source_storage,
        input_reader,
        item_proposal,
        item_gatekeeper,
        confirm_write,
    ):
        text = Path(module.__file__).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{module.__name__} references {token}"


def test_relate_core_does_not_import_adapters() -> None:
    relate_dir = Path(__file__).resolve().parents[1] / "ember" / "relate"
    paths = sorted(relate_dir.glob("*.py"))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RELATE:
            assert token not in text, f"{path} references {token}"


def test_signals_wrapper_stays_inside_candidate_pool() -> None:
    """The Signals wrapper lives and dies in candidate_pool.py (L2 §12, T9).

    No `ember` file except candidate_pool.py may even name `Signals` (not just
    import it), so the bundle cannot leak into rows.py, the CLI, or a port.
    """
    engine_dir = Path(__file__).resolve().parents[1] / "ember"
    paths = sorted(engine_dir.rglob("*.py"))
    assert len(paths) > 1
    for path in paths:
        if path.name == "candidate_pool.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "Signals" not in text, f"{path} names Signals"


def test_maintain_core_does_not_import_adapters() -> None:
    maintain_dir = Path(__file__).resolve().parents[1] / "ember" / "maintain"
    paths = sorted(maintain_dir.glob("*.py"))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RELATE:
            assert token not in text, f"{path} references {token}"


def test_query_core_does_not_import_adapters() -> None:
    query_dir = Path(__file__).resolve().parents[1] / "ember" / "query"
    paths = sorted(query_dir.glob("*.py"))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RELATE:
            assert token not in text, f"{path} references {token}"


def test_bridge_core_does_not_import_adapters() -> None:
    """The bridge is PURE code (bridge L2 §4, T9): `ember/bridge/*.py`
    imports no adapter — `ember/cli.py` converts adapter reports to plain
    dicts before anything crosses into the bridge, and the one bridge
    adapter (the JSON-lines confirm port) lives in `ember/adapters/`."""
    bridge_dir = Path(__file__).resolve().parents[1] / "ember" / "bridge"
    paths = sorted(bridge_dir.glob("*.py"))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{path} references {token}"


def test_engine_core_does_not_reference_link_replay() -> None:
    """The replay step lives in the adapters. No engine core may name it (T9)."""
    paths = []
    for name in ("relate", "maintain", "query", "capture"):
        core_dir = Path(__file__).resolve().parents[1] / "ember" / name
        paths.extend(sorted(core_dir.glob("*.py")))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "link_replay" not in text, f"{path} references link_replay"

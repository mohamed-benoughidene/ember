"""Architecture test: engine core never imports an adapter (Rule T9)."""

from __future__ import annotations

from pathlib import Path

import ember.capture.confirm_write as confirm_write
import ember.capture.input_reader as input_reader
import ember.capture.item_gatekeeper as item_gatekeeper
import ember.capture.item_proposal as item_proposal
import ember.capture.source_storage as source_storage

FORBIDDEN = ("sqlite3", "openai", "anthropic", "ember.adapters")


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

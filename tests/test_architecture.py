"""Architecture test: engine core never imports an adapter (Rule T9)."""

from __future__ import annotations

from pathlib import Path

import ember.capture.input_reader as input_reader
import ember.capture.source_storage as source_storage

FORBIDDEN = ("sqlite3", "openai", "ember.adapters")


def test_capture_core_does_not_import_adapters() -> None:
    for module in (source_storage, input_reader):
        text = Path(module.__file__).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{module.__name__} references {token}"

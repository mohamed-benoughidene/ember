"""Unit tests for phase 1 core logic (fake store, no DB)."""

from __future__ import annotations

import hashlib

import pytest

from ember.capture.errors import (
    InvalidUtf8Error,
    SourceFileNotFound,
    SourceFileTooLarge,
)
from ember.capture.input_reader import MAX_SOURCE_BYTES, InputMode, read_raw_text
from ember.capture.source_storage import (
    compute_content_hash,
    default_title,
    store_source,
)
from tests.fakes import FakeSourceStore


def test_content_hash_matches_sha256_hex() -> None:
    expected = hashlib.sha256(b"hello").hexdigest()
    assert compute_content_hash("hello") == expected


def test_default_title_is_first_80_chars() -> None:
    assert default_title("x" * 200) == "x" * 80


def test_same_text_twice_reuses_first_source_id() -> None:
    store = FakeSourceStore()
    first = store_source(store, "hello")
    second = store_source(store, "hello")

    assert first.source_id == second.source_id
    assert first.reused is False
    assert second.reused is True
    assert len(store.rows) == 1


def test_different_text_gets_new_source_id() -> None:
    store = FakeSourceStore()
    first = store_source(store, "hello")
    second = store_source(store, "world")

    assert first.source_id != second.source_id
    assert second.reused is False
    assert len(store.rows) == 2


def test_returned_raw_text_is_untouched() -> None:
    store = FakeSourceStore()
    text = "  line one\nline two  "
    result = store_source(store, text)

    assert result.raw_text == text


def test_invalid_utf8_raises(tmp_path) -> None:
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(InvalidUtf8Error):
        read_raw_text(mode=InputMode.FILE, path=str(bad))


def test_missing_file_raises(tmp_path) -> None:
    with pytest.raises(SourceFileNotFound):
        read_raw_text(mode=InputMode.FILE, path=str(tmp_path / "nope.txt"))


def test_file_over_threshold_raises(tmp_path) -> None:
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * (MAX_SOURCE_BYTES + 1))

    with pytest.raises(SourceFileTooLarge) as excinfo:
        read_raw_text(mode=InputMode.FILE, path=str(big))

    assert excinfo.value.code == "CAPTURE-002"


def test_error_carries_stable_code() -> None:
    assert InvalidUtf8Error("invalid utf-8").code == "CAPTURE-004"
    assert SourceFileNotFound("file not found: /x").code == "CAPTURE-001"

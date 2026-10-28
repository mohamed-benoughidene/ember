"""Unit tests for the shared tokenizer (mixed case, punctuation, unicode)."""

from __future__ import annotations

from ember.query.tokenize import tokenize


def test_mixed_case_folds() -> None:
    assert tokenize("SQLite SQLITE sqlite") == ["sqlite", "sqlite", "sqlite"]


def test_punctuation_splits_and_is_dropped() -> None:
    assert tokenize("add_item, then (link); done!") == [
        "add",
        "item",
        "then",
        "link",
        "done",
    ]


def test_unicode_letters_are_token_characters() -> None:
    assert tokenize("café naïve") == ["café", "naïve"]


def test_digits_are_tokens() -> None:
    assert tokenize("migration 010 of 001-010") == [
        "migration",
        "010",
        "of",
        "001",
        "010",
    ]


def test_punctuation_only_and_empty_yield_no_tokens() -> None:
    assert tokenize("!!! ???") == []
    assert tokenize("   ") == []

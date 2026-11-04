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


def test_nfc_then_casefold() -> None:
    """NFC-normalize first, then full case folding, before splitting."""
    # NFD cafe-with-acute (e + combining mark) and NFC (U+00E9) are one token.
    assert tokenize("caf\u0065\u0301") == tokenize("caf\u00e9") == ["caf\u00e9"]
    # Full case folding: STRASSE and Straße both fold to strasse.
    assert tokenize("STRASSE") == tokenize("Stra\u00dfe") == ["strasse"]
    # Dotted capital I folds identically in both spellings.
    assert tokenize("\u0130stanbul") == tokenize("\u0130STANBUL")

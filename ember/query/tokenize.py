"""The one tokenizer the gate and the scorer share.

NFC-normalize, then full case fold, then split on runs of characters that
are not letters or digits (unicode letters and digits are kept). No
stemming, no accent stripping, no stopword list, no phrase matching: a term
is one token.
"""

from __future__ import annotations

import unicodedata


def tokenize(text: str) -> list[str]:
    """Return the tokens of `text`: case-folded, split on non-alphanumerics."""
    tokens: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFC", text).casefold():
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens

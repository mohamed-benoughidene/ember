"""The one tokenizer the gate and the scorer share.

Lowercase, then split on runs of characters that are not letters or digits
(unicode letters and digits are kept). No stemming, no stopword list, no
phrase matching: a term is one token.
"""

from __future__ import annotations


def tokenize(text: str) -> list[str]:
    """Return the tokens of `text`: lowercase, split on non-alphanumerics."""
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens

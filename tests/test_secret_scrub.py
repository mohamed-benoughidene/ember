"""Secret scrubbing: no key-shaped value may survive an error line."""

from __future__ import annotations

from ember.adapters.llm import _without_secret
from ember.errors import EmberError

PLANTED_TOKEN = "sk-plant0987654321abcdef"
CONFIG_SECRET = "sk-config0123456789"


def test_log_line_contains_no_planted_tokens(monkeypatch) -> None:
    """`log_line()` must not print a planted `sk-` token or the env key value."""
    env_value = "emberfakevalue111222333444"
    monkeypatch.setenv("EMBER_AI_API_KEY", env_value)
    error = EmberError(
        "x",
        detail=f"token {PLANTED_TOKEN} here and key {env_value} there",
    )
    line = error.log_line()
    assert PLANTED_TOKEN not in line
    assert env_value not in line
    assert "REDACTED" in line


def test_without_secret_strips_both_and_stays_short() -> None:
    """`_without_secret` strips the planted `sk-` token and the exact key."""
    result = _without_secret(f"boom {PLANTED_TOKEN}", CONFIG_SECRET)
    assert PLANTED_TOKEN not in result
    assert CONFIG_SECRET not in result
    assert len(result) < 200

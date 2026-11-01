"""Single project error base with stable codes and no secrets."""

from __future__ import annotations

import os
import re
import sys
from typing import Any

_ENV_KEY_VARS = ("EMBER_AI_API_KEY", "OPENROUTER_API_KEY")
_SK_SHAPE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def scrub_secrets(text: str) -> str:
    """Return `text` with key-shaped secrets replaced by `REDACTED`.

    Replaces the exact `EMBER_AI_API_KEY` / `OPENROUTER_API_KEY` values read
    from `os.environ`, and any `sk-`-shaped token.
    """
    for var in _ENV_KEY_VARS:
        value = os.environ.get(var)
        if value:
            text = text.replace(value, "REDACTED")
    return _SK_SHAPE.sub("REDACTED", text)


class EmberError(Exception):
    """Base error for every Ember failure. Carries a stable code and name."""

    code: str = "EMBER-000"
    name: str = "EmberError"

    def __init__(self, message: str, **context: Any) -> None:
        self.message = message
        self.context = context
        self.location = _caller_location()
        super().__init__(message)

    def log_line(self) -> str:
        parts = [f"{self.code} {self.name}", self.location, self.message]
        details = " ".join(f"{key}={value}" for key, value in self.context.items())
        if details:
            parts.append(details)
        return scrub_secrets(" | ".join(parts))


def _caller_location() -> str:
    frame = sys._getframe(2)
    module = frame.f_globals.get("__name__", "?")
    return f"{module}.{frame.f_code.co_name}"

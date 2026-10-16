"""Single project error base with stable codes and no secrets."""

from __future__ import annotations

import sys
from typing import Any


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
        return " | ".join(parts)


def _caller_location() -> str:
    frame = sys._getframe(2)
    module = frame.f_globals.get("__name__", "?")
    return f"{module}.{frame.f_code.co_name}"

"""Write port for the raw AI answers (Phase 3.5, Constitution D8 + I16).

The adapter owns the SQL. The engine core only knows this protocol, so it never
imports `sqlite3` or an adapter module.
"""

from __future__ import annotations

from typing import Protocol


class AiResponseStorePort(Protocol):
    def save(self, *, item_id: int, raw_response: str) -> None:
        """Store one raw provider answer verbatim against `item_id`.

        Raise `ValueError` when the owner pair is invalid (both or neither of
        `source_id`/`item_id` set), and the adapter's own write error class on a
        persistence failure.
        """
        ...

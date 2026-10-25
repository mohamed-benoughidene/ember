"""MAINTAIN-010 coverage for every `SqliteMaintainContext` read."""

from __future__ import annotations

import sqlite3
from typing import Callable

import pytest

from ember.adapters.sqlite import SqliteMaintainContext
from ember.maintain.errors import ItemsReadFailed


class BrokenConnection:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise sqlite3.OperationalError("boom")


_READS = [
    ("list_items", lambda ctx: ctx.list_items()),
    ("list_confirmed_links", lambda ctx: ctx.list_confirmed_links()),
    ("list_reversed_link_ids", lambda ctx: ctx.list_reversed_link_ids()),
]


@pytest.mark.parametrize("name, read", _READS, ids=[name for name, _ in _READS])
def test_read_failure_raises_maintain_010(
    name: str,
    read: Callable[[SqliteMaintainContext], object],
) -> None:
    context = SqliteMaintainContext(BrokenConnection())

    with pytest.raises(ItemsReadFailed) as exc:
        read(context)

    assert exc.value.code == "MAINTAIN-010", name

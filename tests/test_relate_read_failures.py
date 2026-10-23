"""RELATE-016 coverage for every `SqliteLinkContext` read."""

from __future__ import annotations

import sqlite3
from typing import Callable

import pytest

from ember.adapters.sqlite import SqliteLinkContext
from ember.relate.errors import ItemsReadFailed


class BrokenConnection:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise sqlite3.OperationalError("boom")


_READS = [
    ("item_exists", lambda ctx: ctx.item_exists(1)),
    ("item_type", lambda ctx: ctx.item_type(1)),
    ("item_statement", lambda ctx: ctx.item_statement(1)),
    ("item_created_at", lambda ctx: ctx.item_created_at(1)),
    ("find_existing", lambda ctx: ctx.find_existing(1, 2, "supports")),
    ("existing_link_types", lambda ctx: ctx.existing_link_types(1)),
    ("list_other_items", lambda ctx: ctx.list_other_items(1)),
    ("find_latest_unlinked_active", lambda ctx: ctx.find_latest_unlinked_active()),
    ("item_status", lambda ctx: ctx.item_status(1)),
    ("supersedes_ancestors", lambda ctx: ctx.supersedes_ancestors(1)),
]


@pytest.mark.parametrize("name, read", _READS, ids=[name for name, _ in _READS])
def test_read_failure_raises_relate_016(
    name: str,
    read: Callable[[SqliteLinkContext], object],
) -> None:
    context = SqliteLinkContext(BrokenConnection())

    with pytest.raises(ItemsReadFailed) as exc:
        read(context)

    assert exc.value.code == "RELATE-016", name

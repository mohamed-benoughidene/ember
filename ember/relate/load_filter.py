"""Phase 1 core: load the new item and build the candidate universe.

Pure logic. Items and links are read only through `LinkLookupPort`, so the
core writes no SQL and touches no driver.
"""

from __future__ import annotations

from pydantic import BaseModel

from ember.relate.compat import LINK_TYPES, allowed_link_types
from ember.relate.errors import ItemIdNotFound, ItemsReadFailed
from ember.relate.link_lookup import LinkLookupPort
from ember.relate.rows import CandidateUniverse, NewItem


class LoadedCandidates(BaseModel):
    new_item: NewItem
    universe: CandidateUniverse


def resolve_new_item(
    lookup: LinkLookupPort,
    *,
    item_id: int | None,
    latest: bool,
    db_path: str,
) -> NewItem | None:
    """Load the new item to relate, or return None when `--latest` finds none.

    Raises ValueError when not exactly one of `item_id` / `latest` is given,
    ItemIdNotFound when `item_id` is not in the DB, and ItemsReadFailed when a
    row disappears between the existence check and the field reads.
    """
    if (item_id is None) == (not latest):
        raise ValueError("exactly one of item_id or latest is required")
    if item_id is None:
        return lookup.find_latest_unlinked_active()
    if not lookup.item_exists(item_id):
        raise ItemIdNotFound(
            f"item {item_id} not found in {db_path}",
            item_id=item_id,
            db_path=db_path,
        )
    item_type = lookup.item_type(item_id)
    statement = lookup.item_statement(item_id)
    created_at = lookup.item_created_at(item_id)
    if item_type is None or statement is None or created_at is None:
        raise ItemsReadFailed("item row missing during read", item_id=item_id)
    return NewItem(
        id=item_id,
        type=item_type,
        statement=statement,
        created_at=created_at,
    )


def build_candidate_universe(
    lookup: LinkLookupPort,
    new_item: NewItem,
) -> CandidateUniverse:
    """Keep items with a link type that is both unused and type-compatible.

    Filter #1 drops link types already linked from the new item to a candidate
    (any status). Filter #2 drops candidates with no type-compatible link type.
    The port's order is preserved.
    """
    survivors: list[NewItem] = []
    for candidate in lookup.list_other_items(new_item.id):
        if candidate.id == new_item.id:
            continue
        viable = {
            link_type
            for link_type in LINK_TYPES
            if lookup.find_existing(new_item.id, candidate.id, link_type) is None
        }
        if viable & allowed_link_types(new_item.type, candidate.type):
            survivors.append(candidate)
    return CandidateUniverse(items=survivors)


def load_and_filter(
    lookup: LinkLookupPort,
    *,
    item_id: int | None = None,
    latest: bool = False,
    db_path: str,
) -> LoadedCandidates | None:
    """Resolve the new item and its filtered candidates. None is a soft exit."""
    new_item = resolve_new_item(
        lookup,
        item_id=item_id,
        latest=latest,
        db_path=db_path,
    )
    if new_item is None:
        return None
    return LoadedCandidates(
        new_item=new_item,
        universe=build_candidate_universe(lookup, new_item),
    )

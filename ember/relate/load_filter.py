"""Phase 1 core: load the new item and build the candidate universe.

Pure logic. Items and links are read only through `LinkLookupPort`, so the
core writes no SQL and touches no driver.
"""

from __future__ import annotations

from pydantic import BaseModel

from ember.relate.compat import allowed_link_types
from ember.relate.errors import ItemIdNotFound, ItemsReadFailed
from ember.relate.link_lookup import LinkLookupPort
from ember.relate.rows import CandidateUniverse, NewItem


class LoadedCandidates(BaseModel):
    new_item: NewItem
    universe: CandidateUniverse


def _read_item(
    lookup: LinkLookupPort, *, item_id: int, db_path: str
) -> NewItem:
    """Read one item by id, or raise a named error."""
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
    # None is the legal unlabeled shape, so it never trips the missing-row
    # check above.
    metadata = lookup.item_metadata(item_id)
    return NewItem(
        id=item_id,
        type=item_type,
        statement=statement,
        created_at=created_at,
        metadata=metadata,
    )


def load_item_candidates(
    lookup: LinkLookupPort, *, item_id: int, db_path: str
) -> LoadedCandidates:
    """Load one item by id and return its filtered candidate universe."""
    new_item = _read_item(lookup, item_id=item_id, db_path=db_path)
    return LoadedCandidates(
        new_item=new_item,
        universe=build_candidate_universe(lookup, new_item),
    )


def load_latest_candidates(
    lookup: LinkLookupPort,
) -> LoadedCandidates | None:
    """Load the newest unrelated Active item. None is the soft exit."""
    new_item = lookup.find_latest_unlinked_active()
    if new_item is None:
        return None
    return LoadedCandidates(
        new_item=new_item,
        universe=build_candidate_universe(lookup, new_item),
    )


def build_candidate_universe(
    lookup: LinkLookupPort,
    new_item: NewItem,
) -> CandidateUniverse:
    """Keep items with a link type that is both unused and type-compatible.

    Filter #1 reads every existing outgoing link once and subtracts its
    link types per candidate (any status). Filter #2 drops candidates with no
    type-compatible link type. The port's order is preserved.
    """
    existing = lookup.existing_link_types(new_item.id)
    survivors: list[NewItem] = []
    for candidate in lookup.list_other_items(new_item.id):
        if candidate.id == new_item.id:
            continue
        allowed = allowed_link_types(new_item.type, candidate.type)
        if not allowed:
            continue
        if allowed - existing.get(candidate.id, set()):
            survivors.append(candidate)
    return CandidateUniverse(items=survivors)

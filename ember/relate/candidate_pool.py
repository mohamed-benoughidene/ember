"""Phase 2 core: build the ranked candidate pool from three signals.

Content (cached embeddings), graph (1-hop Confirmed neighbors), and metadata
(`created_at` inside a 30-day window) each produce a candidate set; the merge
unions them, scoring a candidate with the highest signal cosine it earned.
Cosine math is stdlib `math` only and every cache, link, and model call goes
through a port, so this module reads no database driver and knows no model.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from math import sqrt
from typing import TextIO

from ember.relate.embedder import EmbedderPort
from ember.relate.embedding_store import EmbeddingStorePort
from ember.relate.errors import (
    CosineComputeFailed,
    EmbedderEncodeFailed,
    EmbeddingWriteFailed,
    GraphReadFailed,
    MetadataReadFailed,
    RelateError,
)
from ember.relate.link_lookup import LinkLookupPort
from ember.relate.load_filter import LoadedCandidates
from ember.relate.rows import NewItem, RankedCandidate, SignalKind

MODEL_CHANGED_LINE = (
    "embedding model changed: wiping cache (this is a one-time minutes-long cost on large DBs)"
)
CONTENT_TOP_K = 10
FLAT_COSINE = 0.5
METADATA_WINDOW = timedelta(days=30)


def build_candidate_pool(
    loaded: LoadedCandidates,
    *,
    link_lookup: LinkLookupPort,
    embedding_store: EmbeddingStorePort,
    embedder: EmbedderPort,
    stderr: TextIO = sys.stderr,
    counts_out: dict[str, int] | None = None,
) -> list[RankedCandidate]:
    """Run the three Phase 2 signals and return the merged, ranked pool.

    Pre-flight wipes a vector cache written by a different embedding model,
    with one STDERR warning and no error code. An empty universe returns `[]`
    before any encode. `counts_out`, when given, receives the raw pre-merge
    signal sizes under `dense`, `graph`, and `metadata`.
    """
    model = embedder.model_name()
    _check_model_change(embedding_store, model=model, stderr=stderr)
    items = loaded.universe.items
    if not items:
        _write_counts(counts_out, dense=0, graph=0, metadata=0)
        return []
    new_item = loaded.new_item
    new_vector = _resolve_vector(new_item, embedder, embedding_store, model=model)
    content = _content_signal(items, new_vector, embedder, embedding_store, model=model)
    graph = _graph_signal(link_lookup, items, new_item_id=new_item.id)
    metadata = _metadata_signal(items, new_item)
    _write_counts(
        counts_out, dense=len(content), graph=len(graph), metadata=len(metadata)
    )
    return _merge(items, content=content, graph=graph, metadata=metadata)


def _check_model_change(
    store: EmbeddingStorePort, *, model: str, stderr: TextIO
) -> None:
    """Wipe a cache written by another embedder, warning once on STDERR."""
    cached = store.first_model_name()
    if cached is None or cached == model:
        return
    print(MODEL_CHANGED_LINE, file=stderr)
    store.wipe()


def _resolve_vector(
    item: NewItem,
    embedder: EmbedderPort,
    store: EmbeddingStorePort,
    *,
    model: str,
) -> list[float]:
    """Return the item's vector from the cache, or encode it and cache it."""
    cached = store.get(item.id)
    if cached is not None and store.model_name_of(item.id) == model:
        return cached
    vector = _encode(embedder, item, model=model)
    _write_vector(store, item.id, vector, model=model)
    return vector


def _content_signal(
    items: list[NewItem],
    new_vector: list[float],
    embedder: EmbedderPort,
    store: EmbeddingStorePort,
    *,
    model: str,
) -> dict[int, float]:
    """Score every universe item by cosine, keeping the top `CONTENT_TOP_K`."""
    scores: dict[int, float] = {}
    for item in items:
        vector = _resolve_vector(item, embedder, store, model=model)
        scores[item.id] = _cosine(new_vector, vector)
    order = sorted(scores, key=lambda item_id: (-scores[item_id], item_id))
    return {item_id: scores[item_id] for item_id in order[:CONTENT_TOP_K]}


def _graph_signal(
    link_lookup: LinkLookupPort,
    items: list[NewItem],
    *,
    new_item_id: int,
) -> set[int]:
    """Return the 1-hop neighbors that survived the Phase 1 filter."""
    try:
        neighbors = link_lookup.neighbors_of(new_item_id)
    except RelateError:
        raise
    except Exception as error:  # noqa: BLE001 - a failed read is a graph read failure
        raise GraphReadFailed("neighbor read failed", item_id=new_item_id) from error
    universe = {item.id for item in items}
    return {neighbor_id for neighbor_id in neighbors if neighbor_id in universe}


def _metadata_signal(items: list[NewItem], new_item: NewItem) -> set[int]:
    """Return the universe items created within `METADATA_WINDOW` of the new item."""
    new_created_at = _parse_created_at(new_item.created_at, item_id=new_item.id)
    kept: set[int] = set()
    for item in items:
        created_at = _parse_created_at(item.created_at, item_id=item.id)
        if _within_window(created_at, new_created_at, item_id=item.id):
            kept.add(item.id)
    return kept


def _parse_created_at(value: str, *, item_id: int) -> datetime:
    """Parse an ISO TEXT timestamp; a malformed value becomes RELATE-023."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise MetadataReadFailed(
            "created_at is not an ISO timestamp", item_id=item_id, value=value
        ) from error


def _within_window(
    created_at: datetime, new_created_at: datetime, *, item_id: int
) -> bool:
    """Report whether two timestamps sit inside the metadata window.

    A naive/aware mix cannot be subtracted; that type failure becomes RELATE-023
    like a malformed value does.
    """
    try:
        distance = abs(created_at - new_created_at)
    except TypeError as error:
        raise MetadataReadFailed(
            "created_at timezone mismatch", item_id=item_id
        ) from error
    return distance <= METADATA_WINDOW


def _merge(
    items: list[NewItem],
    *,
    content: dict[int, float],
    graph: set[int],
    metadata: set[int],
) -> list[RankedCandidate]:
    """Union the signals: highest cosine wins, source is dense > graph > metadata."""
    by_id = {item.id: item for item in items}
    scores: dict[int, float] = {}
    sources: dict[int, SignalKind] = {}
    for item_id, cosine in content.items():
        scores[item_id] = cosine
        sources[item_id] = SignalKind.dense
    for item_id in graph:
        scores[item_id] = max(scores.get(item_id, FLAT_COSINE), FLAT_COSINE)
        sources.setdefault(item_id, SignalKind.graph)
    for item_id in metadata:
        scores[item_id] = max(scores.get(item_id, FLAT_COSINE), FLAT_COSINE)
        sources.setdefault(item_id, SignalKind.metadata)
    order = sorted(scores, key=lambda item_id: (-scores[item_id], item_id))
    return [
        RankedCandidate(
            item=by_id[item_id],
            cosine=scores[item_id],
            source=sources[item_id],
        )
        for item_id in order
    ]


def _encode(embedder: EmbedderPort, item: NewItem, *, model: str) -> list[float]:
    """Encode one statement; any embedder failure becomes RELATE-018.

    An `EmbedderLoadFailed` (RELATE-017) or any other `RelateError` is already
    named and is re-raised unchanged.
    """
    try:
        vectors = embedder.embed([item.statement])
    except RelateError:
        raise
    except Exception as error:  # noqa: BLE001 - every model failure is an encode fail
        raise EmbedderEncodeFailed(
            "embedder encode failed", item_id=item.id, model=model
        ) from error
    if len(vectors) != 1:
        raise EmbedderEncodeFailed(
            "embedder returned the wrong vector count",
            item_id=item.id,
            count=len(vectors),
        )
    return list(vectors[0])


def _write_vector(
    store: EmbeddingStorePort,
    item_id: int,
    vector: list[float],
    *,
    model: str,
) -> None:
    """Cache one vector; any store failure becomes RELATE-019.

    An already-named `RelateError` from the port is re-raised unchanged.
    """
    try:
        store.upsert(item_id, vector, model)
    except RelateError:
        raise
    except Exception as error:  # noqa: BLE001 - every store failure is a write fail
        raise EmbeddingWriteFailed(
            "embedding cache write failed", item_id=item_id, model=model
        ) from error


def _write_counts(
    counts_out: dict[str, int] | None,
    *,
    dense: int,
    graph: int,
    metadata: int,
) -> None:
    """Record the raw pre-merge signal sizes for the CLI's debug line."""
    if counts_out is None:
        return
    counts_out["dense"] = dense
    counts_out["graph"] = graph
    counts_out["metadata"] = metadata


def _cosine(left: list[float], right: list[float]) -> float:
    """Return the cosine similarity of two vectors, clamped to `[-1.0, 1.0]`.

    Stdlib `math` only. Unequal lengths and a zero denominator (a zero or
    corrupted cache vector) both raise RELATE-022.
    """
    if len(left) != len(right):
        raise CosineComputeFailed(
            "embedding length mismatch", left=len(left), right=len(right)
        )
    dot = 0.0
    left_squares = 0.0
    right_squares = 0.0
    for left_value, right_value in zip(left, right):
        dot += left_value * right_value
        left_squares += left_value * left_value
        right_squares += right_value * right_value
    denominator = sqrt(left_squares) * sqrt(right_squares)
    if denominator == 0.0:
        raise CosineComputeFailed("zero-vector embedding", length=len(left))
    score = dot / denominator
    return max(-1.0, min(1.0, score))

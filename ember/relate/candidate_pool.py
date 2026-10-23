"""Phase 2 core: build the ranked candidate pool from three signals.

Content (cached embeddings), graph (1-hop Confirmed neighbors), and metadata
(`created_at` inside a 30-day window) each produce a candidate set; the merge
unions them, scoring a candidate with the highest signal cosine it earned.
Cosine math is stdlib `math` only and every cache, link, and model call goes
through a port, so this module reads no database driver and knows no model.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import sqrt

from ember.relate.embedder import EmbedderPort
from ember.relate.embedding_store import EmbeddingStorePort
from ember.relate.errors import CosineComputeFailed, MetadataReadFailed
from ember.relate.link_lookup import LinkLookupPort
from ember.relate.load_filter import LoadedCandidates
from ember.relate.rows import NewItem, Pool, RankedCandidate, SignalKind

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
) -> Pool:
    """Run the three Phase 2 signals and return the merged, ranked pool.

    Inputs: the Phase 1 `LoadedCandidates` plus the three ports. `link_lookup`
    reads 1-hop neighbors, `embedding_store` reads and writes the vector cache,
    and `embedder` turns statements into vectors.

    Output: `Pool(ranked, counts, warning)`. `ranked` is sorted by cosine
    descending, then item id ascending. `counts` holds the pre-merge signal
    sizes under `dense`, `graph`, and `metadata`. `warning` is the model-change
    text, or None.

    Raises (propagated from the ports and the two core helpers):
    - `RELATE-037 EmbeddingReadFailed` when a cache read fails.
    - `RELATE-018 EmbedderEncodeFailed` when the model cannot encode.
    - `RELATE-019 EmbeddingWriteFailed` when a cache write or wipe fails.
    - `RELATE-021 GraphReadFailed` when the neighbor read fails.
    - `RELATE-022 CosineComputeFailed` on a zero or unequal-length vector.
    - `RELATE-023 MetadataReadFailed` on a malformed or mixed-zone timestamp.
    - `RELATE-017 EmbedderLoadFailed` if the model failed to load.

    Side effects: may upsert vectors into `item_embeddings`, and may wipe the
    cache (returning `warning`) when the cached model differs from the active
    model. The caller prints `warning`; this module writes no output itself.
    """
    model = embedder.model_name()
    warning = _model_change_warning(embedding_store, model=model)
    items = loaded.universe.items
    if not items:
        return Pool(
            ranked=[],
            counts={"dense": 0, "graph": 0, "metadata": 0},
            warning=warning,
        )
    new_item = loaded.new_item
    new_vector = _resolve_vector(new_item, embedder, embedding_store, model=model)
    content = _content_signal(items, new_vector, embedder, embedding_store, model=model)
    graph = _graph_signal(link_lookup, items, new_item_id=new_item.id)
    metadata = _metadata_signal(items, new_item)
    return Pool(
        ranked=_merge(items, content=content, graph=graph, metadata=metadata),
        counts={
            "dense": len(content),
            "graph": len(graph),
            "metadata": len(metadata),
        },
        warning=warning,
    )


def _model_change_warning(store: EmbeddingStorePort, *, model: str) -> str | None:
    """Wipe a cache written by another embedder and return the warning text."""
    cached = store.first_model_name()
    if cached is None or cached == model:
        return None
    store.wipe()
    return MODEL_CHANGED_LINE


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
    vector = list(embedder.embed([item.statement])[0])
    store.upsert(item.id, vector, model)
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
    neighbors = link_lookup.neighbors_of(new_item_id)
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
    """Parse an ISO TEXT timestamp; a malformed value raises RELATE-023."""
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

    A naive/aware mix cannot be subtracted; that type failure raises RELATE-023
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


def _cosine(left: list[float], right: list[float]) -> float:
    """Return the cosine similarity of two vectors, clamped to `[-1.0, 1.0]`.

    Stdlib `math` only. Unequal lengths and a zero denominator (a zero or
    corrupted cache vector) both raise `RELATE-022`.
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

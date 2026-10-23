"""Unit tests for relate phase 2 (candidate pool), no DB and no model.

Every test drives the core through `build_candidate_pool` and reads the `Pool`
it returns (`ranked`, `counts`, `warning`). Nothing here imports a private
helper and nothing asserts a call count: the observable contract is the pool
plus the cache state the run leaves behind (Constitution T6).

The three ports are the only seam. They either serve canned data or raise:
the expected-failure tests prove the core re-raises the port's named error
unchanged, and the generic-failure tests prove a code bug is never wrapped
(Constitution I5).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ember.relate.candidate_pool import build_candidate_pool
from ember.relate.errors import (
    CosineComputeFailed,
    EmbedderEncodeFailed,
    EmbedderLoadFailed,
    EmbeddingReadFailed,
    EmbeddingWriteFailed,
    GraphReadFailed,
    ItemsReadFailed,
    MetadataReadFailed,
    RelateError,
)
from ember.relate.load_filter import LoadedCandidates
from ember.relate.rows import (
    CandidateUniverse,
    Link,
    NewItem,
    Pool,
    RankedCandidate,
    SignalKind,
)
from tests.relate.fakes import FakeEmbedder, FakeEmbeddingStore, FakeLinkLookup

MODEL = "fake-model"
NEW_TIME = "2026-06-15T00:00:00+00:00"
FAR_DAYS = 200
# Id 90 is never in a universe, so its cached row proves a wipe really ran.
DROPPED_ID = 90
WARNING_LINE = (
    "embedding model changed: wiping cache (this is a one-time minutes-long cost on large DBs)"
)


def _stamp(days: int) -> str:
    return (datetime.fromisoformat(NEW_TIME) + timedelta(days=days)).isoformat()


def _item(item_id: int, *, days: int = 0, item_type: str = "Finding") -> NewItem:
    return NewItem(
        id=item_id,
        type=item_type,
        statement=f"statement {item_id}",
        created_at=_stamp(days),
    )


def _link(
    link_id: int,
    source_id: int,
    target_id: int,
    *,
    status: str = "Confirmed",
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_id,
        target_item_id=target_id,
        link_type="contradicts",
        status=status,
        created_at=NEW_TIME,
    )


def _loaded(new_item: NewItem, items: list[NewItem]) -> LoadedCandidates:
    return LoadedCandidates(new_item=new_item, universe=CandidateUniverse(items=items))


def _candidate() -> LoadedCandidates:
    """A one-item universe far outside the metadata window."""
    return _loaded(_item(1), [_item(2, days=FAR_DAYS)])


def _build(
    loaded: LoadedCandidates,
    *,
    embedder: FakeEmbedder,
    store: FakeEmbeddingStore,
    lookup: FakeLinkLookup | None = None,
) -> Pool:
    return build_candidate_pool(
        loaded,
        link_lookup=FakeLinkLookup(items=[]) if lookup is None else lookup,
        embedding_store=store,
        embedder=embedder,
    )


def _scored(ranked: list[RankedCandidate]) -> list[tuple[int, float | None]]:
    return [(candidate.item.id, candidate.cosine) for candidate in ranked]


def _ids_with_source(ranked: list[RankedCandidate], kind: SignalKind) -> list[int]:
    return sorted(c.item.id for c in ranked if c.source is kind)


def _upsert_ids(store: FakeEmbeddingStore) -> list[int]:
    return [item_id for item_id, _, _ in store.upserts]


def _low_cosine_vectors(*item_ids: int) -> dict[str, list[float]]:
    """Vectors orthogonal to the new item, so those ids fall out of the top 10."""
    return {f"statement {item_id}": [0.0, 1.0, 0.0] for item_id in item_ids}


class _NoEncodeEmbedder(FakeEmbedder):
    """Fails the test when the core asks the model for a vector."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError(f"embed must not be called, got {texts}")


class _EmptyEmbedder(FakeEmbedder):
    """Returns no vectors, which the port contract forbids: a code bug."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return []


class _NoNeighborLookup(FakeLinkLookup):
    """Fails the test when the graph signal reads neighbors."""

    def neighbors_of(self, item_id: int) -> list[int]:
        raise AssertionError("neighbors_of must not be called")


class _FailingNeighborLookup(FakeLinkLookup):
    """Raises a canned error from the neighbor read."""

    def __init__(self, items: list[NewItem], *, error: Exception) -> None:
        super().__init__(items)
        self._error = error

    def neighbors_of(self, item_id: int) -> list[int]:
        raise self._error


class _RepeatingNeighborLookup(FakeLinkLookup):
    """Returns repeated and unknown neighbor ids, as a sloppy reader might."""

    def __init__(self, items: list[NewItem], *, neighbors: list[int]) -> None:
        super().__init__(items)
        self._neighbors = list(neighbors)

    def neighbors_of(self, item_id: int) -> list[int]:
        return list(self._neighbors)


class _UntouchedStore(FakeEmbeddingStore):
    """Fails the test on any per-item cache read or write."""

    def get(self, item_id: int) -> list[float] | None:
        raise AssertionError(f"get must not be called (item {item_id})")

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        raise AssertionError(f"upsert must not be called (item {item_id})")


class _FailingStore(FakeEmbeddingStore):
    """Raises a canned error from whichever cache-port methods are set."""

    def __init__(
        self,
        *,
        get_error: Exception | None = None,
        upsert_error: Exception | None = None,
        wipe_error: Exception | None = None,
        model_name_of_error: Exception | None = None,
        first_model_name_error: Exception | None = None,
        rows: dict[int, list[float]] | None = None,
        model_name: str = MODEL,
    ) -> None:
        super().__init__(rows, model_name=model_name)
        self._get_error = get_error
        self._upsert_error = upsert_error
        self._wipe_error = wipe_error
        self._model_name_of_error = model_name_of_error
        self._first_model_name_error = first_model_name_error

    def get(self, item_id: int) -> list[float] | None:
        if self._get_error is not None:
            raise self._get_error
        return super().get(item_id)

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        if self._upsert_error is not None:
            raise self._upsert_error
        super().upsert(item_id, vector, model_name)

    def wipe(self) -> None:
        if self._wipe_error is not None:
            raise self._wipe_error
        super().wipe()

    def model_name_of(self, item_id: int) -> str | None:
        if self._model_name_of_error is not None:
            raise self._model_name_of_error
        return super().model_name_of(item_id)

    def first_model_name(self) -> str | None:
        if self._first_model_name_error is not None:
            raise self._first_model_name_error
        return super().first_model_name()


def _ports_with_failure(
    method: str, error: Exception
) -> tuple[FakeEmbedder, FakeEmbeddingStore, FakeLinkLookup]:
    """Build the three ports so `method` raises `error` and every other call works."""
    new_item = _item(1)
    items = [_item(2, days=FAR_DAYS)]
    lookup = FakeLinkLookup([new_item, *items])
    cached_new_item = {1: [1.0, 0.0, 0.0]}
    if method == "embed":
        # No cached row, so the new item must be encoded.
        return FakeEmbedder(error=error, model_name=MODEL), FakeEmbeddingStore(
            model_name=MODEL
        ), lookup
    if method == "get":
        return FakeEmbedder(model_name=MODEL), _FailingStore(get_error=error), lookup
    if method == "upsert":
        return FakeEmbedder(model_name=MODEL), _FailingStore(upsert_error=error), lookup
    if method == "wipe":
        return (
            FakeEmbedder(model_name=MODEL),
            _FailingStore(
                wipe_error=error,
                rows={DROPPED_ID: [9.0, 9.0, 9.0]},
                model_name="old-model",
            ),
            lookup,
        )
    if method == "first_model_name":
        return (
            FakeEmbedder(model_name=MODEL),
            _FailingStore(first_model_name_error=error),
            lookup,
        )
    if method == "model_name_of":
        return (
            FakeEmbedder(model_name=MODEL),
            _FailingStore(
                model_name_of_error=error, rows=cached_new_item, model_name=MODEL
            ),
            lookup,
        )
    if method == "neighbors_of":
        return (
            FakeEmbedder(model_name=MODEL),
            FakeEmbeddingStore(cached_new_item, model_name=MODEL),
            _FailingNeighborLookup([new_item, *items], error=error),
        )
    raise AssertionError(f"unknown port method {method}")


# --- pool shape, counts, and the pre-flight warning -------------------------


def test_empty_universe_returns_an_empty_pool_without_running_signals() -> None:
    store = _UntouchedStore(model_name=MODEL)

    pool = _build(
        _loaded(_item(1), []),
        embedder=_NoEncodeEmbedder(model_name=MODEL),
        store=store,
        lookup=_NoNeighborLookup(items=[]),
    )

    assert pool.ranked == []
    assert pool.counts == {"dense": 0, "graph": 0, "metadata": 0}
    assert pool.warning is None
    assert store.rows == {}
    assert store.model_names == {}
    assert store.upserts == []


def test_empty_universe_still_reports_a_model_change_warning() -> None:
    store = _UntouchedStore({DROPPED_ID: [9.0, 9.0, 9.0]}, model_name="old-model")

    pool = _build(
        _loaded(_item(1), []),
        embedder=_NoEncodeEmbedder(model_name=MODEL),
        store=store,
        lookup=_NoNeighborLookup(items=[]),
    )

    assert pool.ranked == []
    assert pool.counts == {"dense": 0, "graph": 0, "metadata": 0}
    assert pool.warning == WARNING_LINE
    # The dropped id's row is gone, so the pre-flight wipe really ran.
    assert store.rows == {}
    assert store.model_names == {}
    assert store.upserts == []


# --- content signal --------------------------------------------------------


def test_content_only_scores_the_cache_and_caches_every_encoded_vector() -> None:
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 7)]
    vectors = {
        "statement 3": [1.0, 1.0, 0.0],
        "statement 4": [0.0, 1.0, 0.0],
        "statement 5": [-1.0, 0.0, 0.0],
        "statement 6": [2.0, 0.0, 0.0],
    }
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore(
        {1: [1.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        model_name=MODEL,
    )

    pool = _build(_loaded(_item(1), items), embedder=embedder, store=store)

    assert [
        (item_id, round(cosine, 6)) for item_id, cosine in _scored(pool.ranked)
    ] == [
        (2, 1.0),
        (6, 1.0),
        (3, 0.707107),
        (4, 0.0),
        (5, -1.0),
    ]
    assert [candidate.source for candidate in pool.ranked] == [SignalKind.dense] * 5
    assert pool.counts == {"dense": 5, "graph": 0, "metadata": 0}
    assert pool.warning is None
    # Item 2 was served by the cache; 3-6 were encoded and cached under MODEL.
    assert store.rows == {
        1: [1.0, 0.0, 0.0],
        2: [1.0, 0.0, 0.0],
        3: [1.0, 1.0, 0.0],
        4: [0.0, 1.0, 0.0],
        5: [-1.0, 0.0, 0.0],
        6: [2.0, 0.0, 0.0],
    }
    assert store.model_names == {item_id: MODEL for item_id in range(1, 7)}
    assert _upsert_ids(store) == [3, 4, 5, 6]


def test_content_signal_keeps_only_the_top_ten_by_cosine() -> None:
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 15)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)

    pool = _build(_loaded(_item(1), items), embedder=embedder, store=store)

    assert [candidate.item.id for candidate in pool.ranked] == list(range(2, 12))
    assert pool.counts == {"dense": 10, "graph": 0, "metadata": 0}


def test_content_ties_break_by_item_id_ascending() -> None:
    items = [_item(item_id, days=FAR_DAYS) for item_id in (9, 3, 7, 2, 5)]
    embedder = FakeEmbedder(model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)

    pool = _build(_loaded(_item(1), items), embedder=embedder, store=store)

    assert [candidate.item.id for candidate in pool.ranked] == [2, 3, 5, 7, 9]
    assert {candidate.cosine for candidate in pool.ranked} == {1.0}
    assert pool.counts == {"dense": 5, "graph": 0, "metadata": 0}


# --- graph signal ----------------------------------------------------------


def test_graph_only_keeps_universe_neighbors_with_flat_cosine() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 15)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup(
        [new_item, *items],
        [_link(101, 1, 12), _link(102, 1, 13), _link(103, 1, 14)],
    )

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
    )
    by_id = {candidate.item.id: candidate for candidate in pool.ranked}

    assert pool.counts == {"dense": 10, "graph": 3, "metadata": 0}
    assert [candidate.item.id for candidate in pool.ranked] == list(range(2, 15))
    for item_id in (12, 13, 14):
        assert by_id[item_id].source is SignalKind.graph
        assert by_id[item_id].cosine == 0.5
    assert by_id[11].source is SignalKind.dense


def test_graph_signal_dedupes_and_drops_ids_outside_the_universe() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 14)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = _RepeatingNeighborLookup(
        [new_item, *items],
        neighbors=[13, 13, 999, 12, 12],
    )

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
    )

    assert pool.counts == {"dense": 10, "graph": 2, "metadata": 0}
    assert _ids_with_source(pool.ranked, SignalKind.graph) == [12, 13]
    assert 999 not in {candidate.item.id for candidate in pool.ranked}


# --- metadata signal -------------------------------------------------------


def test_metadata_only_keeps_items_inside_the_thirty_day_window() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 12)]
    items += [_item(12, days=10), _item(13, days=-20), _item(14, days=-90)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)

    pool = _build(_loaded(new_item, items), embedder=embedder, store=store)
    by_id = {candidate.item.id: candidate for candidate in pool.ranked}

    assert pool.counts == {"dense": 10, "graph": 0, "metadata": 2}
    assert by_id[12].source is SignalKind.metadata
    assert by_id[12].cosine == 0.5
    assert by_id[13].source is SignalKind.metadata
    assert by_id[13].cosine == 0.5
    assert 14 not in by_id


def test_metadata_window_is_inclusive_at_thirty_days() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 12)]
    items += [_item(12, days=30), _item(13, days=-31), _item(14, days=-30)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)

    pool = _build(_loaded(new_item, items), embedder=embedder, store=store)

    assert pool.counts == {"dense": 10, "graph": 0, "metadata": 2}
    assert _ids_with_source(pool.ranked, SignalKind.metadata) == [12, 14]
    assert 13 not in {candidate.item.id for candidate in pool.ranked}


# --- merge and source priority --------------------------------------------


def test_union_of_content_and_graph_keeps_one_dense_entry() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 14)]
    vectors = {"statement 11": [0.6, 0.8, 0.0]}
    vectors.update(_low_cosine_vectors(12, 13))
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup([new_item, *items], [_link(101, 1, 11)])

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
    )
    shared = [candidate for candidate in pool.ranked if candidate.item.id == 11]

    assert pool.counts == {"dense": 10, "graph": 1, "metadata": 0}
    assert [candidate.item.id for candidate in pool.ranked] == list(range(2, 12))
    assert len(shared) == 1
    assert shared[0].cosine == pytest.approx(0.6)
    assert shared[0].source is SignalKind.dense


def test_merge_takes_the_higher_graph_cosine_but_keeps_the_dense_source() -> None:
    """The flat 0.5 outranks a weak content cosine; `source` still marks dense."""
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 14)]
    vectors = {"statement 11": [0.28, 0.96, 0.0]}
    vectors.update(_low_cosine_vectors(12, 13))
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup([new_item, *items], [_link(101, 1, 11)])

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
    )
    shared = [candidate for candidate in pool.ranked if candidate.item.id == 11]

    assert pool.counts == {"dense": 10, "graph": 1, "metadata": 0}
    assert len(shared) == 1
    assert shared[0].cosine == 0.5
    assert shared[0].source is SignalKind.dense


def test_merge_prefers_graph_source_over_metadata_when_both_match() -> None:
    """A neighbor inside the date window keeps the stronger `graph` source."""
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 13)]
    items.append(_item(13, days=5))
    embedder = FakeEmbedder(_low_cosine_vectors(13), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup([new_item, *items], [_link(101, 1, 13)])

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
    )
    shared = [candidate for candidate in pool.ranked if candidate.item.id == 13]

    assert pool.counts == {"dense": 10, "graph": 1, "metadata": 1}
    assert len(shared) == 1
    assert shared[0].cosine == 0.5
    assert shared[0].source is SignalKind.graph


def test_merge_prefers_dense_source_when_all_three_signals_match() -> None:
    """An item in content, graph, and metadata keeps the content cosine and source."""
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 12)]
    items.append(_item(12, days=5))
    vectors = {"statement 12": [0.6, 0.8, 0.0]}
    vectors.update(_low_cosine_vectors(*range(2, 12)))
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup([new_item, *items], [_link(101, 1, 12)])

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
    )
    shared = [candidate for candidate in pool.ranked if candidate.item.id == 12]

    assert pool.counts == {"dense": 10, "graph": 1, "metadata": 1}
    assert len(shared) == 1
    # The 0.6 content cosine outranks the flat 0.5 bump from graph and metadata.
    assert shared[0].cosine == pytest.approx(0.6)
    assert shared[0].source is SignalKind.dense


# --- pre-flight model check and the cache contract -------------------------


def test_preflight_model_change_wipes_the_cache_and_reencodes() -> None:
    items = [_item(2, days=FAR_DAYS), _item(3, days=FAR_DAYS)]
    vectors = {
        "statement 1": [1.0, 0.0, 0.0],
        "statement 2": [1.0, 0.0, 0.0],
        "statement 3": [0.0, 1.0, 0.0],
    }
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore(
        {2: [0.5, 0.5, 0.5], 3: [0.5, 0.5, 0.5], DROPPED_ID: [0.5, 0.5, 0.5]},
        model_name="old-model",
    )

    pool = _build(_loaded(_item(1), items), embedder=embedder, store=store)

    assert pool.warning == WARNING_LINE
    # The row for an id outside the universe is gone: the wipe really ran.
    assert store.rows == {
        1: [1.0, 0.0, 0.0],
        2: [1.0, 0.0, 0.0],
        3: [0.0, 1.0, 0.0],
    }
    assert store.model_names == {1: MODEL, 2: MODEL, 3: MODEL}
    assert _upsert_ids(store) == [1, 2, 3]
    assert pool.counts == {"dense": 2, "graph": 0, "metadata": 0}
    assert _scored(pool.ranked) == [(2, 1.0), (3, 0.0)]


def test_preflight_with_matching_model_name_uses_the_cache() -> None:
    cached = {
        1: [1.0, 0.0, 0.0],
        2: [1.0, 0.0, 0.0],
        3: [0.0, 1.0, 0.0],
    }
    store = FakeEmbeddingStore(cached, model_name=MODEL)

    pool = _build(
        _loaded(_item(1), [_item(2, days=FAR_DAYS), _item(3, days=FAR_DAYS)]),
        embedder=_NoEncodeEmbedder(model_name=MODEL),
        store=store,
    )

    assert pool.warning is None
    assert store.rows == cached
    assert store.model_names == {item_id: MODEL for item_id in cached}
    assert store.upserts == []
    assert _scored(pool.ranked) == [(2, 1.0), (3, 0.0)]


def test_stale_per_item_model_name_reencodes_only_that_item() -> None:
    store = FakeEmbeddingStore(
        {1: [1.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0], 3: [0.0, 1.0, 0.0]},
        model_name=MODEL,
    )
    store.model_names[3] = "stale-model"
    embedder = FakeEmbedder({"statement 3": [1.0, 0.0, 0.0]}, model_name=MODEL)

    pool = _build(
        _loaded(_item(1), [_item(2, days=FAR_DAYS), _item(3, days=FAR_DAYS)]),
        embedder=embedder,
        store=store,
    )

    assert pool.warning is None
    assert store.rows == {
        1: [1.0, 0.0, 0.0],
        2: [1.0, 0.0, 0.0],
        3: [1.0, 0.0, 0.0],
    }
    assert store.model_names == {1: MODEL, 2: MODEL, 3: MODEL}
    assert store.upserts == [(3, [1.0, 0.0, 0.0], MODEL)]
    assert _scored(pool.ranked) == [(2, 1.0), (3, 1.0)]


# --- cosine contract, exercised through the pool ---------------------------


@pytest.mark.parametrize(
    ("new_vector", "candidate_vector"),
    [
        ([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
        ([1.0, 0.0, 0.0], [0.0, 0.0, 0.0]),
    ],
    ids=["new-item-zero", "cached-candidate-zero"],
)
def test_zero_vector_embedding_raises_relate_022(
    new_vector: list[float], candidate_vector: list[float]
) -> None:
    store = FakeEmbeddingStore(
        {1: new_vector, 2: candidate_vector},
        model_name=MODEL,
    )

    with pytest.raises(CosineComputeFailed) as excinfo:
        _build(
            _candidate(),
            embedder=_NoEncodeEmbedder(model_name=MODEL),
            store=store,
        )

    assert excinfo.value.code == "RELATE-022"
    assert excinfo.value.context == {"length": 3}


def test_unequal_length_embedding_raises_relate_022() -> None:
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0], 2: [1.0, 0.0]}, model_name=MODEL)

    with pytest.raises(CosineComputeFailed) as excinfo:
        _build(
            _candidate(),
            embedder=_NoEncodeEmbedder(model_name=MODEL),
            store=store,
        )

    assert excinfo.value.code == "RELATE-022"
    assert excinfo.value.context == {"left": 3, "right": 2}


@pytest.mark.parametrize(
    ("new_vector", "candidate_vector", "expected"),
    [
        pytest.param([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], 1.0, id="parallel"),
        pytest.param([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], -1.0, id="antiparallel"),
        pytest.param([3.0, 4.0, 0.0], [3.0, 4.0, 0.0], 1.0, id="diagonal"),
        pytest.param([1.0, 0.0, 0.0], [5.0, 0.0, 0.0], 1.0, id="scale-free"),
        pytest.param([1.0, 2.0, 3.0], [3.0, -1.0, 2.0], 0.5, id="half"),
        pytest.param([0.5, 0.5], [0.5, -0.5], 0.0, id="orthogonal"),
        pytest.param([0.149, 0.05], [0.149, 0.05], 1.0, id="float-noise-clamped"),
    ],
)
def test_pool_cosines_stay_in_the_closed_unit_range(
    new_vector: list[float], candidate_vector: list[float], expected: float
) -> None:
    store = FakeEmbeddingStore(
        {1: new_vector, 2: candidate_vector},
        model_name=MODEL,
    )

    pool = _build(
        _candidate(),
        embedder=_NoEncodeEmbedder(model_name=MODEL),
        store=store,
    )

    assert pool.counts == {"dense": 1, "graph": 0, "metadata": 0}
    (candidate,) = pool.ranked
    assert candidate.cosine == pytest.approx(expected)
    # The raw ratio for the noise case is 1.0000000000000002: clamping is required.
    assert -1.0 <= candidate.cosine <= 1.0
    assert candidate.source is SignalKind.dense


# --- expected port failures propagate as the port's named error ------------


def test_embedder_encode_failure_for_the_new_item_propagates_relate_018() -> None:
    error = EmbedderEncodeFailed("model exploded", model=MODEL)
    embedder = FakeEmbedder(error=error, model_name=MODEL)

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        _build(
            _candidate(),
            embedder=embedder,
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-018"
    assert excinfo.value is error


def test_embedder_encode_failure_in_the_content_loop_propagates_relate_018() -> None:
    error = EmbedderEncodeFailed("model exploded", model=MODEL)
    embedder = FakeEmbedder(error=error, model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store)

    assert excinfo.value.code == "RELATE-018"
    assert excinfo.value is error


def test_embedder_load_failure_is_reraised_unchanged() -> None:
    error = EmbedderLoadFailed("sentence-transformers is not installed", model=MODEL)
    embedder = FakeEmbedder(error=error, model_name=MODEL)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        _build(
            _candidate(),
            embedder=embedder,
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-017"
    assert excinfo.value is error


@pytest.mark.parametrize("method", ["get", "first_model_name"])
def test_store_read_failure_propagates_relate_037(method: str) -> None:
    error = EmbeddingReadFailed("cache row unreadable", item_id=1)
    embedder, store, lookup = _ports_with_failure(method, error)

    with pytest.raises(EmbeddingReadFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value.code == "RELATE-037"
    assert excinfo.value is error


def test_store_write_failure_for_the_new_item_propagates_relate_019() -> None:
    error = EmbeddingWriteFailed("disk full")
    embedder, store, lookup = _ports_with_failure("upsert", error)

    with pytest.raises(EmbeddingWriteFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value.code == "RELATE-019"
    assert excinfo.value is error


def test_store_write_failure_in_the_content_loop_propagates_relate_019() -> None:
    error = EmbeddingWriteFailed("disk full")
    store = _FailingStore(upsert_error=error, rows={1: [1.0, 0.0, 0.0]})
    embedder = FakeEmbedder(model_name=MODEL)

    with pytest.raises(EmbeddingWriteFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store)

    assert excinfo.value.code == "RELATE-019"
    assert excinfo.value is error


def test_store_wipe_failure_propagates_relate_019() -> None:
    error = EmbeddingWriteFailed("cache is read-only")
    embedder, store, lookup = _ports_with_failure("wipe", error)

    with pytest.raises(EmbeddingWriteFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value.code == "RELATE-019"
    assert excinfo.value is error


def test_graph_read_failure_propagates_relate_021() -> None:
    error = GraphReadFailed("links table is gone", item_id=1)
    embedder, store, lookup = _ports_with_failure("neighbors_of", error)

    with pytest.raises(GraphReadFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value.code == "RELATE-021"
    assert excinfo.value is error


def test_unexpected_named_store_error_is_reraised_unchanged() -> None:
    error = ItemsReadFailed("cache row unreadable", item_id=1)
    embedder, store, lookup = _ports_with_failure("upsert", error)

    with pytest.raises(ItemsReadFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value.code == "RELATE-016"
    assert excinfo.value is error


def test_unexpected_named_graph_error_is_reraised_unchanged() -> None:
    error = ItemsReadFailed("link read fail", item_id=1)
    embedder, store, lookup = _ports_with_failure("neighbors_of", error)

    with pytest.raises(ItemsReadFailed) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value.code == "RELATE-016"
    assert excinfo.value is error


def test_embedder_returning_no_vectors_crashes_loudly() -> None:
    """The vector-count check lives in the adapter, so a short reply is a bug."""
    with pytest.raises(IndexError):
        _build(
            _candidate(),
            embedder=_EmptyEmbedder(model_name=MODEL),
            store=FakeEmbeddingStore(model_name=MODEL),
        )


@pytest.mark.parametrize(
    "method",
    [
        "embed",
        "get",
        "upsert",
        "wipe",
        "first_model_name",
        "model_name_of",
        "neighbors_of",
    ],
)
def test_generic_port_bug_propagates_unchanged(method: str) -> None:
    """A code bug is never wrapped into a RELATE-xxx code (Constitution I5)."""
    error = RuntimeError(f"{method} is buggy")
    embedder, store, lookup = _ports_with_failure(method, error)

    with pytest.raises(RuntimeError) as excinfo:
        _build(_candidate(), embedder=embedder, store=store, lookup=lookup)

    assert excinfo.value is error
    assert not isinstance(excinfo.value, RelateError)


# --- metadata failures stay in the core -----------------------------------


def test_malformed_candidate_created_at_maps_to_relate_023() -> None:
    items = [
        NewItem(
            id=2,
            type="Finding",
            statement="statement 2",
            created_at="yesterday",
        )
    ]

    with pytest.raises(MetadataReadFailed) as excinfo:
        _build(
            _loaded(_item(1), items),
            embedder=FakeEmbedder(model_name=MODEL),
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-023"
    assert excinfo.value.context["item_id"] == 2


def test_malformed_new_item_created_at_maps_to_relate_023() -> None:
    new_item = NewItem(id=1, type="Finding", statement="statement 1", created_at="")

    with pytest.raises(MetadataReadFailed) as excinfo:
        _build(
            _loaded(new_item, [_item(2, days=FAR_DAYS)]),
            embedder=FakeEmbedder(model_name=MODEL),
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-023"
    assert excinfo.value.context["item_id"] == 1


def test_naive_and_aware_created_at_mix_maps_to_relate_023() -> None:
    items = [
        NewItem(
            id=2,
            type="Finding",
            statement="statement 2",
            created_at="2026-06-15T00:00:00",
        )
    ]

    with pytest.raises(MetadataReadFailed) as excinfo:
        _build(
            _loaded(_item(1), items),
            embedder=FakeEmbedder(model_name=MODEL),
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-023"
    assert excinfo.value.context["item_id"] == 2

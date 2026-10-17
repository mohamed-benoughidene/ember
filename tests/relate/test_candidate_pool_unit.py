"""Unit tests for relate phase 2 (candidate pool), no DB and no model."""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO

import pytest

from ember.relate.candidate_pool import _cosine, build_candidate_pool
from ember.relate.errors import (
    CosineComputeFailed,
    EmbedderEncodeFailed,
    EmbedderLoadFailed,
    EmbeddingWriteFailed,
    GraphReadFailed,
    ItemsReadFailed,
    MetadataReadFailed,
)
from ember.relate.load_filter import LoadedCandidates
from ember.relate.rows import (
    CandidateUniverse,
    Link,
    NewItem,
    RankedCandidate,
    SignalKind,
)
from tests.relate.fakes import FakeEmbedder, FakeEmbeddingStore, FakeLinkLookup

MODEL = "fake-model"
NEW_TIME = "2026-06-15T00:00:00+00:00"
FAR_DAYS = 200
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


def _build(
    loaded: LoadedCandidates,
    *,
    embedder: FakeEmbedder,
    store: FakeEmbeddingStore,
    lookup: FakeLinkLookup | None = None,
    stderr: StringIO | None = None,
    counts_out: dict[str, int] | None = None,
) -> list[RankedCandidate]:
    return build_candidate_pool(
        loaded,
        link_lookup=FakeLinkLookup(items=[]) if lookup is None else lookup,
        embedding_store=store,
        embedder=embedder,
        stderr=StringIO() if stderr is None else stderr,
        counts_out=counts_out,
    )


def _scored(pool: list[RankedCandidate]) -> list[tuple[int, float | None]]:
    return [(candidate.item.id, candidate.cosine) for candidate in pool]


def _ids_with_source(pool: list[RankedCandidate], kind: SignalKind) -> list[int]:
    return sorted(c.item.id for c in pool if c.source is kind)


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


class _FailingUpsertStore(FakeEmbeddingStore):
    """Fails upserts for `fail_ids`, or for every id when it is None."""

    def __init__(
        self,
        error: Exception,
        *,
        fail_ids: set[int] | None = None,
        rows: dict[int, list[float]] | None = None,
        model_name: str = MODEL,
    ) -> None:
        super().__init__(rows, model_name=model_name)
        self._error = error
        self._fail_ids = fail_ids

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        if self._fail_ids is None or item_id in self._fail_ids:
            raise self._error
        super().upsert(item_id, vector, model_name)


class _GuardedStore(FakeEmbeddingStore):
    """Records reads and writes so a test can prove none happened."""

    def __init__(self) -> None:
        super().__init__()
        self.gets: list[int] = []
        self.upsert_ids: list[int] = []
        self.first_model_calls = 0

    def get(self, item_id: int) -> list[float] | None:
        self.gets.append(item_id)
        return super().get(item_id)

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        self.upsert_ids.append(item_id)
        super().upsert(item_id, vector, model_name)

    def first_model_name(self) -> str | None:
        self.first_model_calls += 1
        return super().first_model_name()


def _low_cosine_vectors(*item_ids: int) -> dict[str, list[float]]:
    """Vectors orthogonal to the new item, so those ids fall out of the top 10."""
    return {f"statement {item_id}": [0.0, 1.0, 0.0] for item_id in item_ids}


def test_empty_universe_returns_empty_without_running_signals() -> None:
    store = _GuardedStore()
    embedder = FakeEmbedder(model_name=MODEL)
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(_item(1), []),
        embedder=embedder,
        store=store,
        lookup=_NoNeighborLookup(items=[]),
        counts_out=counts,
    )

    assert pool == []
    assert counts == {"dense": 0, "graph": 0, "metadata": 0}
    assert embedder.calls == []
    assert store.gets == []
    assert store.upsert_ids == []
    assert store.wipes == 0
    assert store.first_model_calls == 1


def test_empty_universe_without_counts_sink_returns_empty() -> None:
    loaded = _loaded(_item(1), [])

    pool = _build(
        loaded,
        embedder=FakeEmbedder(model_name=MODEL),
        store=FakeEmbeddingStore(model_name=MODEL),
    )

    assert pool == []


def test_content_only_scores_one_cached_and_four_encoded_vectors() -> None:
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
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(_item(1), items),
        embedder=embedder,
        store=store,
        counts_out=counts,
    )

    assert [(candidate.item.id, round(candidate.cosine, 6)) for candidate in pool] == [
        (2, 1.0),
        (6, 1.0),
        (3, 0.707107),
        (4, 0.0),
        (5, -1.0),
    ]
    assert [candidate.source for candidate in pool] == [SignalKind.dense] * 5
    assert len(embedder.calls) == 4
    assert sorted(text for call in embedder.calls for text in call) == [
        "statement 3",
        "statement 4",
        "statement 5",
        "statement 6",
    ]
    assert [item_id for item_id, _, _ in store.upserts] == [3, 4, 5, 6]
    assert sorted(store.rows) == [1, 2, 3, 4, 5, 6]
    assert counts == {"dense": 5, "graph": 0, "metadata": 0}


def test_content_signal_keeps_only_the_top_ten_by_cosine() -> None:
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 15)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(_item(1), items),
        embedder=embedder,
        store=store,
        counts_out=counts,
    )

    assert [candidate.item.id for candidate in pool] == list(range(2, 12))
    assert counts == {"dense": 10, "graph": 0, "metadata": 0}


def test_content_ties_break_by_item_id_ascending() -> None:
    items = [_item(item_id, days=FAR_DAYS) for item_id in (9, 3, 7, 2, 5)]
    embedder = FakeEmbedder(model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)

    pool = _build(_loaded(_item(1), items), embedder=embedder, store=store)

    assert [candidate.item.id for candidate in pool] == [2, 3, 5, 7, 9]
    assert {candidate.cosine for candidate in pool} == {1.0}


def test_graph_only_keeps_universe_neighbors_with_flat_cosine() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 15)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup(
        [new_item, *items],
        [_link(101, 1, 12), _link(102, 1, 13), _link(103, 1, 14)],
    )
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
        counts_out=counts,
    )
    by_id = {candidate.item.id: candidate for candidate in pool}

    assert counts == {"dense": 10, "graph": 3, "metadata": 0}
    assert [candidate.item.id for candidate in pool] == list(range(2, 15))
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
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
        counts_out=counts,
    )
    graph_ids = _ids_with_source(pool, SignalKind.graph)

    assert counts == {"dense": 10, "graph": 2, "metadata": 0}
    assert graph_ids == [12, 13]
    assert 999 not in {candidate.item.id for candidate in pool}


def test_metadata_only_keeps_items_inside_the_thirty_day_window() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 12)]
    items += [_item(12, days=10), _item(13, days=-20), _item(14, days=-90)]
    embedder = FakeEmbedder(_low_cosine_vectors(12, 13, 14), model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        counts_out=counts,
    )
    by_id = {candidate.item.id: candidate for candidate in pool}

    assert counts == {"dense": 10, "graph": 0, "metadata": 2}
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
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        counts_out=counts,
    )
    metadata_ids = _ids_with_source(pool, SignalKind.metadata)

    assert counts == {"dense": 10, "graph": 0, "metadata": 2}
    assert metadata_ids == [12, 14]
    assert 13 not in {candidate.item.id for candidate in pool}


def test_union_of_content_and_graph_keeps_one_dense_entry() -> None:
    new_item = _item(1)
    items = [_item(item_id, days=FAR_DAYS) for item_id in range(2, 14)]
    vectors = {"statement 11": [0.6, 0.8, 0.0]}
    vectors.update(_low_cosine_vectors(12, 13))
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    lookup = FakeLinkLookup([new_item, *items], [_link(101, 1, 11)])
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
        counts_out=counts,
    )
    shared = [candidate for candidate in pool if candidate.item.id == 11]

    assert counts == {"dense": 10, "graph": 1, "metadata": 0}
    assert [candidate.item.id for candidate in pool] == list(range(2, 12))
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
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(new_item, items),
        embedder=embedder,
        store=store,
        lookup=lookup,
        counts_out=counts,
    )
    shared = [candidate for candidate in pool if candidate.item.id == 11]

    assert counts == {"dense": 10, "graph": 1, "metadata": 0}
    assert len(shared) == 1
    assert shared[0].cosine == 0.5
    assert shared[0].source is SignalKind.dense


def test_preflight_model_change_wipes_the_cache_and_reencodes() -> None:
    items = [_item(2, days=FAR_DAYS), _item(3, days=FAR_DAYS)]
    vectors = {
        "statement 1": [1.0, 0.0, 0.0],
        "statement 2": [1.0, 0.0, 0.0],
        "statement 3": [0.0, 1.0, 0.0],
    }
    embedder = FakeEmbedder(vectors, model_name=MODEL)
    store = FakeEmbeddingStore(
        {2: [0.5, 0.5, 0.5], 3: [0.5, 0.5, 0.5]},
        model_name="old-model",
    )
    stderr = StringIO()
    counts: dict[str, int] = {}

    pool = _build(
        _loaded(_item(1), items),
        embedder=embedder,
        store=store,
        stderr=stderr,
        counts_out=counts,
    )

    assert store.wipes == 1
    assert stderr.getvalue() == WARNING_LINE + "\n"
    assert sorted(text for call in embedder.calls for text in call) == [
        "statement 1",
        "statement 2",
        "statement 3",
    ]
    assert store.model_names == {1: MODEL, 2: MODEL, 3: MODEL}
    assert counts == {"dense": 2, "graph": 0, "metadata": 0}
    assert _scored(pool) == [(2, 1.0), (3, 0.0)]


def test_preflight_with_matching_model_name_uses_the_cache() -> None:
    store = FakeEmbeddingStore(
        {1: [1.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0], 3: [0.0, 1.0, 0.0]},
        model_name=MODEL,
    )
    embedder = FakeEmbedder(model_name=MODEL)
    stderr = StringIO()

    pool = _build(
        _loaded(_item(1), [_item(2, days=FAR_DAYS), _item(3, days=FAR_DAYS)]),
        embedder=embedder,
        store=store,
        stderr=stderr,
    )

    assert stderr.getvalue() == ""
    assert store.wipes == 0
    assert embedder.calls == []
    assert store.upserts == []
    assert _scored(pool) == [(2, 1.0), (3, 0.0)]


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

    assert store.wipes == 0
    assert embedder.calls == [["statement 3"]]
    assert [item_id for item_id, _, _ in store.upserts] == [3]
    assert _scored(pool) == [(2, 1.0), (3, 1.0)]


def test_cosine_zero_vector_raises_relate_022() -> None:
    with pytest.raises(CosineComputeFailed) as excinfo:
        _cosine([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])

    assert excinfo.value.code == "RELATE-022"


def test_cached_zero_vector_raises_relate_022() -> None:
    store = FakeEmbeddingStore({1: [0.0, 0.0, 0.0]}, model_name=MODEL)
    embedder = FakeEmbedder(model_name=MODEL)

    with pytest.raises(CosineComputeFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=store,
        )

    assert excinfo.value.code == "RELATE-022"


def test_cosine_unequal_lengths_raises_relate_022() -> None:
    with pytest.raises(CosineComputeFailed) as excinfo:
        _cosine([1.0, 0.0], [1.0, 0.0, 0.0])

    assert excinfo.value.code == "RELATE-022"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], 1.0),
        ([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], -1.0),
        ([3.0, 4.0, 0.0], [3.0, 4.0, 0.0], 1.0),
        ([1.0, 2.0, 3.0], [3.0, -1.0, 2.0], 0.5),
        ([0.5, 0.5], [0.5, -0.5], 0.0),
    ],
)
def test_cosine_of_normal_vectors_stays_in_range(
    left: list[float], right: list[float], expected: float
) -> None:
    score = _cosine(left, right)

    assert score == pytest.approx(expected)
    assert -1.0 <= score <= 1.0


def test_embed_failure_for_the_new_item_maps_to_relate_018() -> None:
    embedder = FakeEmbedder(error=RuntimeError("model exploded"), model_name=MODEL)

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-018"
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_embed_failure_in_the_content_loop_maps_to_relate_018() -> None:
    store = FakeEmbeddingStore({1: [1.0, 0.0, 0.0]}, model_name=MODEL)
    embedder = FakeEmbedder(error=RuntimeError("model exploded"), model_name=MODEL)

    with pytest.raises(EmbedderEncodeFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=store,
        )

    assert excinfo.value.code == "RELATE-018"


def test_embedder_load_failure_is_reraised_unchanged() -> None:
    error = EmbedderLoadFailed("sentence-transformers is not installed", model=MODEL)
    embedder = FakeEmbedder(error=error, model_name=MODEL)

    with pytest.raises(EmbedderLoadFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=FakeEmbeddingStore(model_name=MODEL),
        )

    assert excinfo.value.code == "RELATE-017"
    assert excinfo.value is error


def test_upsert_failure_for_the_new_item_maps_to_relate_019() -> None:
    store = _FailingUpsertStore(RuntimeError("disk full"))
    embedder = FakeEmbedder({"statement 1": [1.0, 0.0, 0.0]}, model_name=MODEL)

    with pytest.raises(EmbeddingWriteFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=store,
        )

    assert excinfo.value.code == "RELATE-019"


def test_upsert_failure_in_the_content_loop_maps_to_relate_019() -> None:
    store = _FailingUpsertStore(
        RuntimeError("disk full"),
        fail_ids={2},
        rows={1: [1.0, 0.0, 0.0]},
    )
    embedder = FakeEmbedder({"statement 2": [1.0, 0.0, 0.0]}, model_name=MODEL)

    with pytest.raises(EmbeddingWriteFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=store,
        )

    assert excinfo.value.code == "RELATE-019"


def test_named_store_error_is_reraised_unchanged() -> None:
    error = ItemsReadFailed("cache row unreadable", item_id=1)
    store = _FailingUpsertStore(error)
    embedder = FakeEmbedder({"statement 1": [1.0, 0.0, 0.0]}, model_name=MODEL)

    with pytest.raises(ItemsReadFailed) as excinfo:
        _build(
            _loaded(_item(1), [_item(2, days=FAR_DAYS)]),
            embedder=embedder,
            store=store,
        )

    assert excinfo.value.code == "RELATE-016"
    assert excinfo.value is error


def test_neighbor_read_failure_maps_to_relate_021() -> None:
    new_item = _item(1)
    items = [_item(2, days=FAR_DAYS)]
    lookup = _FailingNeighborLookup([new_item, *items], error=RuntimeError("db closed"))

    with pytest.raises(GraphReadFailed) as excinfo:
        _build(
            _loaded(new_item, items),
            embedder=FakeEmbedder(model_name=MODEL),
            store=FakeEmbeddingStore(model_name=MODEL),
            lookup=lookup,
        )

    assert excinfo.value.code == "RELATE-021"
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_named_graph_error_is_reraised_unchanged() -> None:
    new_item = _item(1)
    items = [_item(2, days=FAR_DAYS)]
    error = ItemsReadFailed("link read fail", item_id=1)
    lookup = _FailingNeighborLookup([new_item, *items], error=error)

    with pytest.raises(ItemsReadFailed) as excinfo:
        _build(
            _loaded(new_item, items),
            embedder=FakeEmbedder(model_name=MODEL),
            store=FakeEmbeddingStore(model_name=MODEL),
            lookup=lookup,
        )

    assert excinfo.value.code == "RELATE-016"
    assert excinfo.value is error


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

"""Integration tests for relate phase 2 (candidate pool) on a real SQLite DB.

Plan step 2 section 6 asks for three real-DB targets: a seeded pool, a
pre-warmed embedding cache, and the pre-flight model mismatch. Each runs the
real `SqliteLinkContext`, `SqliteEmbedderStore`, and `load_item_candidates`
against a migrated temp database; only the model is faked, with fixed 384-dim
vectors so the cosine order is known (plan section 12.2 records the 384-dim
fake; the real bge-base model is 768).

`build_candidate_pool` returns a `Pool(ranked, counts, warning)` and writes no
output itself: the pre-flight model-change warning comes back in
`Pool.warning` for the CLI to print, so these tests assert on the returned
value instead of capturing STDERR. The cache assertions read the observable
`item_embeddings` rows (`embedded_at` and the packed vector blob), not fake
call counts.

Every candidate is type-compatible with the new item, and the universe holds
at most ten items, so the content signal keeps all of them: `dense` always
equals the universe size. The graph and metadata signals still contribute
their raw pre-merge counts and bump a member's flat cosine to 0.5 when its
own content cosine is lower.

A fourth test drives the RELATE-021 graph read failure through
`build_candidate_pool` by dropping the `links` table, so the real
`SqliteLinkContext.neighbors_of` raises and the core re-raises it unchanged.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from math import sqrt

import pytest

from ember.adapters.sqlite import (
    SqliteEmbedderStore,
    SqliteLinkContext,
    open_database,
)
from ember.relate.candidate_pool import MODEL_CHANGED_LINE, build_candidate_pool
from ember.relate.errors import GraphReadFailed
from ember.relate.load_filter import load_item_candidates
from ember.relate.rows import SignalKind
from tests.fakes import FIXED_TIME, insert_item, insert_source
from tests.relate.fakes import FakeEmbedder

DIM = 384
MODEL = "fake-model"
NEW_TIME = "2026-06-15T00:00:00+00:00"
# Far outside the 30-day metadata window (roughly 530 days before NEW_TIME).
FAR_TIME = "2025-01-01T00:00:00+00:00"
NEAR_PLUS = (datetime.fromisoformat(NEW_TIME) + timedelta(days=10)).isoformat()
NEAR_MINUS = (datetime.fromisoformat(NEW_TIME) - timedelta(days=10)).isoformat()

NEW_STATEMENT = "the new finding"


def _unit(cosine: float) -> list[float]:
    """A 384-dim unit vector whose cosine against the new item's basis is `cosine`.

    The new item's vector is the first basis vector `e0`, so putting `cosine`
    on the first axis and the matching sine on the second makes the cosine
    against `e0` equal to `cosine` while keeping the vector unit length.
    """
    vector = [0.0] * DIM
    vector[0] = cosine
    vector[1] = sqrt(max(0.0, 1.0 - cosine * cosine))
    return vector


def _candidate_statement(item_id: int) -> str:
    return f"candidate {item_id}"


def _insert_link(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    *,
    link_type: str = "supports",
    status: str = "Confirmed",
) -> None:
    conn.execute(
        "INSERT INTO links (source_item_id, target_item_id, link_type, status,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (source_id, target_id, link_type, status, FIXED_TIME),
    )


class _AdvancingClock:
    """A store clock that returns a distinct timestamp per write.

    Any cache write rewrites `embedded_at`, so a distinct value per write keeps
    "the second run changed nothing" observable from the rows alone.
    """

    def __init__(self) -> None:
        self._writes = 0

    def __call__(self) -> str:
        self._writes += 1
        written_at = datetime.fromisoformat(NEW_TIME) + timedelta(seconds=self._writes)
        return written_at.isoformat()


def _embedded_at_by_item(conn: sqlite3.Connection) -> dict[int, str]:
    """Read the `embedded_at` timestamp of every cache row."""
    rows = conn.execute("SELECT item_id, embedded_at FROM item_embeddings").fetchall()
    return {row["item_id"]: row["embedded_at"] for row in rows}


def _vector_blob_by_item(conn: sqlite3.Connection) -> dict[int, bytes]:
    """Read the raw packed vector blob of every cache row."""
    rows = conn.execute("SELECT item_id, vector FROM item_embeddings").fetchall()
    return {row["item_id"]: row["vector"] for row in rows}


def test_seeded_pool_ranks_by_cosine_then_id_and_counts_all_three_signals(
    db_path,
) -> None:
    """Ten candidates: 3 graph-linked, 2 near in time, the rest far away.

    Plan section 6 "10 items seeded" is read as a ten-item candidate universe
    (ids 2-11); id 1 is the new item. The two far-away items are ids 7 and 8;
    ids 9-11 are also placed far in time so the metadata count stays exactly 2.
    """
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type="Finding",
        statement=NEW_STATEMENT,
        created_at=NEW_TIME,
    )
    # ids 2-4 are the graph links; ids 5 and 6 are the near-in-time pair.
    for item_id in range(2, 12):
        if item_id == 5:
            created_at = NEAR_PLUS
        elif item_id == 6:
            created_at = NEAR_MINUS
        else:
            created_at = FAR_TIME
        insert_item(
            conn,
            source_id=source_id,
            item_id=item_id,
            item_type="Decision",
            statement=_candidate_statement(item_id),
            created_at=created_at,
        )
    _insert_link(conn, 1, 2)
    _insert_link(conn, 1, 3)
    _insert_link(conn, 1, 4)
    conn.commit()

    # Distinct content cosines; ids 3, 4 and 6 sit below the 0.5 flat bump.
    cosines = {
        2: 0.9,
        3: 0.3,
        4: 0.3,
        5: 0.7,
        6: 0.2,
        7: 0.1,
        8: 0.0,
        9: -0.1,
        10: -0.2,
        11: -0.3,
    }
    vectors = {NEW_STATEMENT: _unit(1.0)}
    vectors.update({_candidate_statement(i): _unit(c) for i, c in cosines.items()})
    embedder = FakeEmbedder(vectors, model_name=MODEL, dim=DIM)
    store = SqliteEmbedderStore(conn)
    lookup = SqliteLinkContext(conn)

    loaded = load_item_candidates(lookup, item_id=1, db_path=db_path)
    pool = build_candidate_pool(
        loaded,
        link_lookup=lookup,
        embedding_store=store,
        embedder=embedder,
    )

    assert len(loaded.universe.items) == 10
    # A fresh cache is warm from this model only: nothing to warn the user about.
    assert pool.warning is None
    assert pool.counts == {"dense": 10, "graph": 3, "metadata": 2}
    assert len(pool.ranked) == 10
    # Descending cosine; ids 3, 4 and 6 tie at the flat 0.5 and break id ASC.
    assert [candidate.item.id for candidate in pool.ranked] == [
        2,
        5,
        3,
        4,
        6,
        7,
        8,
        9,
        10,
        11,
    ]
    # Every member is in the content signal, so the strongest source is dense.
    assert {candidate.source for candidate in pool.ranked} == {SignalKind.dense}
    scores = {candidate.item.id: candidate.cosine for candidate in pool.ranked}
    assert scores == pytest.approx(
        {
            2: 0.9,
            5: 0.7,
            3: 0.5,
            4: 0.5,
            6: 0.5,
            7: 0.1,
            8: 0.0,
            9: -0.1,
            10: -0.2,
            11: -0.3,
        }
    )


def test_prewarmed_cache_is_reused_on_the_second_run(db_path) -> None:
    """A cache written by the active model is left byte-for-byte untouched."""
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type="Finding",
        statement=NEW_STATEMENT,
        created_at=NEW_TIME,
    )
    for item_id in range(2, 7):
        insert_item(
            conn,
            source_id=source_id,
            item_id=item_id,
            item_type="Decision",
            statement=_candidate_statement(item_id),
            created_at=NEW_TIME,
        )
    conn.commit()

    cached = {
        1: _unit(1.0),
        2: _unit(0.5),
        3: _unit(0.25),
        4: _unit(-0.5),
        5: _unit(-0.25),
        6: _unit(0.0),
    }
    store = SqliteEmbedderStore(conn, clock=_AdvancingClock())
    for item_id, vector in cached.items():
        store.upsert(item_id, vector, MODEL)

    embedded_at_before = _embedded_at_by_item(conn)
    blobs_before = _vector_blob_by_item(conn)
    assert sorted(embedded_at_before) == sorted(cached)
    assert sorted(blobs_before) == sorted(cached)
    # The clock is distinct per write, so "unchanged" below cannot pass vacuously.
    assert len(set(embedded_at_before.values())) == len(cached)

    # A very different vector per statement: if the pool re-encoded, the cached
    # rows would change and the blob comparison below would catch it.
    statements = [NEW_STATEMENT, *(_candidate_statement(i) for i in range(2, 7))]
    embedder = FakeEmbedder(
        {statement: _unit(-1.0) for statement in statements},
        model_name=MODEL,
        dim=DIM,
    )
    lookup = SqliteLinkContext(conn)
    loaded = load_item_candidates(lookup, item_id=1, db_path=db_path)

    for _run in range(2):
        pool = build_candidate_pool(
            loaded,
            link_lookup=lookup,
            embedding_store=store,
            embedder=embedder,
        )
        assert pool.warning is None
        assert len(pool.ranked) == 5
        assert pool.counts == {"dense": 5, "graph": 0, "metadata": 5}

    # Plan section 7: a cache hit does not re-compute, so no row was rewritten.
    assert _embedded_at_by_item(conn) == embedded_at_before
    assert _vector_blob_by_item(conn) == blobs_before
    assert conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0] == 6
    for item_id, vector in cached.items():
        assert store.get(item_id) == pytest.approx(vector)
        assert store.model_name_of(item_id) == MODEL


def test_preflight_model_mismatch_wipes_and_reencodes_every_item(db_path) -> None:
    """An old-model cache is wiped (warning returned), then fully rebuilt."""
    conn = open_database(db_path)
    source_id = insert_source(conn)
    # New item and universe are all Question: ("Question", "Question") allows
    # `supersedes`, so every candidate survives phase 1.
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type="Question",
        statement="the new question",
        created_at=NEW_TIME,
    )
    for item_id in (2, 3, 4):
        insert_item(
            conn,
            source_id=source_id,
            item_id=item_id,
            item_type="Question",
            statement=_candidate_statement(item_id),
            created_at=NEW_TIME,
        )
    # Incompatible with a Question, so phase 1 drops it: its cached row must be
    # gone after the run and it must never be re-encoded.
    insert_item(
        conn,
        source_id=source_id,
        item_id=90,
        item_type="Decision",
        statement="a dropped candidate",
        created_at=NEW_TIME,
    )
    conn.commit()

    store = SqliteEmbedderStore(conn)
    old_vector = [9.0] * DIM
    for item_id in (2, 3, 90):
        store.upsert(item_id, old_vector, "old-model")
    assert store.first_model_name() == "old-model"

    fresh = {
        "the new question": _unit(1.0),
        _candidate_statement(2): _unit(0.9),
        _candidate_statement(3): _unit(0.8),
        _candidate_statement(4): _unit(0.7),
    }
    embedder = FakeEmbedder(fresh, model_name=MODEL, dim=DIM)
    lookup = SqliteLinkContext(conn)
    loaded = load_item_candidates(lookup, item_id=1, db_path=db_path)

    pool = build_candidate_pool(
        loaded,
        link_lookup=lookup,
        embedding_store=store,
        embedder=embedder,
    )

    # The core no longer prints; the CLI prints this returned line.
    assert pool.warning == MODEL_CHANGED_LINE
    assert [item.id for item in loaded.universe.items] == [2, 3, 4]
    # The rebuilt pool ranks the three surviving candidates by fresh cosine.
    assert [candidate.item.id for candidate in pool.ranked] == [2, 3, 4]
    # The cache holds one fresh row per encoded item, and no old-model row.
    assert conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0] == 4
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM item_embeddings WHERE model_name != ?", (MODEL,)
        ).fetchone()[0]
        == 0
    )
    for item_id in (1, 2, 3, 4):
        assert store.model_name_of(item_id) == MODEL
    assert store.get(1) == pytest.approx(fresh["the new question"])
    # The old 9.0 vector for id 2 was replaced by a freshly encoded one.
    assert store.get(2) == pytest.approx(fresh[_candidate_statement(2)])
    assert store.get(2) != pytest.approx(old_vector)
    # id 90 was wiped and never re-encoded: proof the wipe really ran.
    assert store.get(90) is None


def test_graph_read_failure_surfaces_as_relate_021(db_path) -> None:
    """`build_candidate_pool` re-raises the adapter's RELATE-021 unchanged.

    The failure is raised by the real `SqliteLinkContext.neighbors_of`: the
    `links` table is dropped after a successful phase 1 load, so the adapter's
    real read fails and maps the sqlite error to `GraphReadFailed`.
    """
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type="Finding",
        statement=NEW_STATEMENT,
        created_at=NEW_TIME,
    )
    insert_item(
        conn,
        source_id=source_id,
        item_id=2,
        item_type="Decision",
        statement=_candidate_statement(2),
        created_at=NEW_TIME,
    )
    conn.commit()

    lookup = SqliteLinkContext(conn)
    store = SqliteEmbedderStore(conn)
    embedder = FakeEmbedder(
        {NEW_STATEMENT: _unit(1.0), _candidate_statement(2): _unit(0.9)},
        model_name=MODEL,
        dim=DIM,
    )
    loaded = load_item_candidates(lookup, item_id=1, db_path=db_path)

    # Phase 1 has already loaded the universe; now the graph read cannot work.
    conn.execute("DROP TABLE links")

    with pytest.raises(GraphReadFailed) as excinfo:
        build_candidate_pool(
            loaded,
            link_lookup=lookup,
            embedding_store=store,
            embedder=embedder,
        )

    assert excinfo.value.code == "RELATE-021"
    assert excinfo.value.context["item_id"] == 1
    # The real adapter raised it: the sqlite error is the chained cause.
    assert isinstance(excinfo.value.__cause__, sqlite3.Error)

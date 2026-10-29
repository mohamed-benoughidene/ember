"""Measure the real embedding-model-change wipe + re-encode cost (issue #12).

This is a measurement asset, not product code. It answers one question with
numbers: when the cached embedding model name differs from the active model,
how long does the wipe and the full re-encode freeze one `ember relate`
Phase 2 run on a large database?

The script drives the REAL production path, no shortcuts:

- Schema: `open_database` applies the repo's own migrations.
- Seed: `tests/fakes.py` insert helpers write items, links, and the
  `link_confirmed` change_log ledger rows (`insert_link_with_confirmation`).
- Phase 2 warm-up: `build_candidate_pool` with the real `bge-base-en-v1.5`
  embedder so every vector in `item_embeddings` is a real cached encoding.
- Model swap: Phase 2 runs again with a different real sentence-transformers
  model (`all-MiniLM-L6-v2`). The real `_model_change_warning` detects the
  mismatch, wipes the cache, and every item is re-encoded for real.
- Timing: `time.perf_counter` wall clock. Wipe time is clocked by a thin
  wrapper at the `EmbeddingStorePort` boundary, re-encode time by one at the
  `EmbedderPort` boundary. Both delegate unchanged to the real adapters, and
  the total is the whole Phase 2 call.

No paid API is touched: Phase 2 needs no LLM, and `EMBER_AI_API_KEY` is
deleted from the environment before anything runs.

Usage: .venv/bin/python scripts/measure_model_change.py --items 500 [--db PATH]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ember.adapters.embedder import (  # noqa: E402
    EmbeddingStorePort,
    SentenceTransformerEmbedder,
)
from ember.adapters.sqlite import (  # noqa: E402
    SqliteLinkContext,
    build_embedding_store,
    open_database,
)
from ember.relate.candidate_pool import MODEL_CHANGED_LINE, build_candidate_pool  # noqa: E402
from ember.relate.load_filter import load_latest_candidates  # noqa: E402

from tests.fakes import (  # noqa: E402
    insert_item,
    insert_link_with_confirmation,
    insert_source,
)

MODEL_A = "bge-base-en-v1.5"
MODEL_B = "all-MiniLM-L6-v2"
DEFAULT_DB_DIR = Path("/tmp/opencode/measure14")
ITEM_TYPES = ["Decision", "Finding", "Assumption", "Question"]


class TimedEmbeddingStore:
    """Thin timing wrapper at the `EmbeddingStorePort` boundary.

    Every call delegates unchanged to the real `SqliteEmbedderStore`. Only
    `wipe()` is clocked, so the wipe time is the real wipe duration on the
    real database.
    """

    def __init__(self, inner: EmbeddingStorePort) -> None:
        self._inner = inner
        self.wipe_seconds = 0.0

    def get(self, item_id: int) -> object:
        return self._inner.get(item_id)

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        self._inner.upsert(item_id, vector, model_name)

    def model_name_of(self, item_id: int) -> str | None:
        return self._inner.model_name_of(item_id)

    def first_model_name(self) -> str | None:
        return self._inner.first_model_name()

    def wipe(self) -> None:
        start = time.perf_counter()
        self._inner.wipe()
        self.wipe_seconds += time.perf_counter() - start


class TimedEmbedder:
    """Thin timing wrapper at the `EmbedderPort` boundary.

    `embed()` delegates unchanged to the real adapter. The accumulated wall
    time of the real model calls is the re-encode time.
    """

    def __init__(self, inner: SentenceTransformerEmbedder) -> None:
        self._inner = inner
        self.encode_seconds = 0.0
        self.texts = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        rows = self._inner.embed(texts)
        self.encode_seconds += time.perf_counter() - start
        self.texts += len(texts)
        return rows

    def dim(self) -> int:
        return self._inner.dim()

    def model_name(self) -> str:
        return self._inner.model_name()


def seed_database(conn, *, items: int) -> int:
    """Seed the synthetic corpus through the repo's own helpers.

    Returns the id of the new item (the last insert, a Decision with no
    link, so `load_latest_candidates` picks exactly it). Links and their
    `link_confirmed` change_log ledger rows live only between lower-id
    universe items, with link types taken from the repo's compatibility
    table so the migration 011 enforcement triggers accept the rows.
    """
    from ember.relate.compat import allowed_link_types

    source_id = insert_source(conn, "measurement seed text")
    new_item_id = 0
    for index in range(1, items + 1):
        fresh = index == items
        item_type = "Decision" if fresh else ITEM_TYPES[index % len(ITEM_TYPES)]
        statement = (
            f"Decision {index}: keep the item storage heap-local "
            f"for module {index % 37} because boxed in shared stacks hurts"
        )
        item_id = insert_item(conn, source_id=source_id, item_type=item_type, statement=statement)
        if fresh:
            new_item_id = item_id

    # A handful of confirmed links + change_log ledger rows among early
    # universe items. None touches the new item, so it stays the latest
    # unlinked one. Link type must fit the actual type pair (triggers
    # enforce the compatibility table). Pairs with no allowed type are skipped.
    link_count = min(items - 2, 10)
    for index in range(1, link_count + 1):
        source_type = ITEM_TYPES[index % len(ITEM_TYPES)]
        target_type = ITEM_TYPES[(index + 1) % len(ITEM_TYPES)]
        allowed = sorted(allowed_link_types(source_type, target_type))
        if allowed:
            insert_link_with_confirmation(conn, index, index + 1, allowed[0])
    conn.commit()
    return new_item_id


def delete_database(db_file: Path) -> None:
    """Delete the throwaway database, its journal sidecars, and the
    pre-migration backup copies the migration runner creates."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(str(db_file) + suffix)
        if candidate.exists():
            candidate.unlink()
    for backup in db_file.parent.glob(db_file.name + ".bak-v*"):
        backup.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--items", type=int, default=500, help="items to seed (max 5000)")
    parser.add_argument("--db", type=str, default=None, help="throwaway database path")
    args = parser.parse_args()
    if not 1 <= args.items <= 5000:
        parser.error("--items must be between 1 and 5000")

    # No paid API can be touched from this process. Relate Phase 2 needs no
    # LLM, and the embedder model is picked explicitly below.
    os.environ.pop("EMBER_AI_API_KEY", None)
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ.pop("EMBER_EMBEDDER_MODEL", None)
    print("EMBER_AI_API_KEY: unset (no paid API can be reached)")

    if args.db is not None:
        db_file = Path(args.db).resolve()
    else:
        db_file = DEFAULT_DB_DIR / f"model-change-{args.items}.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    delete_database(db_file)  # start fresh. The seed helpers assume an empty file

    conn = open_database(str(db_file))
    lookup = SqliteLinkContext(conn)
    new_item_id = seed_database(conn, items=args.items)
    print(f"seeded {args.items} items + links + change_log rows in {db_file}")

    # Warm-up run: model A encodes the whole corpus for real, the cache is full.
    warm_start = time.perf_counter()
    embedder_a = SentenceTransformerEmbedder(MODEL_A)
    loaded_warm = load_latest_candidates(lookup)
    if loaded_warm is None:
        print("ERROR: no unlinked Active item after seeding, aborting", file=sys.stderr)
        return 1
    if loaded_warm.new_item.id != new_item_id:
        print(
            f"ERROR: unexpected new item id {loaded_warm.new_item.id} "
            f"(expected {new_item_id}), aborting",
            file=sys.stderr,
        )
        return 1
    pool = build_candidate_pool(
        loaded_warm,
        link_lookup=lookup,
        embedding_store=build_embedding_store(conn),
        embedder=embedder_a,
    )
    warm_seconds = time.perf_counter() - warm_start
    cached_model = build_embedding_store(conn).first_model_name()
    if cached_model != MODEL_A:
        print(f"ERROR: warm cache holds model {cached_model!r}, expected {MODEL_A!r}", file=sys.stderr)
        return 1
    print(f"warm run: pool of {len(pool.ranked)} built in {warm_seconds:.2f}s, cache holds {MODEL_A}")

    # Measured run: model B re-points the cached model name, the real
    # `_model_change_warning` wipes, and every item re-encodes for real.
    model_b_load_start = time.perf_counter()
    embedder_b = SentenceTransformerEmbedder(MODEL_B)
    print(f"model B ({MODEL_B}) load took {time.perf_counter() - model_b_load_start:.2f}s (not part of the measurement)")
    loaded = load_latest_candidates(lookup)
    timed_store = TimedEmbeddingStore(build_embedding_store(conn))
    timed_embedder = TimedEmbedder(embedder_b)
    phase2_start = time.perf_counter()
    pool = build_candidate_pool(
        loaded,
        link_lookup=lookup,
        embedding_store=timed_store,
        embedder=timed_embedder,
    )
    phase2_seconds = time.perf_counter() - phase2_start

    try:
        # The CLI prints `pool.warning` to stderr (cli.py `click.echo(..., err=True)`).
        # Mirror that exact path here and fail hard if the line is not the real one.
        print(pool.warning if pool.warning is not None else "(no warning)", file=sys.stderr)
        if pool.warning != MODEL_CHANGED_LINE:
            print(f"ERROR: expected MODEL_CHANGED_LINE, got {pool.warning!r}", file=sys.stderr)
            return 2
    finally:
        conn.close()
        delete_database(db_file)

    encode_speed = timed_embedder.texts / timed_embedder.encode_seconds if timed_embedder.encode_seconds else 0.0
    end_to_end_speed = timed_embedder.texts / phase2_seconds if phase2_seconds else 0.0
    report = (
        "=== model-change wipe + re-encode measurement ===",
        f"dated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"items seeded: {args.items}",
        f"ranked pool size: {len(pool.ranked)}",
        f"items re-encoded in the measured run: {timed_embedder.texts}",
        f"model A (warm cache): {MODEL_A}",
        f"model B (measured run): {MODEL_B}",
        f"warm run, model A builds the whole pool (not measured): {warm_seconds:.2f}s",
        f"wipe time: {timed_store.wipe_seconds:.3f}s",
        f"re-encode time: {timed_embedder.encode_seconds:.2f}s",
        f"total Phase-2 wall-clock: {phase2_seconds:.2f}s",
        f"model encode speed: {encode_speed:.1f} items/sec",
        f"end-to-end Phase-2 speed: {end_to_end_speed:.1f} items/sec",
        "MODEL_CHANGED_LINE on stderr: yes",
        "environment: cpu only, no paid API key set, throwaway database deleted",
    )
    print("=" * 50)
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

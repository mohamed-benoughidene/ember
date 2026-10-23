"""Integration tests for `SqliteEmbedderStore` on a real SQLite DB.

The adapter owns the packed vector format (little-endian float32) and the
`item_embeddings` cache rows. Read failures surface as RELATE-037, write
failures as RELATE-019 (plan step 2 section 5).
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Callable
from datetime import datetime

import pytest

from ember.adapters.sqlite import (
    SqliteEmbedderStore,
    build_embedding_store,
    open_database,
)
from ember.relate.errors import EmbeddingReadFailed, EmbeddingWriteFailed
from tests.fakes import FIXED_TIME, insert_item, insert_source

VECTOR_A = [0.5, -1.25, 3.0, 0.0]
VECTOR_B = [1.0, 2.0, 3.0, 4.0]
MODEL_A = "bge-base-en-v1.5"
MODEL_B = "bge-small-en-v1.5"


class BrokenConnection:
    """A connection whose every statement fails, to drive the failure paths.

    `sqlite3.Connection.execute` is a read-only attribute on an immutable
    type, so a double is the only way to force a database failure (the same
    approach as `tests/test_relate_read_failures.py`).
    """

    def execute(self, *args: object, **kwargs: object) -> object:
        raise sqlite3.OperationalError("boom")


def _seed_items(conn: sqlite3.Connection, count: int) -> None:
    """Insert `count` items, so `item_embeddings` rows have a valid owner."""
    source_id = insert_source(conn)
    for item_id in range(1, count + 1):
        insert_item(conn, source_id=source_id, item_id=item_id)
    conn.commit()


def _vector_blob(conn: sqlite3.Connection, item_id: int) -> bytes:
    row = conn.execute(
        "SELECT vector FROM item_embeddings WHERE item_id = ?", (item_id,)
    ).fetchone()
    return row["vector"]


def test_get_returns_none_on_empty_table(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    assert SqliteEmbedderStore(conn).get(1) is None


def test_get_returns_none_when_the_item_has_no_row(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 2)
    store = SqliteEmbedderStore(conn)
    store.upsert(1, VECTOR_A, MODEL_A)

    assert store.get(2) is None
    assert store.get(999) is None


def test_upsert_then_get_round_trips_the_vector(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)
    store = SqliteEmbedderStore(conn)

    store.upsert(1, VECTOR_A, MODEL_A)

    assert store.get(1) == pytest.approx(VECTOR_A)


def test_round_trip_keeps_float32_precision(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)
    store = SqliteEmbedderStore(conn)
    vector = [0.1, 0.2, -1.0 / 3.0, 1e-4]

    store.upsert(1, vector, MODEL_A)

    assert store.get(1) == pytest.approx(vector, rel=1e-6)


def test_upsert_stores_a_little_endian_float32_blob(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    SqliteEmbedderStore(conn).upsert(1, VECTOR_A, MODEL_A)

    blob = _vector_blob(conn, 1)
    assert isinstance(blob, bytes)
    assert len(blob) == len(VECTOR_A) * 4
    assert struct.unpack(f"<{len(VECTOR_A)}f", blob) == pytest.approx(VECTOR_A)


def test_upsert_stores_model_name_and_embedded_at_from_the_clock(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    SqliteEmbedderStore(conn, clock=lambda: FIXED_TIME).upsert(1, VECTOR_A, MODEL_A)

    row = conn.execute(
        "SELECT model_name, embedded_at FROM item_embeddings WHERE item_id = 1"
    ).fetchone()
    assert row["model_name"] == MODEL_A
    assert row["embedded_at"] == FIXED_TIME


def test_upsert_defaults_to_a_utc_timestamp(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    SqliteEmbedderStore(conn).upsert(1, VECTOR_A, MODEL_A)

    embedded_at = conn.execute(
        "SELECT embedded_at FROM item_embeddings WHERE item_id = 1"
    ).fetchone()["embedded_at"]
    assert datetime.fromisoformat(embedded_at).tzinfo is not None


def test_second_upsert_replaces_the_vector_and_the_model(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)
    store = SqliteEmbedderStore(conn)

    store.upsert(1, VECTOR_A, MODEL_A)
    store.upsert(1, VECTOR_B, MODEL_B)

    assert store.get(1) == pytest.approx(VECTOR_B)
    assert store.model_name_of(1) == MODEL_B
    assert conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0] == 1


def test_model_name_of_returns_the_stored_name(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)
    store = SqliteEmbedderStore(conn)

    assert store.model_name_of(1) is None

    store.upsert(1, VECTOR_A, MODEL_A)

    assert store.model_name_of(1) == MODEL_A


def test_first_model_name_returns_none_on_empty_table(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    assert SqliteEmbedderStore(conn).first_model_name() is None


def test_first_model_name_returns_a_stored_name(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 2)
    store = SqliteEmbedderStore(conn)
    store.upsert(1, VECTOR_A, MODEL_A)
    store.upsert(2, VECTOR_B, MODEL_B)

    assert store.first_model_name() == MODEL_A


def test_wipe_empties_the_table(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 2)
    store = SqliteEmbedderStore(conn)
    store.upsert(1, VECTOR_A, MODEL_A)
    store.upsert(2, VECTOR_B, MODEL_B)

    store.wipe()

    assert store.get(1) is None
    assert store.get(2) is None
    assert store.first_model_name() is None
    assert conn.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0] == 0


def test_wipe_touches_no_item_and_writes_no_change_log_row(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)
    store = SqliteEmbedderStore(conn)
    store.upsert(1, VECTOR_A, MODEL_A)

    store.wipe()

    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0


def test_wipe_on_an_empty_table_is_a_no_op(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    SqliteEmbedderStore(conn).wipe()

    assert SqliteEmbedderStore(conn).first_model_name() is None


def test_build_embedding_store_returns_a_working_store(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)

    store = build_embedding_store(conn)
    store.upsert(1, VECTOR_A, MODEL_A)

    assert store.get(1) == pytest.approx(VECTOR_A)
    assert store.first_model_name() == MODEL_A
    assert store.model_name_of(1) == MODEL_A


def test_corrupt_vector_blob_is_a_read_failure(db_path) -> None:
    conn = open_database(db_path)
    _seed_items(conn, 1)
    conn.execute(
        "INSERT INTO item_embeddings (item_id, vector, model_name, embedded_at)"
        " VALUES (1, ?, 'm', ?)",
        (b"\x00\x01\x02", FIXED_TIME),
    )

    with pytest.raises(EmbeddingReadFailed) as exc:
        SqliteEmbedderStore(conn).get(1)

    assert exc.value.code == "RELATE-037"


_READS: list[tuple[str, Callable[[SqliteEmbedderStore], object]]] = [
    ("get", lambda store: store.get(1)),
    ("model_name_of", lambda store: store.model_name_of(1)),
    ("first_model_name", lambda store: store.first_model_name()),
]

_WRITES: list[tuple[str, Callable[[SqliteEmbedderStore], object]]] = [
    ("upsert", lambda store: store.upsert(1, VECTOR_A, MODEL_A)),
    ("wipe", lambda store: store.wipe()),
]


@pytest.mark.parametrize("name, read", _READS, ids=[name for name, _ in _READS])
def test_read_failure_raises_relate_037(
    name: str,
    read: Callable[[SqliteEmbedderStore], object],
) -> None:
    store = SqliteEmbedderStore(BrokenConnection())

    with pytest.raises(EmbeddingReadFailed) as exc:
        read(store)

    assert exc.value.code == "RELATE-037", name


@pytest.mark.parametrize("name, write", _WRITES, ids=[name for name, _ in _WRITES])
def test_write_failure_raises_relate_019(
    name: str,
    write: Callable[[SqliteEmbedderStore], object],
) -> None:
    store = SqliteEmbedderStore(BrokenConnection())

    with pytest.raises(EmbeddingWriteFailed) as exc:
        write(store)

    assert exc.value.code == "RELATE-019", name


def test_read_failure_on_one_item_names_that_item() -> None:
    store = SqliteEmbedderStore(BrokenConnection())

    with pytest.raises(EmbeddingReadFailed) as exc:
        store.get(7)

    assert exc.value.context["item_id"] == 7

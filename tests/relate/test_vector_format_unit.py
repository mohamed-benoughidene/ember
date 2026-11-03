"""Unit tests for the one vector format: little-endian float32 on disk.

Pure round-trip on the pack/unpack helpers this chunk moves (Batch 7 chunk
12): pack then unpack must return the values at float32 precision — the
cache's precision, which defines scoring (decision N20, spec-check option A).
No database, no model, no port.
"""

from __future__ import annotations

import struct

from ember.adapters.sqlite import _pack_vector, _unpack_vector


def test_pack_then_unpack_returns_float32_representable_values_exactly() -> None:
    vector = [0.5, -2.25, 1.0, 0.0, 123.0]
    assert _unpack_vector(_pack_vector(vector)) == vector


def test_pack_then_unpack_quantizes_to_float32_precision() -> None:
    # 0.1 is not representable in float32; the round trip must return the
    # exact float32 widening of it, not the original float64 value.
    vector = [0.1, -0.2, 0.3]
    expected = list(
        struct.unpack("<3f", struct.pack("<3f", *vector))
    )
    assert expected != vector  # the precision loss this test pins is real
    assert _unpack_vector(_pack_vector(vector)) == expected


def test_pack_bytes_are_little_endian_float32() -> None:
    vector = [0.5, -2.25, 1.0]
    assert _pack_vector(vector) == struct.pack("<3f", *vector)


def test_unpack_reads_little_endian_float32_blob() -> None:
    blob = struct.pack("<3f", 0.5, -2.25, 1.0)
    assert _unpack_vector(blob) == [0.5, -2.25, 1.0]


def test_round_trip_on_empty_vector() -> None:
    assert _unpack_vector(_pack_vector([])) == []

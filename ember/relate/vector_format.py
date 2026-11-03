"""The ONE vector format: little-endian float32, the embedding cache's format.

Why float32: the cache stores embeddings as little-endian float32 blobs, and
the cache's precision defines scoring (Batch 7 chunk 12, decision N20,
spec-check option A). A query vector is therefore round-tripped through
`pack_vector`/`unpack_vector` before any cosine, so a freshly encoded query
and the same vector returned from a cache hit score identically — otherwise
the float64 tail of a fresh encoding shifts cosine scores at the eighth
significant digit and reruns change the ranking. Worth keeping: float32
halves cache size against cosine differences too small to matter
(`spec-check` D3 option A). Only stdlib here; core must not import adapters.
"""

from __future__ import annotations

import sys
from array import array


def pack_vector(vector: list[float]) -> bytes:
    """Pack a float vector as little-endian float32, the on-disk format."""
    values = array("f", vector)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def unpack_vector(blob: bytes) -> list[float]:
    """Decode a little-endian float32 blob back into floats."""
    values = array("f")
    values.frombytes(blob)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tolist()

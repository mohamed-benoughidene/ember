-- Migration 015: the vector cache's format tag (Batch 7 chunk 13, N14 number).
-- Additive only: nullable TEXT, no default, no rebuild, no backfill
-- (constitution D5). Every pre-015 row reads NULL, and a missing column
-- (a file not yet migrated) reads the same: the ONE format
-- `ember.relate.vector_format` defines — little-endian float32, the
-- on-disk format of `vector` since migration 007. `float32` is the tag
-- new cache writes carry, so a future second format can be told apart.
ALTER TABLE item_embeddings ADD COLUMN vector_format TEXT;

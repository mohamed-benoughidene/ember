-- Migration 013: the undo group id (engine-undo-plan L2 §5.1, undo step 01).
-- Additive and nullable: one user action shares one group id across every
-- ledger row it writes. No default, no backfill: every pre-013 row reads
-- NULL and is invisible to undo.
ALTER TABLE change_log ADD COLUMN group_id INTEGER;

-- Migration 014: the optional ledger source id (Batch 6 N14, D-07 groundwork).
-- Additive and nullable: a forgotten note's ledger row can name its source
-- without carrying any note text. No default, no backfill: every pre-014
-- row reads NULL.
ALTER TABLE change_log ADD COLUMN source_id INTEGER;

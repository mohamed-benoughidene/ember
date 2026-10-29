-- #5: optional project-area label, written by capture (L2 capture plan section 9).
-- Additive only: nullable TEXT, no default, no rebuild, no backfill. NULL means
-- unlabeled, and the 30-day proxy keeps covering those rows (L2 relate plan section 13).
ALTER TABLE items ADD COLUMN metadata TEXT;

-- Migration 016: the history read's ordering index (Batch 8, finding 4.7 #12).
-- Additive only: one new index, no rebuild, no backfill (constitution D5).
-- `history()` reads the ledger sorted by `(timestamp, id)` DESCENDING and
-- shows at most `--limit` rows (Batch 6, finding 4.7 #13): an index on
-- exactly that key lets SQLite walk the index backwards and stop at the
-- page's end, instead of sorting every ledger row on every open.
CREATE INDEX idx_change_log_ts_id ON change_log (timestamp, id);

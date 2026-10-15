# L3 Capture Step 1: Source Storage (Phase 1)

Implements Phase 1 of L2 Capture plan. Read raw input, dedup by hash, return source_id.

## 1. Job

Take raw text (from STDIN or file) and produce `{source_id, raw_text, content_hash}`. Dedup by content hash so the same pasted text never creates two source rows.

## 2. Inputs

- `mode`: `stdin` OR `file`.
- `path` (only if mode=file): absolute path to file on disk.

## 3. Outputs

`{source_id: int, raw_text: str, content_hash: str}`

- `source_id` = id from `sources` table (existing row or new insert).
- `raw_text` = exact bytes read from input, no transform.
- `content_hash` = SHA-256 hex string of `raw_text` bytes.

## 4. Steps

1. Read raw bytes:
   - mode=stdin: read until EOF (Ctrl-D on terminal).
   - mode=file: open path, read all bytes. If size > threshold, exit 1 with reason. Threshold = L3 decision (Section 6 of L2, item 5 of L2 Section 8).
2. Decode bytes as UTF-8. If decode fails, exit 1 with reason.
3. Compute `content_hash = SHA-256(raw_text_bytes)` as hex.
4. Query `sources` table: `SELECT id, full_text FROM sources WHERE content_hash = ?`.
   - DB read = normal app read, not gatekeeper-bound (per L2 Section 5 L99).
5. If match found AND `full_text` equals current `raw_text` byte-for-byte: reuse `source_id`, log "source already stored" to STDERR (info, matches L2 L26).
6. Else: insert new row into `sources` table.
   - Write goes through gatekeeper port. Gatekeeper script reuses the `add_item`-style validate pattern from L1 line 68 (no new gatekeeper name; sources are a sibling table to items, same write-boundary pattern).
   - Gatekeeper generates: `id` (auto), `timestamp` (now).
   - Caller passes: `title` (default = first 80 chars of `raw_text`), `full_text` (= `raw_text`), `content_hash`.
   - Get new `source_id` from gatekeeper output.
7. Return `{source_id, raw_text, content_hash}` to caller (Phase 2).

## 5. Errors

- File not found (mode=file): exit 1, reason = "file not found: <path>".
- File > threshold: exit 1, reason = "file too large".
- STDIN read fail: exit 1, reason = "stdin read fail".
- UTF-8 decode fail: exit 1, reason = "invalid utf-8".
- DB read fail: exit 1, reason = "db read fail".
- DB write fail (gatekeeper): exit 1, reason = "db write fail".

## 6. Test Targets

Unit (mocked DB):
- Hash dedup: same raw_text twice -> 2nd call reuses first source_id.
- Hash mismatch: different raw_text -> new source_id each time.
- UTF-8 decode fail -> exit 1.

Integration (real SQLite temp DB):
- Paste "hello" twice -> 1 row in `sources`, 2 calls return same source_id.
- Paste "hello" then "world" -> 2 rows in `sources`, 2 different source_ids.
- File mode: read `test.txt` -> 1 row in `sources`, source_id matches table query.

## 7. Out of Scope (this step)

- AI proposals (Step 2 / Phase 2).
- User confirm + write (Step 3 / Phase 4).
- Gatekeeper logic itself (L3 owns gatekeeper script bodies; this step just calls the port).

## 8. Next

Step 2 builds the AI port call on top of this output. Step 3 wires user confirm + write using the items this step enables.

## 9. Deferred Settings (from L2 Section 8)

- Large-file rejection threshold (item 5) — L3 picks the number. This step enforces it.

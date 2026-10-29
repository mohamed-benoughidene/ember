# L3 Step 02: `ember export` (Engine E: Utility, closes issue #18)

L2: `plans/engine-utility-plan.md` §4.2, §5.2, §6 (APPROVED)
Ticket: `.scratch/utility/issues/03-plain-text-export.md`

## Constitution rules this step enforces

B1 (one job: render the knowledge base as human-readable text), B2 (no other engine's internals touched), D1 (raw source text verbatim), D2 (embeddings/AI responses excluded, declared), D3 (items referenced by id), I2 (`--out` is data, not a mode), I4 (named `ExportData`, never a 5-tuple), I5/I6 (named EmberError subclasses), I7 (fail fast, no swallowed errors), I8 (empty database exports successfully), I9 (paths validated at the edge), I11/I21 (docstrings list raised codes; tests assert codes), I17/I18/I19/I20 (stable codes, auto location, ids in errors), P3 (fixed gather -> render -> emit pipeline), T1 (render pure, no clock), T3/T4 (real temp DBs, no mocks), T9 (sqlite3 via the existing public opener only; render is a pure function), S1/S3/S4 (standalone, shapes documented, text-file transfer documented).

## Boundary shapes (L2 §5.2)

- CLI opens the DB: `conn = open_query_database(db_path)` (read-only, QUERY-003/004 semantics, floors enforced, never migrates) — same call site pattern as every query command.
- `ember/adapters/export.py`:
  - `gather_export(conn: sqlite3.Connection) -> ExportData`
  - `ExportData`: named model — `schema_version: int`, `items: list`, `links: list`, `sources: list`, `ledger: list` (rows gathered in fixed order: items by id, links by id, sources by id, ledger by timestamp then id)
  - `render_export(data: ExportData) -> str` — PURE. No I/O, no clock. Header "as of" = max ledger timestamp. Sections fixed: header, items, links, sources, ledger. All columns of every row. Removed/Rejected and reversed links labelled with their state and `reversed_at`. Sources verbatim between explicit BEGIN/END marker lines (leading whitespace and non-ASCII preserved). Ledger values full, never truncated. Excludes `item_embeddings` and `ai_responses`; header declares the exclusion (D2). Empty database -> valid 0-count file (I8).
- `ember/cli.py`: `@main.command("export")`, options `--db` (default) and `--out` (optional path). Emit: `--out` given -> guard then write, print the summary line; else print text to stdout. Guard (EXPORT-002) BEFORE any open-for-write: refuse when the resolved output path equals the resolved db path, plus `os.path.samefile` when both exist (L2 §5.2, severe panel finding).

## Error codes this step raises (L2 §6)

EXPORT-001 (output file cannot be written), EXPORT-002 (out path is the knowledge base file). Reused unchanged: QUERY-003 (db missing), QUERY-004 (schema below floor) from `open_query_database`.

## Test targets (write first, red -> green)

In `tests/test_export.py` (real temp SQLite files seeded through the real migration path):
1. Pure render unit: constructed `ExportData` -> render twice -> byte-identical (determinism); section order; rendered counts match the data; verbatim source block with leading whitespace + emoji round-trips exactly; Rejected and reversed links rendered with states; untruncated long ledger values; empty `ExportData` renders a valid header.
2. Coverage proof: seeded DB (>= 1 item per type, one Rejected link, one reversed link, multiple ledger causes, multi-line source) -> every seeded row's fields appear in the text.
3. Hash proof: DB file byte-identical before and after export; same for a refused EXPORT-002 attempt.
4. `--out` writes the file, stdout default works, both exit 0; `--out` unwritable path -> EXPORT-001, exit 1; `--out <the-db>` -> EXPORT-002, exit 1, DB untouched.
5. Floors: below-floor file -> QUERY-004 (existing behavior, asserted so export's reuse stays honest).

Fixture for the verbatim-source test lives at `tests/fixtures/export_source_verbatim.txt`.

## CLI check (run after green)

```
$ ember export --db <seeded temp db> | head -5
# Ember knowledge base export
# schema version: 12
# as of (latest ledger event): <max ledger ts>
# counts: N items, L links, R ledger rows, S sources
# embeddings and AI responses are derived, rebuildable data (D2) and are not exported.      [exit 0]
$ ember export --db <db> --out <db>
error: EXPORT-002 OverwriteRefused | ... | output path is the knowledge base file | ...      [exit 1]
```

## Rollback

No rollback — read-only over the live DB, enforced by the hash-proof tests. The only artifact is the output file, deleted by the user. No schema change (v12 unchanged).

## Build Notes

*(post-implementation: what landed, suite numbers, deviations)*

Landed as one commit on `feat/data-safety` (utility step 02, closes issue 18):

- `ember/adapters/export.py`: `gather_export(conn) -> ExportData` (fixed-order
  SELECTs, schema version read only) and the PURE `render_export(data) -> str`,
  plus the emitter helpers `refuse_self_overwrite` and `write_export`. Row
  models `ExportItem` / `ExportSource` / `ExportData` in the query `rows.py`
  style (pydantic), links reuse `ember.relate.rows.Link` (D3) and ledger rows
  reuse `ember.query.rows.ChangeRow`, so no row shape is duplicated.
- `ember/adapters/errors.py`: `ExportError` (`EXPORT-000`) with leaves
  `OutputWriteFailed` (`EXPORT-001`) and `OverwriteRefused` (`EXPORT-002`),
  following the step 01 `BackupError` pattern exactly.
- `ember/cli.py`: `ember export` with `--db` and optional `--out`, opened via
  `open_query_database` (QUERY-003/004 reused, floors enforced, never
  migrates). The guard runs before any open-for-write, and refusal leaves
  the DB byte-identical (proved by hashes below).
- `tests/test_export.py` (20 tests) + `tests/fixtures/export_source_verbatim.txt`.
- `tests/fakes.py`: `insert_item` grew optional `rationale` / `source` params
  (same conditional-column pattern as its existing `metadata` param) so the
  coverage proof can seed every column. No other existing file changed.
- `PROJECT_MAP.md` and `.scratch` ticket updated. README deliberately not
  touched (orchestrator handles it, per step instructions).

Suite numbers (TDD): red run before implementation: collection error
(`OverwriteRefused` did not exist yet), then 8 passed / 12 failed after the
first implementation pass, then green: **20 passed**. Full suite after:
**872 passed, 4 deselected** (baseline was 852 passed, 4 deselected). `tests/
test_architecture.py` explicitly: **6 passed**.

CLI checks (seeded real DB at /tmp/opencode/export-check/ember.db):
- `ember export --db ember.db | head -5`: the five pinned header lines,
  exit 0.
- `ember export --db ember.db --out /tmp/opencode/export-check/ember.txt`:
  `exported 3 items, 2 links, 1 ledger rows, 1 sources -> ...`, exit 0.
- `ember export --db ember.db --out ember.db`: `error: EXPORT-002
  OverwriteRefused | ember.adapters.export.refuse_self_overwrite | output
  path is the knowledge base file | db_path=ember.db out=ember.db`, exit 1.
  sha256 before `18b17b476906d511cb6a58949935e86fcbc1c98d7e75cfe5e15a2b0088c69e8d`,
  after identical, `IDENTICAL`.

Deviations (each with a one-line justification):

1. **End-marker design hardened** (the step plan flagged this as pre-commit
   work): the end marker is `----- source <id> text end (bytes=<n>,
   sha256=<h>) -----` instead of the sketched bare form, because a source
   containing a bare `----- source 1 text end -----` line (as the fixture
   does) could otherwise close its own block. The id + byte count + digest
   cannot be forged by content without inverting SHA-256, and another
   source's end line fails the id check.
2. **Item blocks lead with `type id | status`** (rule 5 of the build order),
   statement first among the field lines, and `source_id` added after the
   plan's column list: the plan's list omitted it, but "ALL columns of every
   row exported" wins, and a triaging reader needs the source pointer.
3. **`validated` renders as the raw 0/1/(null)** column value rather than a
   prose word: lossless, and the export is the record (L2 §5.2).
4. **v12 `headers` declare the D2 exclusion in the plan's exact wording** and
   the missing-ledger case renders `# as of (latest ledger event): (no
   ledger rows)` so an empty database stays a valid 0-count file (I8).
5. **`tests/query/fakes.py` `make_v9` reused for the floor test** instead of
   a new builder: same pattern as `tests/test_backup.py`, no new seam.

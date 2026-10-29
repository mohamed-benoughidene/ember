# Ember Command Inventory

Every `ember` command, what it does, what it touches, and how it fails.

Facts in this file come from the code (`ember/cli.py` and the engine modules), not from memory. For deeper background see the README and `PROJECT_MAP.md`.

## Conventions (every command)

- `--db PATH` opens that database instead of the default `ember.db`.
- **Exit 0** on success. **Exit 1** for any `EmberError`: one `error: <CODE> <Name> | <location> | <detail>` line on stderr. **Exit 2** for a Click usage error (unknown flag, non-integer value) or for a deliberate user abort (`q` or end of input in a confirm loop).
- **Needs key** means the command calls the AI and reads `EMBER_AI_API_KEY` (or `OPENROUTER_API_KEY`); set it with `scripts/ember-key-wizard.sh`.
- **Read-only** commands are hash-proven by tests: the database file is byte-identical after a run.

---

## Engine A: Capture (writes entries into the knowledge base)

### `ember capture [--file PATH] [--db PATH]` - needs key

The full Phase 1-4 pipeline. Reads raw text from a file or STDIN (file input capped at 5 MiB, UTF-8), dedupes by SHA-256 content hash, asks the AI for typed proposals, validates each (type, non-empty statement, the quote must appear in the stored source, near-duplicate warning), then opens the confirm loop.

- Confirm keys: `y` accept, `n` reject, `e` edit, `q` quit (exit 2).
- `e` re-asks the type (one of `Decision`, `Assumption`, `Finding`, `Question`), the statement, and the optional project label; a failed edit drops that proposal, nothing is written.
- Writes: `sources`, `ai_responses`, `items` (only confirmed ones), `change_log` rows for proposals you rejected.
- The AI sees the newest 50 items as context (mode `B`, default); set `EMBER_CAPTURE_CONTEXT_MODE=A` for no context.
- One AI retry, no wait. Any `CAPTURE-###` error exits 1.

### `ember capture-source [--file PATH] [--db PATH]` - no key

Phase 1 alone: store or reuse the raw source, nothing else. Prints one JSON document (`source_id`, `content_hash`, `raw_text`); `source already stored` prints on stderr when the hash already exists. No AI call, no items written.

### `ember set-validated --item N [--db PATH]` / `ember clear-validated --item N [--db PATH]` - no key

Set or clear the `validated` flag on an item. Only an `Assumption` may carry the flag; anything else exits 1. Both write a `change_log` row (`validated`).

---

## Engine B: Relate (writes links between items)

### `ember relate (--item N | --latest) [--db PATH]` - needs key + optional extra

Links one item to the rest of the graph in four phases: load and filter, rank a candidate pool, ask AI for typed link proposals (raw answer saved verbatim in `ai_responses`), then gatekeeper and a per-proposal confirm loop.

- The two item flags are mutually exclusive. Candidate ranking uses three signals merged by cosine: embedding content, one-hop graph neighbors, and the `items.metadata` project label.
- The content signal needs `pip install -e ".[relate]"` (sentence-transformers); without the extra the command refuses at boot with the install hint.
- Embeddings are cached in `item_embeddings` per model; a model change wipes the cache and prints a warning (one-time minutes-long rebuild).
- Confirm keys: `y` accept, `n` reject, `s` skip (nothing written, the candidate may resurface for a later item), `q` quit (exit 2).
- The link types are `supports`, `contradicts`, `depends_on`, `supersedes`, `answers`, restricted by a per-type compatibility table (11 allowed pairs).
- The gatekeeper runs 9 ordered rules per proposal; refusals print `relate rejected: CODE | detail` (duplicates, `supersedes` cycles, Closed targets). All rejected-row checks also see reversed links.
- An empty candidate pool exits 0 without ever calling the AI. Summary line at the end: `accepted: N, rejected: N, skipped: N, aborted: true|false`.

---

## Engine C: Maintain (keeps statuses coherent)

### `ember maintain [--dry-run] [--db PATH]` - zero AI for the sweep

The status sweep: load items and confirmed links, derive the correct status per item (pure rules, no AI), apply everything in **one transaction** (item updates plus `change_log` rows), print the report.

- The four rules: a confirmed `supersedes` closes its target (reason `superseded`); a confirmed `answers` closes an answered `Question` (reason `answered`); a confirmed `contradicts` challenges its target; a confirmed `depends_on` onto an invalidated/superseded target challenges the dependent.
- Escalation only: the sweep never moves an item to a safer status. A human-set status is shielded until newer link evidence arrives, then re-armed (`sweep_rearm` in the ledger).
- `--dry-run` writes nothing and needs no key.
- **Phase 5, real runs only:** after applying, an AI close-proposal loop runs for `Question` items whose newest confirmed `answers` link is at least 30 days old, capped at 10 per run. Raw answers are saved verbatim before judging; each proposal is confirmed with `[y]es / [n]o / [q]uit`; an accepted close goes through the human `close-item` path. An empty shortlist builds no AI adapter and reads no key.

### `ember close-item --item N --reason invalidated|expired [--dry-run] [--db PATH]` - no key

Human close of an item. Only `invalidated` and `expired` are human reasons (the machine reasons `superseded`, `answered`, `reversed` are refused). One transaction: the close plus the rule fan-out (dependents of an invalidated item get challenged). Errors: unknown reason, machine reason, or already Closed.

### `ember set-status --item N --to Active|Challenged [--db PATH]` - no key

The only human moves are `Active` <-> `Challenged`. Stamps `status_origin='manual'`, which shields the item from the sweep until newer evidence re-arms it. Same-value target is a no-op; a Closed item refuses.

### `ember reverse-supersedes --item N --link N [--db PATH]` - no key

Undo one `supersedes`: restores the item to `Active`, sets `reversed_at` on the link, writes two `change_log` rows (`status` + `link_reversed`) in one transaction. The link row is never deleted. Requires the item closed as `superseded` and a confirmed, unreversed `supersedes` link pointing at it.

### `ember edit-item --item N --field rationale|source --value TEXT [--dry-run] [--db PATH]` - no key

The authorial-slot editor. `rationale` is writable on a `Decision`, `source` on a `Finding`; `statement` is a known but forbidden field, unknown field names are refused. Same-value edits are no-ops (exit 0, nothing written). `--dry-run` prints `item <id>: <field>: <old> -> <new> (dry-run)`.

### `ember remove-link --link N [--dry-run] [--db PATH]` - no key

Remove one confirmed link by status flip (`Confirmed` -> `Rejected`) plus its `link_removed` ledger row, in one transaction. The row is never deleted, so the history stays complete. A missing or already-rejected link exits 1. `--dry-run` prints `link <id>: Confirmed -> Rejected (dry-run)`.

---

## Engine D: Query (read-only views)

All four print exactly one JSON document on stdout and read only `items`, `links`, `change_log`. They enforce a schema floor (`QUERY-004` on an older file) and never migrate. `--db PATH` everywhere.

### `ember current-state [--db PATH]`
Live statuses only: `Active` and `Challenged` items, `Closed` omitted, `Challenged` listed first. Envelope: `mode`, `count`, `items` (each row carries a `challenged` flag).

### `ember topic-search --query TEXT [--status S] [--type T] [--limit N] [--db PATH]`
BM25 keyword search over item statements (all statuses, `Closed` included). `--status` accepts `Active|Challenged|Closed`, `--type` accepts `Decision|Assumption|Finding|Question`; filters narrow the corpus before scoring. `--limit 0` is an explicit empty result; negative values exit 1 (`QUERY-006`). Envelope: `mode`, `query`, `count`, `results`.

### `ember why --item N [--db PATH]`
The reasons behind an item: follows `depends_on` (to its target) and `supports` (to its source), Confirmed links only, transitively, cycle-safe. Unknown ids exit 1 (`QUERY-001`). Envelope: `mode`, `item`, `count`, `reasons` (ordered by depth then id, carrying each reason's rationale text).

### `ember history [--item N] [--limit N] [--offset N] [--since TS] [--db PATH]`
The ledger view, item-scoped or global. Item scope includes rows whose `link_id` touches the item; a row matching both ways appears once. Events are classified into readable kinds (`created`, `link_confirmed`, `status_changed`, `link_reversed`, ... anything unmatchable is `unknown`). Sort is `(timestamp, id)` ascending; `--limit 0` is an explicit empty page. `--since` must parse as ISO-8601 **with a UTC offset** (naive or garbage input exits 1, `QUERY-007`). Envelope: `mode`, `item_id`, `count`, `events`.

---

## Engine E: Utility (safety commands, human-only)

### `ember db-check [--db PATH]` - read-only health report
Checks schema version against the floors (relate 12, maintain 11, query 10, capture none), the enforcement triggers, the link-compatibility table against the code, foreign keys, and replays the reversal ledger against the live `links.reversed_at`. Prints the report and exits 0 with `result: OK`; any drift exits 1 (`DRIFT`), and an unreadable database exits 1 too (`UNREADABLE`: missing file, non-SQLite bytes, or any database error mid-check). Never migrates, never writes.

### `ember backup TARGET_PATH [--db PATH]` - writes only the target file
A restorable snapshot (GLOSSARY: Backup). Uses SQLite's online backup API (a consistent page image even mid-write), opens the source read-only with no schema floors (older files stay restorable; boot upgrades on restore), refuses a target that is the source file itself or an existing directory, and rotates an existing target into `.old-1..3` (newest 3 kept, the same retention as the migration runner's `.bak-v`), then verifies: re-opens the copy and reads its schema version plus item count. A failed snapshot or verify deletes the partial copy, so no broken file is ever left behind. Prints `backup written: <path> (schema v<N>, <count> items)`; a rotation adds `rotated to <path>` on stderr. Restore is deliberately not a command: copy the file back or point `--db` at it. Codes: `BACKUP-001` source open, `BACKUP-002` source invalid, `BACKUP-003` target write, `BACKUP-004` verify failed.

### `ember export [--out PATH] [--db PATH]` - read-only, hash-proven
A readable text rendering (GLOSSARY: Export, not restorable). Every `items`, `links`, `sources`, and `change_log` row, all columns, in fixed order (items by id, links by id, sources by id, ledger by timestamp then id), with derived tables (`item_embeddings`, `ai_responses`) declared excluded in the header. Deterministic: no wall clock (the header's as-of line is the newest ledger timestamp), so the same database renders byte-identical text every time. Raw source text is verbatim between sha256-stamped markers (the end marker names the source id, byte count, and sha256; if a source text does not end with a newline, exactly one is added so the marker starts its own line, and the declared byte count preserves the original). `--out` writes the file and prints `exported <N> items, <M> links, <K> ledger rows, <S> sources -> <path>`; without it the text goes to stdout. `--out` naming the database file itself is refused before anything is opened (`EXPORT-002`), database untouched. Codes: `EXPORT-001` output write failed, `EXPORT-002` overwrite refused; `QUERY-003`/`QUERY-004` reused for the database open.

---

## Helper script

- `scripts/ember-key-wizard.sh`: interactive walkthrough for getting an OpenRouter key; writes `/tmp/opencode/ember.env` (mode 600, outside the repo, delete after a real run). Needed by `capture`, `relate`, and the live tests.

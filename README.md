# Ember

> **Project Context Management System**
> Preserving the evolving state of what a project knows, believes, decides, and learns over time.

---

## What is Ember?

When teams work on software or products, they make decisions, discover facts, test assumptions, and ask questions. Over time, that knowledge gets lost inside old chat logs, commit histories, or people's heads.

Ember is a system for maintaining that durable context. It does not store the project itself (like code files or images). Instead, it stores the understanding **around** the project: why choices were made, what is currently unproven, and what new findings change our thinking.

---

## Core Principles

- **Durable Knowledge Only:** Focuses on persistent knowledge that alters how a project is understood, not raw code or daily to-do lists.
- **Traceable History:** Items are never deleted. State changes (like an assumption becoming invalid) are preserved with their causes.
- **Strict Boundaries:** External data and AI outputs pass through validation scripts before entering the system.
- **Fast, Local-First:** Designed to run with a local database on your own computer with zero mandatory servers.

---

## Repository Structure

- `Constitution.md`: Architectural rules for standalone modules, clean boundaries, and reliable tests.
- `GLOSSARY.md`: The project's vocabulary: knowledge base, ledger, item, link, and the backup/export/restore language.
- `PROJECT_MAP.md`: Index of every file and directory in this project.
- `Personal guidelines.md`: Working guidelines on accuracy, plain language, and critical thinking.
- `docs/`: System documentation, brand philosophy, and architecture diagrams. The full command inventory (every command with its flags, writes, and error codes) is in `docs/commands.md`.
  - `docs/ai version/`: Compressed specifications optimized for AI readers.
  - `docs/humen version/`: Plain-English specifications written for human builders.
  - `docs/Graphs/`: Visual diagrams and example runs.
- `assets/`: Official Ember brand logos and icons.

---

## Status

- **Engine A (Capture):** Built and verified. Stores raw source text with SHA-256 dedup, asks AI for typed `Decision` / `Assumption` / `Finding` / `Question` proposals, validates them with gatekeeper checks, and writes only what you confirm key by key (`y` accept, `n` reject, `e` edit, `q` quit).
- **Engine B (Relate):** Built and verified. Ranks link candidates for one item with three signals (embedding content, graph neighbors, project labels), asks AI for typed link proposals, runs 9 gatekeeper rules (duplicates, `supersedes` cycles, compatibility), and writes links only after your per-proposal check (`y` accept, `n` reject, `s` skip, `q` quit).
- **Engine C (Maintain):** Built and verified. A deterministic, zero-AI sweep derives item statuses from confirmed links and writes only the difference to the ledger, plus an optional AI close-proposal loop for `Question` items whose newest answer link is at least 30 days old. Five human-only commands (`close-item`, `set-status`, `reverse-supersedes`, `edit-item`, `remove-link`) write through the same ledger, each with a `--dry-run`.
- **Engine D (Query):** Built and verified. Four read-only JSON commands over the local database: current state, BM25 topic search, the `why` reason walk, and the `history` ledger view. It refuses an older database instead of migrating it.
- **Engine E (Utility):** Built and verified. Human-only safety commands outside the pipeline: `backup` (verified snapshot with rotation) and `export` (deterministic readable text file).

---

## Quickstart

### Installation

Requires Python 3.12+.

```bash
git clone https://github.com/mohamed-benoughidene/ember.git
cd ember
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Environment Variables

For AI-assisted capture, provide an OpenRouter API key:

```bash
export EMBER_AI_API_KEY="your-openrouter-key"
```

Optional settings:
- `EMBER_AI_MODEL`: Model name (default: `anthropic/claude-haiku-5.5`).
- `EMBER_AI_BASE_URL`: API base URL (default: `https://openrouter.ai/api/v1`).
- `EMBER_CAPTURE_CONTEXT_MODE`: `B` to include the newest 50 items as context (default), `A` for no context.

### CLI Usage

**1. Store raw source text only (Phase 1):**

```bash
# Read from STDIN
printf 'We decided to use SQLite for local storage.' | ember capture-source

# Or read from a file
ember capture-source --file note.txt
```

**2. Run full Capture pipeline (Phases 1–4):**

```bash
ember capture --file note.txt
```

Ember stores the raw text, generates typed item proposals (`Decision`, `Assumption`, `Finding`, `Question`), runs gatekeeper checks, and prompts you to confirm (`y`), reject (`n`), edit (`e`), or quit (`q`). Editing re-asks the type, the statement, and the optional project label, then revalidates before the write. Sources are deduplicated by content hash (the same text twice reuses the stored source), file input is capped at 5 MiB, and by default the AI sees the newest 50 items as context (`EMBER_CAPTURE_CONTEXT_MODE`).

**3. Manage Assumption validation flag:**

```bash
# Mark an Assumption as verified
ember set-validated --item 2

# Clear the flag
ember clear-validated --item 2
```

**4. Relate an item to typed link candidates (Phase 1):**

```bash
ember relate --item <id> [--db PATH]
ember relate --latest [--db PATH]
```

Phase 1 loads the item, drops pairs that already have a link (any status), and prints `{"phase": 1, "new_item_id": <id>, "candidates": <count>}` (or `no unrelated items`). `--db` must point to an existing database. Confirm each proposal with `y` (accept), `n` (reject), `s` (skip, the candidate is not written and may resurface later), or `q` (quit, exit 2). Ranking uses three signals: embedding content, one-hop graph neighbors, and the project label written by capture. The content signal needs the optional extra installed once (```pip install -e ".[relate]"```); if the embedding model ever changes, the vector cache is wiped and rebuilt (a one-time, minutes-long cost, a warning prints). Gatekeeper rejections print one `relate rejected: CODE | detail` line each before the summary.

**5. Maintain the graph (Engine C):**

```bash
# Reconcile item statuses from links (add --dry-run to preview)
ember maintain [--db PATH]

# Close an item by hand (human-only reasons: invalidated, expired)
ember close-item --item <id> --reason invalidated [--dry-run] [--db PATH]

# Move an item between Active and Challenged
ember set-status --item <id> --to Active [--db PATH]

# Undo a supersedes (restores the closed item to Active)
ember reverse-supersedes --item <id> --link <id> [--db PATH]

# Change an authorial field by hand (rationale on a Decision, source on a Finding)
ember edit-item --item <id> --field rationale --value "new text" [--dry-run] [--db PATH]

# Remove one confirmed link (a status flip to Rejected, never a delete)
ember remove-link --link <id> [--dry-run] [--db PATH]
```

The sweep reads `items` + Confirmed `links`, derives each item's status (a confirmed `supersedes` or `answers` closes the target, a `contradicts` challenges it, and an invalidated dependency challenges the dependent), and writes only the difference, one `change_log` row per change. `close-item`, `set-status`, `reverse-supersedes`, `edit-item`, and `remove-link` are the human-only mutations; all render through the same report format. After a real sweep applies its changes, Ember may offer AI close proposals for `Question` items whose newest answer link is at least 30 days old (at most 10 per run), each confirmed with `[y]es / [n]o / [q]uit`; an accepted close goes through the same human `close-item` path. An empty shortlist calls no AI and needs no key.

**6. Query the project context (Engine D):**

```bash
ember current-state [--db PATH]
ember topic-search --query TEXT [--status Active] [--type Question] [--limit 10] [--db PATH]
ember why --item <id> [--db PATH]
ember history [--item <id>] [--limit 20] [--offset 0] [--since 2026-01-01T00:00:00+00:00] [--db PATH]
```

All four are read-only and never write to the database. Each prints one JSON document on stdout. `current-state` lists the `Active` and `Challenged` items with the `Challenged` ones first. `topic-search` ranks by BM25 over item statements; `--limit 0` means an explicitly empty result. `why` walks the `depends_on` and `supports` links behind an item (Confirmed links only, transitively). `history` shows that item's `change_log` rows with the cause of each change, or the whole ledger with no `--item`; `--since` must carry a UTC offset. An older database is refused (`QUERY-004`), never migrated.

**7. Keep the knowledge safe (Engine E):**

```bash
# Snapshot the whole knowledge base to a file you can always go back to
ember backup /path/to/backup.db [--db PATH]

# Export everything as plain text, readable without Ember, forever
ember export [--db PATH] [--out PATH]
```

`backup` copies the database with SQLite's online backup API (a consistent snapshot even if another command is mid-write), then re-opens the copy and prints its schema version and item count as proof. If the target already exists, the previous copy is rotated to `<target>.old-1` (the `.old` chain keeps the newest 3 old copies, so 4 generations exist in total, like the migration runner's own backups) and the command reports the rotation. Restore is deliberately not a command: copy the backup back over `ember.db`, or point Ember at it with `--db`. A backup of an older-schema file is fine, boot upgrades it on restore.

`export` writes every item, link, source, and full ledger row as one deterministic, human-readable text file (same database always produces the same bytes). Rejected and reversed links are included with their states, raw source text is kept verbatim, and derived data (embeddings, AI responses) is declared excluded in the header. The file cannot be restored into Ember; that is the backup's job. Read-only: the database file is byte-identical after an export. If `--out` points at the database itself, export refuses before touching anything (`EXPORT-002`).

### Running Tests

```bash
# Run all offline tests (873 tests)
pytest

# Run the live AI round-trip test (requires EMBER_AI_API_KEY)
pytest -m live
```

## API key wizard

For any command that needs a real OpenRouter key (capture, relate, or the live tests), run:

```
bash scripts/ember-key-wizard.sh
```

It walks you through getting the key from openrouter.ai, writes it to `/tmp/opencode/ember.env` (mode 600, outside the repo, never committed), verifies the file, and reminds you to delete it after a real run.

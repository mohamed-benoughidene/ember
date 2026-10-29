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
- `PROJECT_MAP.md`: Index of every file and directory in this project.
- `Personal guidelines.md`: Working guidelines on accuracy, plain language, and critical thinking.
- `docs/`: System documentation, brand philosophy, and architecture diagrams.
  - `docs/ai version/`: Compressed specifications optimized for AI readers.
  - `docs/humen version/`: Plain-English specifications written for human builders.
  - `docs/Graphs/`: Visual diagrams and example runs.
- `assets/`: Official Ember brand logos and icons.

---

## Status

- **Engine A (Capture):** Built and verified. Implements raw input storage, hash deduplication, AI item proposals, gatekeeper validation, user confirm loop, and the assumption validation flag.
- **Engine B (Relate):** Built and verified (finding candidate typed links between items).
- **Engine C (Maintain):** Built and verified.
- **Engine D (Query):** Built and verified.

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

Ember stores the raw text, generates typed item proposals (`Decision`, `Assumption`, `Finding`, `Question`), runs gatekeeper checks, and prompts you to confirm (`y`), reject (`n`), edit (`e`), or quit (`q`).

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

Phase 1 loads the item, drops pairs that already have a link (any status), and prints `{"phase": 1, "new_item_id": <id>, "candidates": <count>}` (or `no unrelated items`). `--db` must point to an existing database.

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
```

The sweep reads `items` + Confirmed `links`, derives each item's status, and writes the difference with a `change_log` row per change. `close-item`, `set-status`, and `reverse-supersedes` are the human-only mutations; all four render through the same report format.

**6. Query the project context (Engine D):**

```bash
ember current-state [--db PATH]
ember topic-search --query TEXT [--db PATH]
ember why --item <id> [--db PATH]
ember history [--item <id>] [--db PATH]
```

All four are read-only and never write to the database. Each prints one JSON document on stdout. `current-state` lists the `Active` and `Challenged` items with the `Challenged` ones first. `topic-search` ranks by BM25 over item statements. `why` walks the `depends_on` and `supports` links behind an item. `history` shows that item's `change_log` rows with the cause of each change, or the whole ledger with no `--item`.

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
# Run all offline tests (598 tests)
pytest

# Run the live AI round-trip test (requires EMBER_AI_API_KEY)
pytest -m live
```

## License

Ember is **source-available** under the [Business Source License 1.1](LICENSE) (`BSL-1.1`), (c) Mohamed Benoughidene.

- **You may use, copy, modify, and redistribute Ember for free** as long as the use stays inside your own organization or is personal: learning, development, testing, personal projects, and internal tools included.
- **Only selling Ember itself** (or a product or service built on or with it, including as a hosted service) to third parties requires a commercial license. Contact **mohamedbenoughidene@gmail.com**.
- **It ages into open source:** two years after a version is first published, that version automatically becomes available under the MIT License.
- Ember is not Open Source while under BSL 1.1; the license text says so itself.
- Contributions are welcome under the terms of [CLA.md](CLA.md): you keep ownership of what you write and grant the project a permanent license to use it, signed with a `Signed-off-by:` line in your commits.

## API key wizard

For any command that needs a real OpenRouter key (capture, relate, or the live tests), run:

```
bash scripts/ember-key-wizard.sh
```

It walks you through getting the key from openrouter.ai, writes it to `/tmp/opencode/ember.env` (mode 600, outside the repo, never committed), verifies the file, and reminds you to delete it after a real run.

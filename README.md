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
- **Engine B (Relate):** Next up (finding candidate typed links between items).
- **Engine C (Maintain):** Planned.
- **Engine D (Query):** Planned.

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

### Running Tests

```bash
# Run all offline tests (165 tests)
pytest

# Run the live AI round-trip test (requires EMBER_AI_API_KEY)
pytest -m live
```

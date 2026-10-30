<p align="center">
  <img src="assets/icon.svg" alt="Ember icon: a dark, cracked stone with a glowing core" width="96">
</p>

# Ember: local-first knowledge base for project decisions

> **Project Context Management System**
> Preserving the evolving state of what a project knows, believes, decides, and learns over time.

Ember is a command-line tool that keeps the knowledge around a project: decisions, assumptions, findings, and questions. It stores them in one local file, links them to each other, and records every change in a ledger.

Ember is a Python tool. It is not related to the Ember.js web framework. The [glossary](GLOSSARY.md) explains words like item, link, and ledger.

**[Run your first capture in five minutes](#quickstart)**

## What is Ember?

When teams build software, they make decisions, find facts, test assumptions, and ask questions. That knowledge gets lost in chat logs, commit history, and people's heads.

Ember keeps it. It does not store the project itself, such as code or images. It stores the understanding around the project: why choices were made, what is unproven, and what new findings change.

If you keep a decision log today, Ember does that job and also keeps assumptions, findings, and questions. Every item is Active, Challenged, or Closed.

## What you can do with Ember

- **Capture notes.** Ember reads a note, proposes items, and saves only the ones you confirm.
- **Link items.** Ember proposes how items relate: supports, contradicts, supersedes, answers, or depends on. You confirm each link.
- **Track assumptions.** Mark an assumption as verified. Ember flags an item as Challenged when a link contradicts it.
- **Ask why a decision was made.** Search by topic, list what is true now, or walk the reasons behind one item.
- **Back up and export.** Save a restorable snapshot, or write a plain text file any editor can read.

## Core Principles

- **Durable Knowledge Only:** Persistent knowledge that changes how a project is understood, not raw code or daily to-do lists.
- **Traceable History:** Ember has no command that deletes an item. Removing a link marks it Rejected. State changes keep their causes.
- **Strict Boundaries:** External data and AI outputs pass through validation scripts before entering the system.
- **Local-First:** The knowledge base is one local SQLite file, and Ember needs no server of its own. Commands that use AI send text to an AI service. See [Your text and the internet](#your-text-and-the-internet).

## Quickstart

Ember needs Python 3.12 or newer.

### Install

```bash
git clone https://github.com/mohamed-benoughidene/ember.git
cd ember
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Get an API key

`capture` and `relate` need an [OpenRouter](https://openrouter.ai) key. `maintain` needs one only for its optional AI close proposals. All other commands run without one.

The key wizard walks you through getting a key. It writes the key to `.env` (mode 600, gitignored, never committed) and never prints it.

```bash
bash scripts/ember-key-wizard.sh
```

Load the key into your shell before a real run:

```bash
set -a; source .env; set +a
```

### Settings

| Variable | What it does | Default |
|---|---|---|
| `EMBER_AI_API_KEY` | Your OpenRouter key. `OPENROUTER_API_KEY` also works. | none |
| `EMBER_AI_MODEL` | The AI model name. | `anthropic/claude-haiku-5.5` |
| `EMBER_AI_BASE_URL` | The AI service address. | `https://openrouter.ai/api/v1` |
| `EMBER_CAPTURE_CONTEXT_MODE` | `B` shows the AI the newest 50 items. `A` shows none. | `B` |
| `EMBER_EMBEDDER_MODEL` | The model that ranks link candidates in `relate`. | `bge-base-en-v1.5` |
| `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS` | How long `relate` waits for that model to load. | `120` |

`relate` also needs an optional extra. Its first run may download the embedding model.

```bash
pip install -e ".[relate]"
```

### Your first run

Ember creates `ember.db` (the knowledge base file) in the folder where you run it. Use `--db PATH` on any command to pick another file. Ember also writes a safety copy such as `ember.db.bak-v0` before it sets up or upgrades the file.

These three commands need no key:

```bash
printf 'We decided to use SQLite for local storage.' | ember capture-source
ember current-state
ember backup backup.db
```

Example output, one result per command:

```text
{"source_id": 1, "content_hash": "d24e3e4fefb852e4452635f2989c2d9ece94578299fd019880ec9868800078af", "raw_text": "We decided to use SQLite for local storage."}
{"mode": "current_state", "count": 0, "items": []}
backup written: backup.db (schema v12, 0 items)
```

`current-state` shows no items because `capture-source` only stores the note. To turn a note into items, run `capture` (needs a key). Ember proposes items and asks you to confirm each one: `y` accept, `n` reject, `e` edit, `q` quit.

```bash
ember capture --file note.txt
```

## Your text and the internet

Three commands send text to an AI service. The default is OpenRouter (see [Settings](#settings)).

- `capture` sends the whole note, plus the id, type, and statement of the newest 50 items. Mode `A` sends no items.
- `relate` sends the id, type, and statement of the new item and of each candidate it ranks.
- `maintain` sends text only on a real run, and only for Questions with an old answer. It handles up to 10 Questions per run. For each one, it sends the id, type, and statement, and the ids and date of its newest answer link.

All other commands run only on your computer. After its first download, the `relate` embedding model also runs on your computer.

## Commands at a glance

| Command | What it does | Needs a key |
|---|---|---|
| `capture` | Reads a note, proposes items, saves the ones you confirm | Yes |
| `capture-source` | Stores a raw note only, with no AI | No |
| `set-validated` | Marks an Assumption as verified | No |
| `clear-validated` | Clears that flag | No |
| `relate` | Proposes typed links for one item, saves the ones you confirm | Yes, plus the `relate` extra |
| `maintain` | Updates item statuses from confirmed links, with no AI | Only for the AI close proposals |
| `close-item` | Closes an item by hand | No |
| `set-status` | Moves an item between Active and Challenged | No |
| `reverse-supersedes` | Undoes a `supersedes` link | No |
| `edit-item` | Edits the rationale of a Decision or the source of a Finding | No |
| `remove-link` | Removes one confirmed link by marking it Rejected | No |
| `current-state` | Lists live items, Challenged first | No |
| `topic-search` | Searches item statements by topic | No |
| `why` | Shows the reasons behind an item | No |
| `history` | Shows the ledger, for one item or for all | No |
| `db-check` | Reports the health of the knowledge base file | No |
| `backup` | Saves a restorable snapshot | No |
| `export` | Writes everything as one plain text file | No |

For every flag, what each command writes, and every error code, read the [full command inventory](docs/commands.md).

## Status

Ember has five parts, called engines. All five are built and verified by the offline test suite.

- **Engine A, Capture:** Stores raw notes and asks AI to propose items. You confirm each one.
- **Engine B, Relate:** Ranks link candidates and asks AI to propose typed links. You confirm each one.
- **Engine C, Maintain:** A sweep with no AI updates statuses from confirmed links. Five commands make manual changes.
- **Engine D, Query:** Four read-only commands show the current state, search topics, explain a decision, and show the ledger.
- **Engine E, Utility:** Safety commands: `backup`, `export`, and the read-only `db-check`.

## FAQ

### What is Ember?

Ember is a command-line tool that helps you track decisions, assumptions, findings, and questions in a project. It stores them as items in one local SQLite file, links them, and keeps a ledger of every change. It does not store your code.

### Does Ember send my text over the internet?

Only `capture`, `relate`, and the optional close proposals in `maintain` do. They send text to an AI service, OpenRouter by default. [Your text and the internet](#your-text-and-the-internet) lists exactly what. All other commands run only on your computer.

### Do I need an API key?

Only for the three commands above. `capture-source`, the Query commands, `backup`, and `export` run without one. The [key wizard](#get-an-api-key) helps you get a key.

### Can I lose my knowledge?

`ember backup` saves a restorable snapshot. To restore, copy it over `ember.db` or point `--db` at it. `ember export` writes plain text you can read without Ember. Ember has no command that deletes an item.

### Can I use Ember at work, and can I sell it?

You may use, copy, modify, and share Ember for free for personal use or inside your own organization. Selling Ember, or a product or service built on it, needs a commercial license. This is a summary, not legal advice. Read [LICENSE](LICENSE) for the exact terms.

### How is Ember different from architecture decision records?

Tools like [adr-tools](https://github.com/npryce/adr-tools) keep architecture decisions as numbered files. Ember also keeps assumptions, findings, and questions, and the links between them. Which one fits depends on your team.

## Running tests

```bash
pytest
pytest -m live
```

`pytest` runs the offline tests. `pytest -m live` calls the real AI service, needs `EMBER_AI_API_KEY`, and costs money.

## Repository Structure

- [`Constitution.md`](Constitution.md): Architectural rules for standalone modules, clean boundaries, and reliable tests.
- [`GLOSSARY.md`](GLOSSARY.md): The project's vocabulary: knowledge base, ledger, item, link, and the backup/export/restore language.
- [`PROJECT_MAP.md`](PROJECT_MAP.md): Index of every file and directory in this project.
- [`docs/`](docs/): System documentation, brand philosophy, and architecture diagrams. The full command inventory (every command with its flags, writes, and error codes) is in [`docs/commands.md`](docs/commands.md).
  - [`docs/ai version/`](docs/ai%20version/): Compressed specifications optimized for AI readers.
  - [`docs/humen version/`](docs/humen%20version/): Plain-English specifications written for human builders.
  - [`docs/Graphs/`](docs/Graphs/): Visual diagrams and example runs.
- [`plans/`](plans/): The layered build plans: the system master plan (L1), the engine plans (L2), and the per-step plans (L3).
- [`assets/`](assets/): Official Ember brand logos and icons.

## License

Ember is **source-available** under the [Business Source License 1.1](LICENSE) (`BSL-1.1`), (c) Mohamed Benoughidene.

- **You may use, copy, modify, and redistribute Ember for free** as long as the use stays inside your own organization or is personal: learning, development, testing, personal projects, and internal tools included.
- **Only selling Ember itself** (or a product or service built on or with it, including as a hosted service) to third parties requires a commercial license. Contact **mohamedbenoughidene@gmail.com**.
- **It ages into open source:** two years after a version is first published, that version automatically becomes available under the MIT License.
- Ember is not Open Source while under BSL 1.1; the license text says so itself.
- Contributions are welcome under the terms of [CLA.md](CLA.md): you keep ownership of what you write and grant the project a permanent license to use it, signed with a `Signed-off-by:` line in your commits.


## Contributing and security

- **Contribute:** Read the [Contributor License Agreement](CLA.md) first. You keep ownership of what you write, and you sign your commits with a `Signed-off-by:` line.
- **Report a security problem:** Follow the [security policy](SECURITY.md). Report it privately. Do not open a public issue.

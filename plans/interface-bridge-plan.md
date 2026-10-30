# L2 Plan: Interface Bridge (the structured door between the window and Python)

Status: DRAFT 2026-10-30, not yet through the review gate. Nothing is built.
Origin: `docs/ember-interface-spec.md` Implementation Decisions §3 (modules), §4 (gaps), §11 (platform); user stories 105 to 107.
L1: `plans/master-plan.md` §8, "Interface module amendment" items 1 and 2.
Needs first: `plans/engine-undo-plan.md` built (the bridge wraps `undo` and `redo` once).
Branch: `ember-interface`.

## Plain words (for the founder)

The window must never guess what a command printed. Today most commands print sentences for humans. This plan makes every command able to also print one clean data document, adds two small read commands the screens need, and lets the confirm step (yes / no / edit) talk through a pipe instead of a keyboard. The terminal keeps working exactly as before.

## §1 Purpose (one job)

Give the app a stable, tested, machine-readable way to run every Ember command and answer its confirm questions, without a server and without changing what any command does. Every bridge call is a normal `ember` command run as a child process.

## §2 Facts this plan stands on (read 2026-10-30)

- Query commands (`current-state`, `topic-search`, `why`, `history`) and `capture-source` already print one JSON document on stdout. Their no-flag output is pinned by golden tests (`tests/fixtures/query/no_flags_golden.json`). They stay untouched.
- Write commands print text lines: `maintain`/`close-item`/`set-status`/`reverse-supersedes` print `format_report` lines; `edit-item`, `remove-link` print one line per change; `capture` and `relate` print a summary line `accepted: N, rejected: N, ...`; `backup` and `export` print one summary line; `db-check` prints a text report (`ember/cli.py`).
- Errors: one stderr line `error: <CODE> <Name> | <module.function> | <detail>`, exit 1; exit 2 for usage errors and user abort (`docs/commands.md` conventions).
- The confirm step is an injected port: `ConfirmPort.ask(prompt) -> str` and `write(text)` (`ember/capture/confirm_write.py:49-62`, relate and maintain have their own twins). The terminal versions are `TerminalConfirm`, `RelateTerminalConfirm`, `MaintainTerminalConfirm` in `ember/cli.py:101-154`. The port carries **pre-formatted text**, not structured data: `format_block` (capture) and `format_link_block` (relate) emit `key: <json value>` lines. The edit sub-questions are plain `ask` calls: "new type? (default X)", "new statement? (default X)", "new metadata? (default X)".
- The AI key is read from `EMBER_AI_API_KEY` or `OPENROUTER_API_KEY` in the process environment (`ember/adapters/llm.py`). The app can therefore hold the key itself and pass it to the child process. No Python change is needed for key storage.
- `current-state` omits Closed items; `topic-search` requires a query; `why` follows `depends_on` and `supports` only (spec §4 gaps). There is no read for "all items" or "an item with all its links".
- `relate` needs the optional package `sentence-transformers` and may download a model on first run (spec story 45).

## §3 Decision this plan makes (A/B, needs the maintainer)

How does the app talk to Python?

- **A (recommended): child processes, one per command.** The app runs `ember <command> --db <file> --format json`. Interactive commands run `--confirm json` and keep the process open: Ember writes event lines on stdout, the app writes answer lines on stdin. No port, no server (README promise). Tests use `CliRunner` / `subprocess` on the same commands (spec "one test seam"). Cost: the parse of the pinned text blocks (§5.4) is a contract between two sides, guarded by a round-trip test.
- **B: a new long-lived `ember serve-stdio` process** speaking a request/response protocol. One process, fast repeat calls. Cost: moves orchestration out of `cli.py` into a second entry point (the relate and capture wiring lives in `cli.py` bodies today, so this is a refactor of ~400 lines with 3 or more files touched), and a second place where rules can drift.

Everything below assumes A. If B is chosen the plan is rewritten.

## §4 Module layout

```
ember/bridge/__init__.py        (marks package)
ember/bridge/json_out.py        (pure: result models -> one JSON document string)
ember/bridge/json_confirm.py    (JSON-lines ConfirmPort for the three confirm loops)
ember/bridge/block_parse.py     (pure: parse the pinned text blocks into dicts)
ember/bridge/errors.py          (BRIDGE-000 .. 003)
ember/cli.py                    (new options on existing commands, 2 new read commands)
ember/query/...                 (list_items, show_item read models and run_ functions)
tests/bridge/...                (contract tests, one table row per command)
```

`ember/bridge/` is a leaf above the engines: it imports result models and ports, never an adapter (T9, architecture test extended). `cli.py` stays the only composition root.

## §5 Contracts

### §5.1 `--format text|json` (a choice, not a flag; I2)
Added to the write and utility commands: `capture-source` (already JSON, accepts the option as a no-op `json`), `set-validated`, `clear-validated`, `maintain`, `close-item`, `set-status`, `reverse-supersedes`, `edit-item`, `remove-link`, `undo`, `redo`, `backup`, `export`, `db-check`. Default `text` keeps today's output byte for byte (pinned by existing tests). `json` prints exactly one document on stdout: `{"command": "...", "dry_run": bool, "changes": [...], "summary": {...}}`. The `changes` shape is the existing result model (`StatusChange`, `EditChange`, `LinkChange`, `BackupReport`, `ExportData` counts), so no second definition of any fact (D3). Query commands do not get the option (already JSON).

### §5.2 Errors
Unchanged: stderr line `error: CODE Name | where | detail`, exit 1 (usage/abort exit 2). The app parses this line. A contract test pins its shape for every code family (`CAPTURE-`, `RELATE-`, `MAINTAIN-`, `QUERY-`, `BACKUP-`, `EXPORT-`). Plain-language sentences for each code live in the app (L2 app §5.6), not here.

### §5.3 Two new read-only commands (additive, I10)
- `ember list-items [--status S] [--type T] [--limit N] [--offset N] [--db PATH]` — every item in any status (fills the Home/Look up gap), through `open_query_database` (read-only, floor 10). Same validators and `QUERY-006` as `topic-search`. One JSON document: `{"total": N, "items": [...]}`; each item carries id, type, statement, status, close_reason, rationale, source, validated, created_at. Hash-proven read-only.
- `ember show-item --item N [--db PATH]` — one item with its source text, and ALL its links in both directions with status and `reversed_at`, plus the other item's id, type, statement and status. This is the provenance read ("Challenged by", "Replaced by", spec §4). Unknown id → `QUERY-001`.

### §5.4 `--confirm terminal|json` on `capture`, `relate`, `maintain`
- `terminal` (default) = today.
- `json`: the JSON confirm port. Events on stdout, one JSON object per line, flushed:
  `{"event":"block","kind":"item"|"link"|"close","fields":{...},"text":"<original block>"}`,
  `{"event":"prompt","text":"<prompt>","choices":["y","n","e","q"]}`,
  `{"event":"message","text":"..."}`,
  `{"event":"summary",...}`.
  Answers: one line `{"answer":"y"}` on stdin. End of input raises the engine's existing `UserAbort` (exit 2), exactly like the terminal.
- `fields` come from `block_parse.py` parsing the pinned block (`key: <json>` lines). `text` always carries the raw block, so a parse failure degrades to showing text, never to losing data. A round-trip test builds blocks with the real `format_block` / `format_link_block` / `format_proposal_block` and asserts the parser recovers every field; if any formatter changes, that test fails first.
- No engine change: the engine still receives plain strings.

## §6 Error codes (new namespace, I17)

| Code | Name | Raised at |
|---|---|---|
| BRIDGE-000 | BridgeError | base, never raised directly |
| BRIDGE-001 | AnswerLineInvalid | `json_confirm`: stdin line is not `{"answer": <string>}` (then re-asks; second bad line aborts) |
| BRIDGE-002 | BlockParseFailed | internal only: `block_parse` could not read a block; the event is still sent with `fields: null` (never fatal) |
| BRIDGE-003 | FormatUnsupported | `--format json` asked of a command that lacks it (guard for tests) |

Reused unchanged: all engine codes; `QUERY-001`, `QUERY-006` on the new reads.

## §7 Test targets (T1 to T4)

1. **Contract table test** (`tests/bridge/test_contract_table.py`): one row per command (22) with: its flags, its JSON top-level keys under `--format json`, its text output unchanged under `text`, its exit codes. Fails when a command is added without a row (same idea as `test_docs_in_sync.py`).
2. **Unit:** `json_out` renders each result model; `block_parse` round-trips real blocks (including quotes with colons, non-ASCII, `null` warning); `json_confirm` ask/write on in-memory pipes; bad answer line → `BRIDGE-001`.
3. **Integration, real temp DB:** every write command, text vs json, same DB state; `list-items` returns Closed items and the correct total; `show-item` lists a Rejected and a reversed link; read-only hash proof for both new reads.
4. **E2E (one):** `capture --confirm json` with a fake AI and scripted stdin: block, prompt, `e` edit sub-prompts, confirm, summary; DB state equals the terminal run on the same input.
5. **Not covered:** the real AI round trip and the first-run model download of `relate` (existing live tests cover the AI). Manual check: run `ember relate --latest --confirm json` once with a real key.

## §8 Steps (L3)

| # | File | Phase |
|---|---|---|
| 01 | `plans/steps/bridge/01-format-json.md` | `--format json` on write and utility commands |
| 02 | `plans/steps/bridge/02-list-items-show-item.md` | Two new read commands |
| 03 | `plans/steps/bridge/03-json-confirm.md` | `--confirm json` for capture, relate, maintain |
| 04 | `plans/steps/bridge/04-contract-suite-and-closeout.md` | Contract table, docs, map |

## §9 Deferred to L3
- Exact JSON key names inside `summary` per command (step 01, bounded by §5.1: only existing result-model fields).
- Whether `db-check --format json` reuses the report's own fields or a new model (step 01; must not duplicate check logic, D3).
- Whether `maintain` Phase 5 accepted-close lines are streamed as `message` events or only in `summary` (step 03).

## §Z Constitution compliance

- **B1** one job: structured I/O. **B2** uses only public result models and ports. **B3** no rule lives in the bridge. **B5** three small deep modules, one entry point each.
- **D1** nothing stored differently. **D3** results reuse the engine models; no copies. **D4** stdin answers are untrusted input, validated once at the edge (`BRIDGE-001`). **D5** options are additive.
- **P2** UI → command layer → logic → data. **P3** `block_parse`: text in, dict out, no hidden state. **P4** `json_confirm` is an adapter for the existing `ConfirmPort`.
- **I1** names by job. **I2** `--format`/`--confirm` are choices, not boolean flags (to be tested at review). **I3** ≤ 4 inputs. **I4** named results. **I5-I7** named errors, never swallowed. **I9** validate at the edge. **I10** defaults keep old behaviour. **I12** stdout data, stderr errors, exit codes unchanged. **I16** raw AI answers still saved by the engine (D8 untouched). **I17-I21** BRIDGE-001..003 stable; tests assert codes.
- **T1** `json_out` and `block_parse` pure. **T2** pipes and process I/O at the edge. **T3** in-memory pipes as fakes. **T4** pyramid §7. **T9** architecture test extended to `ember/bridge/`.
- **S1** every command has a sample in the contract table. **S2** `tests/bridge/` isolated. **S3/S4** shapes and the pipe protocol documented in §5.

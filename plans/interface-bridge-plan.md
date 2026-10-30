# L2 Plan: Interface Bridge (the structured door between the window and Python)

Status: BUILT (2026-10-30). Maintainer gate passed (2026-10-30: D1 = child processes option A, D2 = embedder stays unfakeable, one manual check owed, option A, D3 = key test is shape-check at save + real refusal at first Add, NO `ember check-key` command). Steps 01-04 landed on `ember-interface`: Bridge 02 `77d1bbd`, merge `2f7fe24`, Bridge 01 `5a4fa7e`, Bridge 03 `46bcdc3`, plus the step-04 closeout commit carrying this note; suite 1164 passed, 4 deselected. Known handoffs: the D2 manual check (`ember relate --latest --confirm json` once with a real key) is still owed before the app's relate screen ships; stories 5/8 stay PARTIAL per D3 (the real refusal at first Add is the app's to build); `capture` and `relate` carry the `--format` flag without using it (shared `OutputOptions` bundle, see `archive/interface-deviations.md`); the app parsers read the shapes pinned in `tests/bridge/test_contract_table.py` and L2 §5.
Origin: `docs/ember-interface-spec.md` Implementation Decisions §3 (modules), §4 (gaps), §11 (platform); user stories 105 to 107.
L1: `plans/master-plan.md` §8, "Interface module amendment" items 1 and 2.
Needs first: `plans/engine-undo-plan.md` built (the bridge wraps `undo` and `redo` once).
Branch: `ember-interface`.

## Plain words (for the founder)

The window must never guess what a command printed. Today most commands print sentences for humans. This plan lets the commands the screens need also print one clean data document, adds two small read commands, and lets the confirm step (yes / no / edit) talk through a pipe instead of a keyboard. The terminal keeps working exactly as before.

## §1 Purpose (one job)

Give the app a stable, tested, machine-readable way to run Ember commands and answer their confirm questions, without a server and without changing what any command does.

## §2 Facts this plan stands on (read 2026-10-30)

- Query commands (`current-state`, `topic-search`, `why`, `history`) and `capture-source` already print one JSON document. **Only `topic_search`, `history` and `history_item_1` are pinned byte-for-byte** (`tests/fixtures/query/no_flags_golden.json`); `current-state` and `why` have no golden today.
- Write commands print text lines: the `format_report` lines, `item N: field edited`, `link N: ...`, the summaries `accepted: N, rejected: N, ...`, `backup written: ...`, and the `db-check` report (`ember/cli.py`).
- **Prints that bypass the confirm port:** the `capture` body prints `dropped proposal: ...`, `0 valid proposals`, `rejected by gatekeeper: ...` and the final summary with `click.echo`; the `relate` body prints `relate rejected: CODE | detail` lines after the loop and the final summary; `maintain` prints its sweep report and the stale-cap note. None of these go through `ConfirmPort.write`. With a JSON event stream on stdout they would corrupt it.
- Errors: one stderr line `error: <log_line()>` and exit 1; exit 2 for usage errors and user abort. `log_line()` is `"CODE Name" | location | message | k=v k=v` (the context field is absent when there is none; `ember/errors.py`), and free text can reach it (a raw `--reason`, an OpenAI error string) so a value may contain `|` or a newline.
- `ConfirmPort.ask(prompt) -> str` and `write(text)` carry **pre-formatted text**; the three terminal versions are in `ember/cli.py:101-154`. The real texts differ by engine:
  - capture: before the prompt, `format_block` prints `- id: N`, `  type: "..."`, `  statement: "..."`, `  source_quote: "..."`, `  confidence: 0.9` (bare), `  metadata: ...`, `  near_dup_warning: null` or `{matching_item_id: 3, similarity: 0.91}` (NOT valid JSON); prompt `[y]es / [n]o / [e]dit / [q]uit`; edit asks `new type? (default X)`, `new statement? (default X)`, `new metadata? (default X)`.
  - relate: before the prompt, a preview `Proposal i/n: item a -> item b [type]` plus `  rationale: ...`; AFTER a `y` it prints the `format_link_block` YAML (`- link_id: ...`); prompt `[y]es / [n]o / [s]kip / [q]uit`.
  - maintain Phase 5: `format_proposal_block` returns lines `Proposal i/n: item N [type] statement`, `  newest answers link ...`, `  reason: X, confidence Y`, `  rationale: Z` (values NOT JSON-quoted); prompt `[y]es / [n]o / [q]uit`.
- The AI key is read from `EMBER_AI_API_KEY` or `OPENROUTER_API_KEY`; the model and base URL from `EMBER_AI_MODEL`, `EMBER_AI_BASE_URL` (`ember/adapters/llm.py`). The embedder reads only `EMBER_EMBEDDER_MODEL` and a timeout (`ember/adapters/embedder.py`): **there is no way to inject a fake embedder into a child process.**
- `capture` without `--file` reads ALL of stdin (`ember/capture/input_reader.py`); the 5 MiB limit applies to `--file` only.
- `open_query_database` is read-only, floor 10, never migrates; `links.reversed_at` exists only from migration 011.
- Only `maintain`, `close-item`, `edit-item`, `remove-link` have `--dry-run` today (`set-status`, `reverse-supersedes` do not).
- No read gives "all items" or "an item with all its links"; `current-state` omits Closed; `topic-search` needs a query.

## §3 Decision this plan makes (A/B, needs the maintainer)

How does the app talk to Python?

- **A (recommended): child processes, one per command.** The app runs `ember <command> --db <file> --format json`. Interactive commands run `--confirm json` and keep the process open: events on stdout, answers on stdin. No port, no server. Tests use `CliRunner` / `subprocess` on the same commands. Cost: the parse of the engines' text blocks (§5.4) is a contract between two sides, guarded by round-trip tests.
- **B: a long-lived `ember serve-stdio` process** with a request/response protocol. Cost: moves ~400 lines of orchestration out of `cli.py` into a second entry point (3 or more files) and creates a second place where rules can drift.

Everything below assumes A.

## §4 Module layout

```
ember/bridge/__init__.py            (marks package; PURE code only)
ember/bridge/json_out.py            (pure: plain dicts/models -> one JSON document string)
ember/bridge/block_parse.py         (pure: one parser per engine formatter; text -> ParsedBlock)
ember/adapters/json_confirm.py      (ADAPTER: the JSON-lines ConfirmPort classes and the output sink; reads stdin, writes stdout)
ember/adapters/errors.py            (BRIDGE-000, BRIDGE-001 added beside BackupError/ExportError)
ember/cli.py                        (OutputOptions, new options on existing commands, 2 new read commands)
ember/query/...                     (list_items, show_item read models and run_ functions)
tests/bridge/...                    (contract tests)
```

`ember/bridge/*.py` imports no adapter (T9). `json_out` therefore never receives `BackupReport`, `ExportData` or `DbCheckReport` (they live in `ember/adapters/`); `cli.py` turns each into a plain dict before calling the renderer. `json_confirm` reads stdin and writes stdout, so it is an adapter and lives in `ember/adapters/`. `tests/test_architecture.py` gains `test_bridge_core_does_not_import_adapters` over `ember/bridge/*.py`. `cli.py` stays the only composition root.

## §5 Contracts

### §5.1 `--format text|json` (a choice, branched only in the CLI body; I2)
The branch `render = render_json if fmt == "json" else render_text` happens ONLY in `cli.py`; no engine or renderer function takes a `fmt` or `mode` argument (a named test greps for it). A small frozen `OutputOptions(fmt, confirm)` built by a shared Click decorator keeps handlers at ≤ 4 inputs (I3).

Commands that gain `--format [text|json]` (default `text`, unchanged byte for byte): `maintain`, `close-item`, `set-status`, `reverse-supersedes`, `edit-item`, `remove-link`, `undo`, `redo`, `backup`, `db-check`. Not added (no screen needs it): `capture-source` (already JSON), `set-validated` / `clear-validated` (the app re-reads with `show-item`), `export` (the app only needs the exit code and the `--out` path it chose). Query commands are untouched (already JSON).

JSON shape: one document, sorted keys, `ensure_ascii=False`: `{"command": "...", "changes": [...], "summary": {...}}`; a dry run is stated INSIDE the document (`"dry_run": true` is a model field, not a renderer argument). `changes` reuse the engine models (`StatusChange`, `EditChange`, `LinkChange`, `UndoResult`), so no second definition of any fact (D3). The `undo` / `redo` documents pin the keys `source_group_id`, `source_action`, `target_label` (story 113).

### §5.2 Errors (the app's parsing rule)
Unchanged stderr line, exit 1 (usage/abort exit 2). The app reads the FIRST stderr line, matches `\Aerror: (?P<code>[A-Z]+-\d{3}) (?P<name>\w+) \| (?P<where>[^|\n]+) \| (?P<rest>.*)\Z` with `re.S` (so a newline or `|` in free text cannot break it), and treats any further stderr lines as continuation of `rest`. `log_line()` is not changed. The contract test includes one case with a newline and a `|` in a value (for example a `--reason` containing both). The same pattern lives in a shared fixture file read by the Python tests and by the app tests. Plain-language sentences live in the app (app L2 §5.6).

### §5.3 Two new read-only commands (additive, I10)
- `ember list-items [--status S] [--type T] [--limit N] [--offset N] [--db PATH]` — every item in any status, through `open_query_database`. Same validators and `QUERY-006` as `topic-search`. `{"total": N, "items": [...]}`; each item: id, type, statement, status, close_reason, rationale, source, validated, created_at. Hash-proven read-only.
- `ember show-item --item N [--db PATH]` — the item, its source text verbatim, and ALL its links in both directions with status, the other item's id/type/statement/status, and `reversed_at`. **`reversed_at` is selected only when the column exists** (`PRAGMA table_info(links)`); on a v10 file it is `null` and nothing fails. Unknown id -> `QUERY-001`.

### §5.4 `--confirm terminal|json` on `capture`, `relate`, `maintain`
- `terminal` is today's behaviour. `json` selects the JSON confirm classes (a real choice of adapter at the composition root, P4).
- **Output sink.** Every `click.echo` in the `capture`, `relate` and `maintain` bodies goes through one sink object. In `terminal` mode it echoes exactly as today. In `json` mode it emits `message` events and the final summary line becomes the `summary` event. `cli.py` bodies change; the engines do not. A test asserts that every stdout line under `--confirm json` parses as JSON.
- Events, one JSON object per line, flushed: `{"event":"block","kind":"item"|"link-preview"|"link"|"close","fields":{...}|null,"text":"..."}`, `{"event":"prompt","kind":"choice"|"type"|"statement"|"metadata","text":"...","choices":[...]}`, `{"event":"message","text":"..."}`, `{"event":"summary",...}`. `choices` come from each engine's `PROMPT` constant, never hard-coded. Answers: one line `{"answer":"<text>"}` on stdin.
- `block_parse.py` has ONE parser per formatter (capture block, relate preview, relate link block, maintain proposal), each reading the real shapes in §2. `fields` is `null` when a parse fails and `text` always carries the raw block, so a parse failure shows text and never loses data. Round-trip tests build blocks with the REAL formatters, including a non-null near-duplicate warning, quotes containing `: `, emoji and long text, and fail first if any formatter changes. (Structured `*_fields` functions beside each formatter would remove the parser; that is an engine change and is deferred, not planned.)
- End of input, or a second bad answer line, raises the engine's own `UserAbort` (exit 2); a bad line is first answered by raising `BRIDGE-001` internally and re-asking once.
- **Stdin conflict:** `capture --confirm json` requires `--file` (the app writes pasted text to a temp file); `capture` with `--confirm json` and no `--file` exits with a usage error (exit 2).

## §6 Error codes (new, I17)

| Code | Name | Raised at |
|---|---|---|
| BRIDGE-000 | BridgeError | base, never raised directly |
| BRIDGE-001 | AnswerLineInvalid | `json_confirm`: a stdin line is not `{"answer": <string>}` (re-ask once; a second bad line aborts with the engine `UserAbort`, exit 2) |

(The draft's `BRIDGE-002` and `BRIDGE-003` are removed: one was never fatal, the other is covered by Click's exit 2.) Reused unchanged: all engine codes; `QUERY-001`, `QUERY-003`, `QUERY-004`, `QUERY-006` on the new reads.

## §7 Test targets (T1 to T4)

1. **Contract table** (`tests/bridge/test_contract_table.py`): one row per command (22) with sample args, JSON top-level keys, whether `--format`/`--confirm` apply, exit codes. Fails when a command is added without a row.
2. **Unit:** `json_out` per model; `block_parse` round trips with REAL formatters; `json_confirm` on in-memory pipes; `BRIDGE-001`; a grep test that no non-CLI function takes `fmt`/`mode`.
3. **Integration, real temp DB:** every write command text vs json, same DB state (hash); `list-items` returns Closed items and the right total; `show-item` lists Rejected and reversed links, works on a v10 file; read-only hash proof for both reads; every stdout line parses under `--confirm json`.
4. **E2E (one):** `capture --file note.txt --confirm json` with a fake AI over the existing seam and scripted stdin: block, prompt, edit sub-prompts, confirm, summary; DB equals the terminal run on the same input.
5. **Not covered:** the real AI round trip and the first-run model download of `relate`. Manual check once with a real key. Cross-process fakes: the AI can be faked by a local server on `EMBER_AI_BASE_URL`; **the embedder cannot** (decision D2 below).

## §8 Steps (L3)

| # | File | Phase |
|---|---|---|
| 01 | `plans/steps/bridge/01-format-json.md` | `--format json` on the ten commands, `OutputOptions` |
| 02 | `plans/steps/bridge/02-list-items-show-item.md` | Two new read commands |
| 03 | `plans/steps/bridge/03-json-confirm.md` | Output sink, `--confirm json`, block parsers |
| 04 | `plans/steps/bridge/04-contract-suite-and-closeout.md` | Contract table, architecture test, docs, map |

## §9 Deferred to L3
- Exact JSON key names inside `summary` per command (step 01; only fields that exist on the result models).
- Whether `db-check --format json` reuses the report's own fields (step 01; must not duplicate check logic).
- Whether accepted-close lines in `maintain` are streamed as `message` events (step 03: yes, in order, like the terminal).

## §10 Decisions for the maintainer at the L2 gate
- **D1:** child processes (A, recommended) or `serve-stdio` (B). See §3.
- **D2 (embedder seam):** Link items cannot be tested end to end in a child process without the real model. **A:** accept it ("Not covered by tests", one manual check with the real model). **B:** add a test-only setting, for example `EMBER_EMBEDDER_FAKE=1`, to the embedder factory (a Python change, one more thing that can ship by mistake). Recommended: A.
- **D3 (key test):** see app L2 §3 (it may add a command to this plan).

## §Z Constitution compliance

- **B1** one job: structured I/O. **B2** uses only public result models and ports; `cli.py` converts adapter reports to plain dicts. **B3** no rule lives in the bridge. **B5** two small pure modules and one adapter.
- **D1** nothing stored differently. **D3** results reuse the engine models. **D4** stdin answers are untrusted, validated once at the edge (`BRIDGE-001`). **D5** options are additive.
- **P2** UI -> command layer -> logic -> data (the bridge is a leaf at the top). **P4** `json_confirm` is an adapter for the existing `ConfirmPort`, chosen at the composition root.
- **I1** names by job. **I2** `--format` / `--confirm` are choices branched only in `cli.py`; a named test enforces it (the existing `--dry-run` flags are untouched). **I3** `OutputOptions` keeps handlers ≤ 4 inputs (the existing 5-input `edit_item` is brought under 4 in step 01). **I4** named returns (`ParsedBlock` with `parsed: bool` and a possibly empty `fields`, never `None`). **I5-I7** named errors, never swallowed. **I9** validate at the edge. **I10** defaults keep old behaviour. **I12** stdout data, stderr errors, exit codes unchanged. **I16** raw AI answers still saved by the engine (D8 untouched). **I17-I21** `BRIDGE-001` stable; tests assert codes.
- **T1** `json_out` and `block_parse` pure. **T2** pipes and process I/O in the adapter. **T3** in-memory pipes as fakes. **T4** pyramid §7. **T9** architecture test extended to `ember/bridge/*.py`.
- **S1** every command has a sample in the contract table. **S2** `tests/bridge/` isolated. **S3/S4** shapes and the pipe protocol documented in §5.

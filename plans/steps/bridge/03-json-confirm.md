# L3 Bridge Step 3: output sink, JSON confirm, block parsers

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-bridge-plan.md` §5.4. Phase: interactive commands. Needs step 01.

## Constitution rules this step enforces
P4 (the JSON confirm is an adapter for the existing `ConfirmPort`, chosen at the composition root), D4 (stdin validated once), T1 (`block_parse` pure), T3 (in-memory pipes), T9 (`ember/bridge/*.py` imports no adapter), I5/I7, I17-I20, B3.

## Deferred settings resolved by this step
- Whether Phase-5 accepted-close lines are `message` events (L2 §9): yes, in order, as the terminal prints them.

## 1. Boundary shapes (cite L2 §4, §5.4, §6)
- `ember/adapters/json_confirm.py` (adapter): three thin classes satisfying the three existing `ConfirmPort` protocols, differing only in which `UserAbort` they raise (same reason the three terminal classes differ), plus the **output sink**. Output is flushed after every line.
- **Output sink:** every `click.echo` in the `capture`, `relate`, `maintain` bodies of `cli.py` goes through the sink. `terminal` mode = identical bytes to today. `json` mode = `message` events and a final `summary` event. `cli.py` bodies change; engines do not.
- `ember/bridge/block_parse.py` (pure): `parse_capture_block`, `parse_link_preview`, `parse_link_block`, `parse_close_proposal_block`, each returning `ParsedBlock(parsed: bool, fields: dict)` (never `None`, I4). Shapes are exactly those in L2 §2: capture `near_dup_warning` is `null` or `{matching_item_id: N, similarity: X}` (not JSON), `confidence` is bare, maintain values are not quoted. `text` always carries the raw block.
- Events: `block` (kind `item`, `link-preview`, `link`, `close`), `prompt` (kind `choice`, `type`, `statement`, `metadata`; `choices` from each engine's `PROMPT` constant), `message`, `summary`. Relate: the preview is sent as `link-preview` BEFORE the prompt, the YAML link block as a `link` message AFTER a `y`.
- `capture`, `relate`, `maintain` gain `--confirm [terminal|json]` (default `terminal`). `capture --confirm json` without `--file` is a usage error (exit 2) because stdin carries the answers.
- Answers: one line `{"answer": "<text>"}`. An invalid line raises `BRIDGE-001` (re-ask once); a second invalid line, or end of input, raises the engine's `UserAbort` (exit 2). Engines write only after a confirm, so nothing is half-written.

## 2. Tests
- `tests/bridge/test_block_parse.py`: round trip using the REAL formatters (`format_block`, the relate preview and `format_link_block`, `format_proposal_block`), including a non-null near-duplicate warning, quotes containing `: `, emoji, long text; a deliberately broken block -> `parsed=False`, raw text kept.
- `tests/bridge/test_json_confirm.py`: scripted pipes drive the real `run_confirm_loop`, `confirm_links`, `run_close_proposals` with fake proposers; `e` triggers the three sub-prompts as `prompt` events; end of input -> engine abort path, exit 2; a bad line -> `BRIDGE-001` then re-ask.
- **Every stdout line under `--confirm json` parses as JSON** (including dropped-proposal, gatekeeper-rejection and relate-rejection lines).
- Terminal bytes unchanged: golden of `capture`, `relate`, `maintain` terminal outputs captured before the step.
- Parity E2E: `capture --file note.txt --confirm json` and the terminal run (same scripted keys) leave identical DB state and ledger rows.
- No-key path: missing key exits 1 before any event is sent.

## 3. CLI check (S1)
```
$ printf '{"answer":"y"}\n' | ember capture --file note.txt --confirm json --db t.db    (fake AI via the existing seam)
{"event":"block","kind":"item","fields":{"id":1,"type":"Decision",...},"text":"- id: 1\n  type: ..."}
{"event":"prompt","kind":"choice","text":"[y]es / [n]o / [e]dit / [q]uit","choices":["y","n","e","q"]}
{"event":"summary","accepted":1,"rejected":0,"warnings":0,"aborted":false}    [exit 0]
```

## 4. Error codes raised (L2 §6)
BRIDGE-001. Engine abort codes unchanged (exit 2).

## 5. Rollback
Revert the commit. Defaults unchanged.

## 6. Done when
Parity test passes for all three commands; round-trip test passes; terminal goldens unchanged; suite green with real counts. Manual check (not covered by tests): run `ember relate --latest --confirm json` once with a real key and read the events.

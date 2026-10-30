# L3 Bridge Step 3: the JSON confirm port

Status: DRAFT 2026-10-30. Parent: `plans/interface-bridge-plan.md` §5.4. Phase: interactive commands. Needs step 01 (summary shape).

## Constitution rules this step enforces
P4 (an adapter for the existing `ConfirmPort`, engine untouched), D4 (stdin is outside data, validated once), T1 (`block_parse` pure), T3 (in-memory pipes), I5/I7, I17-I20, B3.

## Deferred settings resolved by this step
- Whether Phase-5 accepted-close lines are `message` events or only part of `summary` (L2 §9). Contract: they stay `message` events, in order, because the terminal prints them in order.

## 1. Boundary shapes (cite L2 §5.4, §6)
- `ember/bridge/block_parse.py`: `parse_block(text) -> ParsedBlock | None`. Input: the pinned `key: <json value>` lines from `format_block` (capture), `format_link_block` (relate) and `format_proposal_block` (maintain Phase 5, read the real formatter first; its lines are pinned in `tests/maintain/test_close_proposals_cli.py`). `None` when unreadable (the event then carries `fields: null`).
- `ember/bridge/json_confirm.py`: three thin classes satisfying the three existing `ConfirmPort` protocols, differing only in which `UserAbort` they raise (same reason the three terminal classes differ: `CAPTURE`/`RELATE-031`/`MAINTAIN-022` codes). One shared helper builds events. Output is flushed after every line.
- `capture`, `relate`, `maintain` gain `--confirm [terminal|json]` (default `terminal`). `json` implies the final summary is an `event: summary` object (built by step 01's renderer).
- Answer rules: one line `{"answer": "<text>"}`. Invalid line → `BRIDGE-001`, re-prompt once, second invalid → treated as end of input (abort, exit 2, nothing half-written because the engines write only after a confirm).

## 2. Tests
- `tests/bridge/test_block_parse.py`: round trip with real formatters; quotes containing `: `, emoji, long text; `null` near-dup warning; a deliberately broken block → `None`.
- `tests/bridge/test_json_confirm.py`: scripted pipes drive the real `run_confirm_loop`, `confirm_links`, `run_close_proposals` with fake proposers; `e` triggers the three sub-prompts as `prompt` events; end of input → engine abort path, exit 2.
- Parity E2E: `capture --confirm json` and `capture` (terminal, same scripted keys) leave identical DB state and identical ledger rows (compare dumps).
- No-key path: missing key still exits 1 with the existing code before any event is sent (an `error:` stderr line, no stdout events).

## 3. CLI check (S1)
```
$ printf '{"answer":"y"}\n' | ember capture --file note.txt --confirm json --db t.db    (fake AI via env seam used by existing CLI tests)
{"event":"block","kind":"item","fields":{"id":1,"type":"Decision",...},"text":"- id: 1\n  type: ..."}
{"event":"prompt","text":"[y]es / [n]o / [e]dit / [q]uit","choices":["y","n","e","q"]}
{"event":"summary","accepted":1,"rejected":0,"warnings":0,"aborted":false}    [exit 0]
```

## 4. Error codes raised
BRIDGE-001, BRIDGE-002 (internal, non-fatal). Engine abort codes unchanged (exit 2).

## 5. Rollback
Revert the commit. Defaults unchanged.

## 6. Done when
Parity test passes for all three commands; round-trip test passes; suite green with real counts. Manual check (not covered by tests): run `ember relate --latest --confirm json` once with a real key and read the events.

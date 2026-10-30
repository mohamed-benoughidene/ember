# L3 Bridge Step 1: `--format json` on write and utility commands

Status: DRAFT 2026-10-30. Parent: `plans/interface-bridge-plan.md` §5.1. Phase: structured output. Needs the Undo L2 built.

## Constitution rules this step enforces
D3 (reuse result models), I2 (a choice option, not a boolean flag), I10 (default unchanged), I12, T1 (renderer pure), T9, B3.

## Deferred settings resolved by this step
- JSON key names inside `summary` per command (L2 §9): only fields that already exist on the result models; no invented fields.
- `db-check --format json`: the check function already returns a typed report; render that, do not re-run checks in the renderer.

## 1. Boundary shapes (cite L2 §5.1)
- `ember/bridge/json_out.py`: pure renderers, one per result model: `render_changes(command, dry_run, changes, summary) -> str`, plus `render_backup`, `render_export_summary`, `render_db_check`. Output is one JSON document with sorted, stable key order and `ensure_ascii=False`.
- Commands that gain `--format [text|json]` (default `text`): `set-validated`, `clear-validated`, `maintain`, `close-item`, `set-status`, `reverse-supersedes`, `edit-item`, `remove-link`, `undo`, `redo`, `backup`, `export`, `db-check`; `capture-source` accepts it as a no-op.
- `export --format json` with no `--out` still prints the rendered export text (that file is the export format itself); the option then only changes the `--out` summary line to JSON. Stated so no one expects a JSON export.
- Under `--format json` errors are unchanged (stderr line, exit 1).

## 2. Tests
- For each command: run with `text` and `json` on identical seeded temp DBs: same resulting DB bytes (hash); `text` stdout equals the pre-step golden (capture goldens BEFORE the change in the first commit of the step); `json` stdout parses and has the pinned keys.
- `--dry-run` + `json` writes zero rows (hash).
- Unknown value `--format xml` → exit 2 (Click).
- Renderer unit tests: no I/O, deterministic.

## 3. CLI check (S1)
```
$ ember close-item --item 1 --reason expired --dry-run --format json --db t.db
{"changes":[{"item_id":1,"new_status":"Closed",...}],"command":"close-item","dry_run":true,"summary":{...}}   [exit 0]
$ ember close-item --item 1 --reason expired --db t.db        -> the old text lines, unchanged   [exit 0]
```

## 4. Error codes raised
Engine codes unchanged. `BRIDGE-003` only inside the guard test.

## 5. Rollback
Revert the commit. Options are additive; default behaviour never changed.

## 6. Done when
Whole suite passes with real counts; every golden unchanged; contract-table rows for these commands added.

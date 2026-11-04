# L3 Bridge Step 1: `--format json` on ten commands

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-bridge-plan.md` §5.1. Phase: structured output. Needs the Undo L2 built.

## Constitution rules this step enforces
D3 (reuse result models), I2 (a choice option branched only in `cli.py`), I3 (`OutputOptions`), I10 (default unchanged), I12, T1 (renderer pure), T9, B3.

## Deferred settings resolved by this step
- JSON key names inside `summary` per command (L2 §9): only fields that already exist on the result models.
- `db-check --format json`: the check function already returns a typed report; `cli.py` turns it into a plain dict, the renderer never re-runs checks.

## 1. Boundary shapes (cite L2 §4, §5.1)
- First commit of the step, before any change: raw-stdout fixtures for the ten commands in `text` mode (the "before" goldens), plus `current-state` and `why` if the Undo plan has not already captured them.
- `ember/bridge/json_out.py`: pure renderers taking plain dicts or engine models (never `BackupReport`, `ExportData`, `DbCheckReport`, which live in `ember/adapters/`): one JSON document, sorted keys, `ensure_ascii=False`. A dry run is a field of the document, not a renderer argument.
- `OutputOptions(fmt, confirm)` built by a shared Click decorator. Handlers stay at ≤ 4 inputs; `edit_item` (5 inputs today) is brought under the limit in this step.
- Commands that gain `--format [text|json]` (default `text`): `maintain`, `close-item`, `set-status`, `reverse-supersedes`, `edit-item`, `remove-link`, `undo`, `redo`, `backup`, `db-check`. NOT `capture-source`, `set-validated`, `clear-validated`, `export`.
- Under `--format json` errors are unchanged (stderr line, exit 1).
- `undo` / `redo` documents pin `source_group_id`, `source_action`, `target_label`.

## 2. Tests
- For each command: `text` and `json` on identical seeded temp DBs: same resulting DB bytes (hash); `text` stdout equals the "before" golden; `json` parses and has the pinned keys.
- `--dry-run` + `json` writes zero rows (hash).
- Unknown value `--format xml` -> exit 2 (Click).
- A named test greps `ember/` and fails if any function outside `cli.py` takes a parameter named `fmt` or `mode`.
- Renderer unit tests: no I/O, deterministic.

## 3. CLI check (S1)
```
$ ember close-item --item 1 --reason expired --dry-run --format json --db t.db
{"changes":[{"item_id":1,"new_status":"Closed",...}],"command":"close-item","dry_run":true,"summary":{...}}   [exit 0]
$ ember close-item --item 1 --reason expired --db t.db        -> the old text lines, unchanged   [exit 0]
```

## 4. Error codes raised (L2 §6)
Engine codes unchanged. No bridge code in this step.

## 5. Rollback
Revert the commit. Options are additive; default behaviour never changed.

## 6. Done when
Whole suite passes with real counts; every golden unchanged; contract-table rows for these commands added.

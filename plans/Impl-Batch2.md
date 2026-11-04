# Batch 2 implementation plan: the error boundary — one edge handler, house codes on every known failure, and the crash report in the app

Spec: docs/Spec-Batch2.md
Branch: batch-2, cut from where batch-1 merged (per archive/Plan.md D-29: each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` when its "Done when" passes). On 2026-11-01 that merge point sits on `ember-interface`; whether Batch 1 has landed is still open — see Unknowns.
Needs first: Batch 0 and Batch 1 (per archive/Plan.md §3 order; the Release chunk cannot run without Batch 1's .deb check script).
Size: 15 chunks, 45 steps (3 per chunk), about 24 hours.
Code numbers (decision I1): the three capture codes this plan pins — CAPTURE-017 DbOpenFailed, CAPTURE-018 TextNotEncodable, CAPTURE-019 BaseUrlInvalid — are confirmed by decision I1. Batch 7 will take the next free capture numbers when it is built, per I1 (numbers are never reused, D-27).

Code words used below, explained once:
- **house line** — the one error line Ember prints: `error: CODE Name | module.function | detail`. The regex that pins it lives in `tests/fixtures/bridge/error_parsing_rule.txt`.
- **crash file** — a text file hidden where the OS keeps app state; it keeps the full error trace with secrets removed.
- **edge handler** — one place at the program's exit door that catches errors, so every command does not need its own copy.

## Before you start

- Python tests (repo convention, venv is real — `ls .venv/bin/pytest` confirms it):
  - `.venv/bin/pytest tests/test_cli_error_boundary.py` — the new Batch 2 file (NEW).
  - `.venv/bin/pytest` — the whole Python suite (pyproject pins `testpaths = ["tests"]`, addopts `-q -m 'not live'`).
- App unit tests (run from `app/`): `npm test -- bridge-client` (the argument filters by filename; see `app/test/run.js`), `npm test` for all.
- App e2e (run from `app/`, only under xvfb): `xvfb-run -a npm run e2e -- add`.
- Safety rules (Constitution + Spec-Batch2 "Safety rules"): never set a real AI key — every engine command run by hand goes through `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY`; never open `~/.config/ember-app/ember.db` or `key.enc`; no GUI / Electron launch except inside the e2e harness (xvfb); every temp file goes under `/tmp/opencode/batch2/` (create it first: `mkdir -p /tmp/opencode/batch2`).
- The exit contract this batch must not break (verified in `ember/cli.py:322-324,397-402,522-526,618-620` and `docs/commands.md:10`): house errors exit 1, a user abort exits 2, a click usage error exits 2 with no code (decision N6).
- The house line format stays (`ember/errors.py:21-26` matches the pinned fixture; verified by `tests/bridge/test_error_contract.py`).

## Chunk 1 of 15: scrub key-shaped secrets from every error line

Covers: story 22; report findings 4.3 #23 and 4.10 #4 (spec "Secret scrubbing runs on the crash text and on every error context").

1. Add tests/test_secret_scrub.py (NEW), two tests: (a) `EmberError("x", detail="token sk-plant0987654321abcdef here").log_line()` contains neither the planted `sk-…` token nor the value of a monkeypatch-set `EMBER_AI_API_KEY`; (b) `ember.adapters.llm._without_secret("boom sk-plant0987654321abcdef", "sk-config0123456789")` returns neither key and stays under 200 chars.
2. Run `.venv/bin/pytest tests/test_secret_scrub.py`. Expect: 2 failed (today `log_line()` prints context raw, `ember/errors.py:21-26`; `_without_secret` strips only the exact key, `ember/adapters/llm.py:268-272`).
3. In `ember/errors.py`, add `scrub_secrets(text)` (NEW function): replaces the exact `EMBER_AI_API_KEY` / `OPENROUTER_API_KEY` values read from `os.environ`, and any `sk-`-shaped token, with `REDACTED`; call it inside `log_line()`. In `ember/adapters/llm.py`, make `_without_secret` call `scrub_secrets` before the 200-char trim.

Proof it's real: delete the `scrub_secrets(...)` call inside `log_line()` — test (a) turns red with the planted token on the line. Undo the deletion.
Done when: `.venv/bin/pytest tests/test_secret_scrub.py` prints 2 passed.
Commit message: `Batch 2: scrub key-shaped secrets from every error line`

## Chunk 2 of 15: the edge handler, EMBER-000, and the crash file

Covers: stories 1, 5, 6, 12, 16; report §6 forced-crash path, 4.6 #12 (the boundary catches the raw `sqlite3.Error` from `_newest_group_id`, `ember/cli.py:984-990`), 4.10 #17 (broken pipe). Decisions D-06, N4, N7.

1. Add tests/test_cli_error_boundary.py (NEW), two tests:
   - `test_forced_unexpected_exception_gives_one_ember_000_line_and_a_crash_file`: monkeypatch `ember.cli.store_source` to raise `RuntimeError("boom")` (the command calls the name imported into `ember.cli` — `ember/cli.py:72,321` — so patching `ember.capture.source_storage` would not be seen), set env `XDG_STATE_HOME` to a tmp dir and `EMBER_AI_API_KEY` to a planted fake, then `CliRunner().invoke(main, ["capture-source", "--db", db_path], input="hello")`. Assert: exit code 1; exactly one line on `result.stderr`; it starts with `error: EMBER-000 InternalError`; it names a `module.function` (the innermost traceback frame — the substitute's raise site); it carries `crash=` plus an id; and the file `XDG_STATE_HOME/ember/crashes/<that id>.txt` exists, contains `Traceback (most recent call last):` and `RuntimeError: boom`, and does not contain the planted fake key.
   - `test_broken_pipe_ends_with_a_house_line`: call the NEW edge function directly (name it `_handle_unexpected`, see step 3) with `BrokenPipeError()` injected under capsys; assert it prints one `error: EMBER-000` house line on stderr and raises exit 1.
2. Run `.venv/bin/pytest tests/test_cli_error_boundary.py`. Expect: 2 failed (today `ember/__main__.py` calls `main()` bare and no handler exists).
3. Implement: in `ember/cli.py` add `class EmberGroup(click.Group)` (NEW) overriding `invoke()` so it wraps the whole dispatch (the shared unexpected-exception print logic lives in one helper named `_handle_unexpected`, which test (b) calls directly); and `@click.group(cls=EmberGroup)`. In a NEW module `ember/crash_report.py` (NEW file): `crash_id()` (UTC timestamp + 6 hex chars), `crash_dir()` (honours `XDG_STATE_HOME`, default `~/.local/state/ember/crashes`), `write_crash_file()` — engine version, command name (no arguments), time, full traceback with full paths (N7), all through `scrub_secrets`. `EmberGroup.invoke` catches: `BrokenPipeError` → one `error: EMBER-000 InternalError | ember.cli.<command> | output pipe closed` line on stderr, exit 1, no crash file; any other non-`EmberError`, non-`SystemExit`, non-click exception → the crash file plus `error: EMBER-000 InternalError | <module.function of the innermost frame> | crash=<id>`, exit 1. The base class `ember/errors.py` `code`/`name` (`EMBER-000` / `EmberError`) stays untouched; the handler prints the `InternalError` name itself (check fix #4).

Proof it's real: temporarily make `EmberGroup.invoke` a plain `return super().invoke(ctx)` — both tests turn red (raw traceback). Undo.
Done when: `.venv/bin/pytest tests/test_cli_error_boundary.py` prints 2 passed, and by hand: `mkdir -p /tmp/opencode/batch2/state && echo hello | XDG_STATE_HOME=/tmp/opencode/batch2/state env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/ember capture-source --db /tmp/opencode/batch2/nodir/x.db` prints one `error: EMBER-000 ... crash=` line, exits 1, and leaves a crash file under `/tmp/opencode/batch2/state/ember/crashes/`.
Commit message: `Batch 2: one edge handler, EMBER-000, and the crash file`

## Chunk 3 of 15: error names come from the classes; context shows file names only

Covers: stories 20, 21; report findings 4.10 #11, part of 4.10 #4; N7 (the context half — the crash file already keeps full paths since Chunk 2).

1. Add tests/test_error_names.py (NEW), two tests: (a) walk every class in `ember/capture/errors.py`, `ember/query/errors.py`, `ember/relate/errors.py`, `ember/maintain/errors.py`, `ember/adapters/errors.py` and assert `cls.code`/`cls.name` exist and `cls.name == cls.__name__` (today 11 capture classes disagree — `ember/capture/errors.py:13-96`); (b) invoke `capture-source --db <tmp_path>/sub/dir/x.db` with `CliRunner` and assert the stderr house line does NOT contain `str(tmp_path)` (today every opener context passes the full path, e.g. `ember/adapters/sqlite.py:118`).
2. Run `.venv/bin/pytest tests/test_error_names.py`. Expect: 2 failed.
3. Implement: in `ember/capture/errors.py` change the 11 `name =` values to equal their class names (codes stay — codes are never renamed). In `ember/adapters/sqlite.py` and `ember/adapters/backup.py`, pass `os.path.basename(db_path)` at every `db_path=` context value on the open/schema raise sites (`sqlite.py:118,126,131,165,173,202-213,252-258`; `backup.py:112,117-119,123-125`).

Proof it's real: change one name back to the old spelling (e.g. `SourceFileNotFound.name = "FileNotFound"`) — test (a) fails. Undo.
Done when: `.venv/bin/pytest tests/test_error_names.py` prints 2 passed, and `grep -n "name = \"" ember/capture/errors.py` shows only names equal to the class above each.
Commit message: `Batch 2: error names from classes, file names only in error context`

## Chunk 4 of 15: remove the 19 copies of the error block

Covers: story 19; report finding 4.10 #13; story 16 and N6 (the handler now prints known errors; exit contract 1/2 kept).

1. Add to tests/test_cli_error_boundary.py (the NEW file from Chunk 2) a pin named `test_known_house_error_is_exactly_one_stderr_line_exit_1`: invoke `close-item --item 1 --reason "a | b"` on the seeded pair the way `tests/bridge/harness.py:157` `invoke()` does (or directly `CliRunner().invoke(main, [...])` after `harness.seed_pair(db_path)`); assert exit code 1 and exactly one stderr line matching the pinned regex from `tests/fixtures/bridge/error_parsing_rule.txt` with code `MAINTAIN-002`. (Passes today too — it pins the contract the removal must keep.)
2. Run `.venv/bin/pytest tests/test_cli_error_boundary.py tests/bridge/test_error_contract.py tests/test_docs_in_sync.py`. Expect: the new test 1 passed. Record the counts.
3. In `ember/cli.py`, delete all 19 `except EmberError:` → `click.echo(f"error: {exc.log_line()}", err=True)` → exit 1 blocks (lines 322-324, 397-399, 522-524, 618-620, 700-702, 751-753, 804-806, 866-868, 929-931, 1019-1021, 1082-1084, 1138-1140, 1163-1165, 1222-1224, 1244-1246, 1312-1314, 1359-1361, 1461-1463, 1493-1495 — counted today with `grep -n "error: " ember/cli.py`). The three `sys.exit(2)` abort lines (`:402`, `:526`, `:659`) stay; click usage errors stay click's (N6). Commands now raise; `EmberGroup` (Chunk 2) prints. If `tests/test_docs_in_sync.py` complains about `docs/commands.md`, update only the error-section wording there in the same commit.

Proof it's real: after the removal, temporarily delete the `EmberError` catch inside `EmberGroup.invoke` — the new one-line pin test fails with a raw traceback and 2 stderr lines. Undo.
Done when: `.venv/bin/pytest` (whole suite) prints all passed, and `grep -c "except EmberError" ember/cli.py` prints `0`.
Commit message: `Batch 2: commands raise; the edge handler prints every house line`

## Chunk 5 of 15: openers close their connection and raise a house code

Covers: stories 7, 8, 23; report findings 4.5 #1, 4.3 #4, 4.3 #11 (the leak half).

1. Add tests/test_db_open_errors.py (NEW), three tests, all `CliRunner` on temp paths: (a) `capture-source --db /tmp/opencode/batch2-<random>/nodir/x.db` → exit 1, exactly one stderr line, code `CAPTURE-017`, name `DbOpenFailed`, no `Traceback`; (b) same with a 29-byte text file as `--db` → `CAPTURE-017` again; (c) `backup <target> --db <text file>` → exit 1, one line, code `BACKUP-001`, no `Traceback`. Assert the planted detail carries only the file name, not the full temp path (Chunk 3).
2. Run `.venv/bin/pytest tests/test_db_open_errors.py`. Expect: (a) and (b) fail with a raw traceback (`open_database`, `ember/adapters/sqlite.py:103-107`, has no try/except); (c) passes the line-count part but the connection leak is not CLI-visible — the closure is reviewed in the diff.
3. Implement: in `ember/capture/errors.py` add `class DbOpenFailed(CaptureError)` with `code = "CAPTURE-017"`, `name = "DbOpenFailed"` (NEW code; the number is confirmed by decision I1, see the Code numbers line in the header). In `ember/adapters/sqlite.py` `open_database`: wrap `_connect` + `_apply_migrations` so any `sqlite3.Error` closes the connection and raises `DbOpenFailed("db open fail", db_path=os.path.basename(db_path))`. In `ember/adapters/backup.py` `_open_source` and in `ember/adapters/sqlite.py` `open_query_database` / `open_maintain_database_readonly`: close `conn` before the `SourceOpenFailed` / query `DbOpenFailed` / `MaintainDbOpenFailed` raises that today leak it (`backup.py:115-131`, `sqlite.py:254-258`, `sqlite.py:204-208`).

Proof it's real: remove the new try/except in `open_database` — tests (a) and (b) go back to raw tracebacks. Undo.
Done when: `.venv/bin/pytest tests/test_db_open_errors.py` prints 3 passed; by hand: `echo hello | env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/ember capture-source --db /tmp/opencode/batch2/nodir/x.db` prints exactly one `error: CAPTURE-017 DbOpenFailed | ...` line and `echo $?` prints `1`.
Commit message: `Batch 2: every open failure is a house error and closes its connection`

## Chunk 6 of 15: busy, recovery and missing split into three codes

Covers: story 14; report finding 4.7 #7 (QUERY-003 covers busy/recovery/missing alike).

1. Add three more tests to tests/test_db_open_errors.py (the NEW file from Chunk 5): (a) `current-state --db <missing path>` → code `QUERY-003` (unchanged, the "file missing" case); (b) hold a write lock (`sqlite3.connect(db).execute("BEGIN EXCLUSIVE")`) on a seeded temp db, run `current-state --db <that db>` → code `QUERY-008`, name `DbBusy`; (c) a 29-byte text file as `--db` → code `QUERY-009`, name `DbRecoveryNeeded`. All exit 1, exactly one stderr line.
2. Run `.venv/bin/pytest tests/test_db_open_errors.py -k "busy or recovery or missing"`. Expect: (a) passes (`open_query_database` already raises `QUERY-003` for missing, `ember/adapters/sqlite.py:252-253`), (b) and (c) fail — the codes do not exist yet.
3. Implement: in `ember/query/errors.py` add `class DbBusy(QueryError)` (`QUERY-008`) and `class DbRecoveryNeeded(QueryError)` (`QUERY-009`) (NEW codes; the spec pins 008/009 as the next free pair). In `ember/adapters/sqlite.py` `open_query_database` (`:252-258`): close the connection on the `sqlite3.Error` path (leak fix, 4.3 #11), then classify — message containing `locked` or `busy` → `DbBusy`; any other open/read failure on an existing file → `DbRecoveryNeeded`; missing file stays `QueryDbOpenFailed`.

Proof it's real: make the classifier raise `DbBusy` for everything — tests (a) and (c) fail. Undo.
Done when: `.venv/bin/pytest tests/test_db_open_errors.py` prints 6 passed.
Commit message: `Batch 2: split QUERY-003 — busy and needs-recovery get QUERY-008/009`

## Chunk 7 of 15: db-check reports a broken version as a finding

Covers: story 13; report findings 4.3 #6, 4.10 #15.

1. Add to tests/test_db_check.py (existing file, its conventions) a test `test_non_numeric_version_is_a_finding_not_a_crash`: build a temp db through the file's own helpers, then set `schema_version.version` to the text `abc` with a direct `sqlite3` UPDATE; run `db-check --db <path>` via `CliRunner`; assert exit code 1, no `Traceback`, the report has a version finding line, and `result:` is `DRIFT`.
2. Run `.venv/bin/pytest tests/test_db_check.py -k version`. Expect: 1 failed (`int()` raises `ValueError` in `_read_version`, `ember/adapters/db_check.py:109-113`, which is not a `sqlite3.Error`, so `check_database`'s except at `:101` misses it and the CLI at `ember/cli.py:1326` has no try).
3. In `ember/adapters/db_check.py`, catch the non-numeric version in `_read_version`'s caller: turn `ValueError` into a finding line (`version: cannot read - not a number`) and set the `DRIFT` verdict; the check still reports instead of crashing.

Proof it's real: re-raise the `ValueError` instead of converting it — the test fails with a traceback again. Undo.
Done when: `.venv/bin/pytest tests/test_db_check.py` prints all passed (previous tests green too).
Commit message: `Batch 2: db-check treats a non-numeric version as a finding`

## Chunk 8 of 15: export — damaged text reads as QUERY-005; one exit for every bad --out

Covers: stories 9, 15; report findings 4.10 #2, 4.10 #16.

1. Add to tests/test_export.py (existing file, its conventions) two tests: (a) seed a temp db, corrupt one stored text by writing a non-UTF-8 byte into the text column with a direct `sqlite3` UPDATE (the report §6 repro), run `export --db <path>` via `CliRunner` → exit 1, exactly one stderr line, code `QUERY-005`, no `Traceback` (today the `sqlite3` decode error escapes `except EmberError`, `ember/cli.py:1312-1314`); (b) `export --out <an existing directory>` → exit 1 with code `EXPORT-001` (today click refuses with a usage error, exit 2 — verified live in the check report).
2. Run `.venv/bin/pytest tests/test_export.py -k "damaged or directory"`. Expect: both failed.
3. Implement: in `ember/cli.py` `export`, change `--out` from `click.Path(dir_okay=False)` to a plain string so every bad `--out` reaches the engine's own `EXPORT-001`/`EXPORT-002` path and exits 1. In `ember/adapters/export.py`, wrap the `gather_export` reads so a `sqlite3.Error` (decode included) closes cleanly and raises `ItemsReadFailed` from `ember/query/errors.py` (the same code other reads use).

Proof it's real: in `export.py`, let the `sqlite3.Error` escape the new wrapper — test (a) fails with a traceback; change `--out` back to `click.Path` — test (b) fails with exit 2. Undo both.
Done when: `.venv/bin/pytest tests/test_export.py` prints all passed; by hand on a temp db: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/ember export --out /tmp/opencode/batch2` prints one `error: EXPORT-001 ...` line and `echo $?` prints `1`.
Commit message: `Batch 2: export maps damaged text to QUERY-005; one bad --out exit`

## Chunk 9 of 15: validate the AI base URL at the config point; read the reply payload through the mapped path

Covers: stories 10, 24; report findings 4.5 #4, 4.3 #24.

1. Add tests/test_ai_base_url.py (NEW) with two tests, plus one addition to tests/test_llm_adapter_unit.py (existing file): (a) CLI test — env `EMBER_AI_API_KEY=sk-fake` and `EMBER_AI_BASE_URL='::::nope'`, invoke `capture --file <tmp note> --db <tmp db>` → exit 1, exactly one stderr line, code `CAPTURE-019`, name `BaseUrlInvalid`, no traceback (today `httpx.InvalidURL` escapes, reproduced in the check report); (b) unit test — `build_link_proposer({...bad url...})` raises `ConfigMissing` (RELATE-035) and `build_close_proposer({...})` raises `CloseAiConfigMissing` (MAINTAIN-020); (c) in test_llm_adapter_unit.py — a fake client whose reply object has NO `choices` attribute produces `AiSchemaError` (CAPTURE-009), not `AttributeError`.
2. Run `.venv/bin/pytest tests/test_ai_base_url.py tests/test_llm_adapter_unit.py -k "base_url or choices or strange"`. Expect: (a) and (c) failed; (b) failed/passed as written — `ConfigMissing` is raised today only for a missing key (`ember/adapters/llm.py:154,217`), the bad URL is not validated at all.
3. Implement: in `ember/adapters/llm.py` add `validate_base_url(env, error_class)` (NEW function) called at the top of all three `build_*_proposer` functions — the capture one raises the NEW `BaseUrlInvalid` (`CAPTURE-019`, confirmed by decision I1, added to `ember/capture/errors.py`), the relate one raises `ConfigMissing` (RELATE-035), the maintain one raises `CloseAiConfigMissing` (MAINTAIN-020), each with detail naming `ai base url`. Make the reply-payload helpers `_content` and `_link_content` read `choices` with `getattr(response, "choices", None)` and raise the family's schema code (CAPTURE-009 / RELATE-033) when absent.

Proof it's real: delete the `validate_base_url` call in `build_item_proposer` — test (a) fails with the raw `httpx` traceback; give `_content` back the bare `response.choices` — test (c) fails with `AttributeError`. Undo both.
Done when: `.venv/bin/pytest tests/test_ai_base_url.py tests/test_llm_adapter_unit.py` prints all passed; by hand: `printf 'a note' > /tmp/opencode/batch2/note.txt && env EMBER_AI_API_KEY=sk-fake-fake-fake EMBER_AI_BASE_URL='::::nope' .venv/bin/ember capture --file /tmp/opencode/batch2/note.txt --db /tmp/opencode/batch2/c2.db` prints exactly one `error: CAPTURE-019 BaseUrlInvalid | ...` line, exits 1, and makes no network call (the URL fails validation before any request).
Commit message: `Batch 2: validate the AI base URL at config load; payload reads stay mapped`

## Chunk 10 of 15: an unpaired surrogate in an edit is refused before any write

Covers: story 11; report finding 4.5 #3.

1. Add to tests/test_cli_capture.py (existing file — it already fakes the AI via `monkeypatch.setattr("ember.cli.build_item_proposer", ...)` and drives `capture` with a fake `FakeItemProposer`, `tests/test_cli_capture.py:56-64`) a test `test_edit_with_unpaired_surrogate_is_refused`: run the confirm loop, answer the edit sub-prompt with text containing a lone surrogate (`"\ud800"`), assert exit code 1, exactly one stderr line, code `CAPTURE-018`, name `TextNotEncodable`, and the item is not written (today the `json.dumps`/`echo` path dies with `UnicodeEncodeError` — the path named at `ember/capture/confirm_write.py:132`).
2. Run `.venv/bin/pytest tests/test_cli_capture.py -k surrogate`. Expect: 1 failed.
3. Implement: in `ember/capture/confirm_write.py` `run_confirm_loop`, at the point an `e`-answered text is accepted, try `text.encode("utf-8")`; on `UnicodeEncodeError` raise the NEW `TextNotEncodable` (`CAPTURE-018`, confirmed by decision I1, added to `ember/capture/errors.py`) with the item/field named in the context. This one point covers both confirm surfaces (terminal and `--confirm json`, which feed the same loop).

Proof it's real: delete the encode check — the test fails with `UnicodeEncodeError` again. Undo.
Done when: `.venv/bin/pytest tests/test_cli_capture.py` prints all passed.
Commit message: `Batch 2: refuse an edit text that cannot be written as UTF-8 (CAPTURE-018)`

## Chunk 11 of 15: the app reads stderr whole and keeps the real cause

Covers: stories 17, 18; report finding 4.4 #3.

1. Extend app/test/fake-ember.js (existing file) with a `FAKE_MODE=traceback` mode: print two `Traceback (most recent call last):`-style lines then one `sqlite3.OperationalError: ...` line on stderr, exit 1, no house line.
2. Add failing tests (one action, two files): to app/test/bridge-client.test.js (existing) — `a traceback with no house line keeps the LAST non-empty stderr line in the APP-002 details` (today `app/main/bridge-client.js:265,276` keeps `stderrLines[0]`); to app/test/db-check-runner.test.js (existing) — `a house line on stderr after line 1 is still parsed` (today `app/main/db-check-runner.js:168` parses only the first line). Then run `npm test -- bridge-client` and `npm test -- db-check-runner` from `app/`. Expect: 2 failed.
3. Implement in `app/main/bridge-client.js`: the no-house-line fallback in `interpret()` takes the last non-empty line of `run.stderrLines`; in `app/main/db-check-runner.js` `interpret()`: scan every stderr line for the house pattern (same loop shape as `findHouseError`, `app/main/bridge-client.js:42-49`) and keep the last non-empty line in the APP-002 detail when nothing matches.

Proof it's real: change the fallback back to `run.stderrLines[0]` / `stderrLines[0]` — both tests fail naming `Traceback...` instead of the `sqlite3` line. Undo.
Done when: `npm test -- bridge-client` and `npm test -- db-check-runner` (from `app/`) each print all passed.
Commit message: `Batch 2: keep the real cause — read stderr whole, last line in Details`

## Chunk 12 of 15: the EMBER-000 sentence and the crash-folder module

Covers: stories 2 and 4 (the words and the folder); decisions D-16, N4, D-08 (the entry is written once here and carried into Batch 6's single table — Batch 6 must not drop it). N5's e2e comes in Chunk 13.

1. Add failing tests: to app/test/plain-sentences.test.js (existing) — `EMBER-000 has a full sentence entry and the EMBER family exists`; and create app/test/crash-file.test.js (NEW) — the folder helper honours `XDG_STATE_HOME`, falls back to `~/.local/state/ember/crashes`, and refuses a crash id containing `/` or `..`. Run `npm test -- plain-sentences` and `npm test -- crash-file` from `app/`. Expect: both failed (no `EMBER-000` entry in `app/shared/plain-sentences.mjs`, no folder helper exists).
2. Implement: in `app/shared/plain-sentences.mjs` add the full `EMBER-000` entry (an unexpected problem inside Ember; the report was saved; share the crash report) and add `EMBER` to `ERROR_FAMILIES`. Create app/main/crash-file.js (NEW): `crashDir()` and `crashPath(crashId)` with the same XDG rule as the engine (N4).
3. Run `npm test -- plain-sentences` and `npm test -- crash-file` again (the filter takes one argument — `app/test/run.js` reads only the first). Expect: both passed.

Proof it's real: set the `EMBER-000` entry's `next` field to `''` — the sentence test fails on a blank field. Undo.
Done when: `npm test -- plain-sentences` and `npm test -- crash-file` (from `app/`) print all passed.
Commit message: `Batch 2: the EMBER-000 sentence and the shared crash-folder rule`

## Chunk 13 of 15: crash channels registered in main

Covers: story 2 and 4 (the main-process half of Copy crash report / Show file); D-16.

1. Add app/test/crash-ipc.test.js (NEW): on injected fakes (the repo's T3 pattern, as in `app/test/shortcuts.test.js`) the handler returns the crash file's whole text and passes it to an injected `clipboard.writeText`; the folder handler calls an injected `shell.showItemInFolder` with the file path; a missing crash file answers with a plain APP-002-shaped refusal and no crash.
2. Run `npm test -- crash-ipc` from `app/`. Expect: 1 failed (no handlers exist).
3. Implement: in `app/main/ipc.js` register two channels (NEW names, keep the file's validate-once style): `ember:crashReport` (crash id → text → `clipboard.writeText`) and `ember:crashReportFolder` (crash id → `shell.showItemInFolder`); wire them through `app/preload/preload.js`'s allowlist and update the pinned channel list in app/test/preload-allowlist.test.js (existing — it pins the exact channel count).

Proof it's real: make `ember:crashReport` return `''` without reading the file — the test fails on the missing crash text. Undo.
Done when: `npm test` (from `app/`) prints all passed, including `crash-ipc`, `preload-allowlist` and `plain-sentences`.
Commit message: `Batch 2: main-process channels for Copy crash report and Show file`

## Chunk 14 of 15: the two crash buttons on the Add screen, e2e-tested

Covers: stories 2, 3; N5 (built and e2e-tested here on the Add screen; Batch 3 does not re-test them).

1. Extend app/test/fake-ember.js with a `FAKE_MODE=crash` mode: write a crash file named by `FAKE_CRASH_ID` into `$XDG_STATE_HOME/ember/crashes/`, print a traceback then `error: EMBER-000 InternalError | fake-ember | crash=<id>`, exit 1. Extend app/test/e2e/helpers/shell.js (existing) to pass `XDG_STATE_HOME` into the scenario env beside `XDG_CONFIG_HOME` (`shell.js:40`).
2. Add the e2e scenario to app/test/e2e/add.js (existing file): on the Add screen a fake `EMBER-000` session death shows the crash sentence from Chunk 12 plus the two buttons "Copy crash report" and "Show file" under Details; clicking Copy shows the "Copied." feedback; the crash text shown matches the fake crash file. Run `xvfb-run -a npm run e2e -- add` from `app/`. Expect: the new scenario fails (no buttons yet). Note the honest split: the REAL clipboard write is pinned by the injected-fake unit test in Chunk 13; the e2e asserts the visible feedback only.
3. Implement in `app/renderer/screens/add.mjs` and `app/renderer/components/state-block.mjs`: when the error info's code is `EMBER-000`, the Details area gets the two buttons wired to the two new channels (escaping still applied to all shown text, as `state-block.mjs` already does). Run the e2e again.

Proof it's real: rename one button's label after the e2e passes — the scenario fails on the missing label. Undo.
Done when: `xvfb-run -a npm run e2e -- add` (from `app/`) prints all scenarios passed, including the new crash one, and `npm test` stays green (the preload allowlist pin from Chunk 13 included).
Commit message: `Batch 2: Copy crash report and Show file on the Add screen (EMBER-000)`

## Chunk 15 of 15: the release rebuild and the full check

Covers: story 25; decision D-01 ("rebuild the .deb and run the Batch 1 check script. Must pass"). Also the bookkeeping rule from PROJECT_MAP.md.

1. Run everything green, in this order, from the repo root: `.venv/bin/pytest`; from `app/`: `npm test`; from `app/`: `xvfb-run -a npm run e2e -- add`. All must pass. Fix nothing silently — a red result goes back to the chunk that owns it.
2. From `app/`, run `npm run package` to rebuild the `.deb`, then run the Batch 1 check script on the built `.deb` exactly as `docs/Spec-Batch1.md` pins it (runnable alone on any `.deb`). It must pass. Requires Batch 1 merged first (see header and Unknowns).
3. Update PROJECT_MAP.md: one line each for the new files (`ember/crash_report.py`, `ember/crash_report` test, `ember/capture/errors.py`'s three new codes, `app/main/crash-file.js`, the two NEW app test files) and the changed exit behaviour. Commit.

Proof it's real: nothing to toggle off and on here — Step 1 is the proof: the whole Python suite, the app tests and the e2e ran green inside this chunk, and the Batch 1 check script only passes against the `.deb` this chunk rebuilt.
Done when (deletes/overwrites are not part of this chunk, but the build overwrites the gitignored release folder — checked here): `npm run package` ends 0, the check script ends 0, and the dated report lands beside the `.deb` in the gitignored folder (D-12).
Commit message: `Batch 2: rebuild the .deb, run the Batch 1 check, update the project map`

## Final check

- The full commands, all green: `.venv/bin/pytest`; `cd app && npm test`; `cd app && xvfb-run -a npm run e2e -- add`.
- The batch's "Done when" from archive/Plan.md Batch 2 ("the five crash paths in report section 6 … each produce exactly one stderr line with a house code, a non-zero exit, and, for EMBER-000, a crash file with no secrets"), each with its proof:
  1. Bad `--db`: `echo hello | env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/ember capture-source --db /tmp/opencode/batch2/nodir/x.db` → exactly one stderr line `error: CAPTURE-017 DbOpenFailed | …`, `echo $?` prints `1`. (pytest twin: tests/test_db_open_errors.py.)
  2. Non-SQLite file: `printf 'not a database' > /tmp/opencode/batch2/notadb.db` then the same command with `--db /tmp/opencode/batch2/notadb.db` → one `error: CAPTURE-017 …` line, exit 1.
  3. Damaged text in the database: seed a temp db with the file's helpers, corrupt one text column byte with a direct `sqlite3` UPDATE (the Chunk 8 test does exactly this), then `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/ember export --db <file>` → one `error: QUERY-005 ItemsReadFailed | …` line, exit 1. (pytest twin in tests/test_export.py.)
  4. Bad base URL: the manual command in Chunk 9's Done when → one `error: CAPTURE-019 BaseUrlInvalid | …` line, exit 1, no network call.
  5. Unpaired surrogate: pytest only (tests/test_cli_capture.py, Chunk 10) — reaching the confirm loop needs the faked AI proposer, so no manual AI-free command exists.
  - `EMBER-000` + crash file with no secrets: the forced-crash pytest in Chunk 2 (monkeypatched helper, CLI invoked in-process — the spec's forcing mechanism, no test hook in the product); by hand, the Chunk 2 Done-when command shows the line and the crash file under `/tmp/opencode/batch2/state/ember/crashes/`.
- Release (decision A / D-01, story 25): `npm run package` + the Batch 1 check script pass (Chunk 15).

## Unknowns

- **Branch and merge state.** archive/Plan.md names no branch names and does not state whether Batch 1 has landed or merged. Today (2026-11-01) the working branch is `ember-interface` and the Batch 1 `.deb` check script does not exist in the repo yet (`scripts/` holds only `ember-key-wizard.sh` and `measure_model_change.py`; `app/scripts/` holds only `pack.js` and `build-ember-runtime.sh`). Batch 1 must land before Chunk 15; the check script's exact path/name comes from Batch 1's landing.
- **The crash file's "engine version" line.** Today the only version string is `ember/__init__.py` (`0.1.0`). Batch 1 creates the one version source (check report §4); Chunk 2's crash writer should read that source instead once Batch 1 lands, not the stopgap. The exact accessor is batch-1-shaped and unconfirmed.
- **Scope of the busy/recovery split.** The spec splits the QUERY opener only (story 14). The relate and maintain openers keep their single codes (`RELATE-012`, `MAINTAIN-007`) even when the real cause is busy or a damaged file; widening the split to them is not part of this batch.
- **`ember:crashReport` / `ember:crashReportFolder` channel names.** The two IPC channels, the crash id shape (`<UTC timestamp>-<6 hex>`) and the crash file name (`<id>.txt`) are this plan's choices (marked NEW); nothing in the repo pins them today.

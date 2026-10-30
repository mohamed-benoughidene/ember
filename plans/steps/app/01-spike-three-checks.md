# L3 App Step 1: the spike (three checks plus Python packaging)

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §2, §8. Phase: gate. **No product code is written in this step.** The spike is throwaway; only a decision record is kept.

## Constitution rules this step enforces
P1 (no architecture before the evidence), S1 (every check is a runnable command with an expected result), D7 (nothing touches the founder's real knowledge base: spike uses a copy).

## Deferred settings resolved by this step
- Python bundling method (L2 §9).
- Electron versus Tauri (spec decision 5).

## 1. The checks (each: what to run, what proves it)
1. **Runs Ember's Python.** On Linux (Debian, the founder): a throwaway Electron window starts `ember list-items --format json`-equivalent (any read command on a copy of a real knowledge base) as a child process and shows the result. Proof: the data appears; exit code 0.
2. **Python for a non-coder.** Candidate methods to test, in order: (a) freeze `ember` into one executable per OS; (b) ship an embedded Python plus the installed package; (c) require system Python (rejected for non-coders unless (a) and (b) fail, state why). Proof per method: a clean machine/container with no Python runs the command. Measure the folder size with `relate`'s embedder included and excluded; report both numbers.
3. **Popup shortcut on Windows and macOS.** A throwaway app registers the default shortcut (spec §10). Proof: an automated CI job on `windows-latest` and `macos-latest` launches it and reports registration success/failure. (Launch check only; a person with those machines confirms later, spec decision 9.) On Linux the founder runs `echo $XDG_SESSION_TYPE` and the spike reports whether registration works there; if not, the tray fallback is shown working.
4. **Install size.** Report the installer size per OS for the best bundling method. The founder decides if it is acceptable (spec §11: "acceptable to the founder").

## 2. Tests
None as code. The deliverable is `Build Notes` appended here: the commands run, the real numbers (MB), pass/fail per check per OS, and a recommendation.

## 3. Check command (S1)
The spike repository folder is outside the product tree (scratchpad or a branch not merged). Its README lists the exact commands. Nothing is added to `app/`.

## 4. Error codes raised
None.

## 5. Rollback
Delete the throwaway folder. No repo change except Build Notes in this file.

## 6. Done when / gate
All four checks have real numbers. The maintainer answers: **A:** Electron confirmed, go to step 02. **B:** a check failed or size is too large, switch to Tauri and rewrite `plans/interface-app-plan.md` §4 to §9 before any further step. If the size answer is "too large only because of `relate`'s embedder", a third option is allowed: record it as an A/B for the maintainer (for example Link items needing a separate optional download).

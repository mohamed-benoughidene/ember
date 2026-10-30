# L3 App Step 1: the spike (risk check, throwaway)

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §2, §3 decisions 1, 2, 3, 4. Phase: gate. **No product code is written in this step.** The spike is throwaway and lives on a side branch that is never merged; only a decision record is kept.
**RISK step (AGENTS.md §2):** it installs Electron, a Python freezer and a packager (package adds, exact names and versions shown and confirmed before `npm install` / `pip install`), and adds ONE throwaway CI workflow file on the side branch (a workflow edit; it runs on `windows-latest` and `macos-latest`). Nothing in `main` or `ember-interface` changes except Build Notes in this file.
**When:** decision 1 in the app L2. Recommended: BEFORE the Undo build starts. It needs neither Undo nor the Bridge.

## Constitution rules this step enforces
P1 (no architecture before the evidence), S1 (each check is a runnable command with an expected result), D7 (nothing touches the founder's real knowledge base: the spike uses a copy).

## Deferred settings resolved by this step (L2 §9)
- Python bundling method.
- Electron versus Tauri.
- Key storage backend on the founder's machine (decision 4).
- Base size versus size with the embedder (decision 3).

## 1. The questions (cite L2 §2; each has a command and an expected result)
1. **Can a frozen `ember` run on a machine with no Python?** On a clean Debian container: `./ember current-state --db copy.db` prints the JSON document, exit 0. Try (a) one frozen executable per OS, (b) an embedded Python plus the installed package. (c) "require system Python" is rejected for non-coders unless (a) and (b) both fail; say why. Record the folder size in MB WITHOUT and WITH `sentence-transformers`.
2. **Does a hello-world Electron window launch on Windows and macOS?** One throwaway workflow on the side branch runs on `windows-latest` and `macos-latest`: `npm run spike:launch` prints `launch: ok` and exits 0. Also record the installer size per OS.
3. **Shortcut and tray on the founder's Debian.** The founder runs `echo $XDG_SESSION_TYPE` and `echo $XDG_CURRENT_DESKTOP`. `npm run spike:shortcut` prints `registered: true|false`; `npm run spike:tray` prints whether a tray icon is visible (founder confirms by eye). If registration fails, the menu route (L2 §5.5) must be shown working.
4. **Key storage backend.** `npm run spike:keystore` prints the selected `safeStorage` backend and whether encryption is available (API checked in the docs for the pinned Electron version first).

## 2. Tests
None as product code. The deliverable is **Build Notes** appended here: the exact commands run, real numbers (MB, pass/fail per check per OS), and a recommendation.

## 3. Check commands (S1)
The five `npm run spike:*` commands above, run in the throwaway folder (listed in its README). Each prints the stated line. Nothing is added to `app/`.

## 4. Error codes raised
None.

## 5. Rollback
Delete the throwaway folder and the side branch (`git push origin --delete <branch>` after the founder agrees). The only repo change is this file's Build Notes.

## 6. Done when / gate
All checks have real numbers. The founder answers: **A:** Electron confirmed, continue. **B:** a check failed or the size is too large -> switch to Tauri and rewrite `plans/interface-app-plan.md` §4 to §9 before any further app step. If the size is too large only because of the embedder, record the A/B of decision 3.

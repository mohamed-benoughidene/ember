# Interface spike: findings (three checks + key storage)

Status: FINAL numbers below, measured on the founder's machine, 2026-10-30.
Parent: `plans/steps/app/01-spike-three-checks.md` (the spec), `plans/interface-app-plan.md` §3
decisions 2, 3, 4, `docs/ember-interface-spec.md` §11.
Where probed: throwaway dirs in `/tmp/opencode/` (`spike-app`, `spike-venv`,
`spike-venv2`, `spike-pi`, `spike-probe`) on the same Debian machine. Nothing in
`ember/` or any tracked file was changed by the probes.

## Machine and environment (facts read live)

| Fact | Value | How read |
|---|---|---|
| Session type | Wayland | `echo $XDG_SESSION_TYPE` |
| Desktop | KDE (Plasma) | `echo $XDG_CURRENT_DESKTOP`; `loginctl` shows `Type=wayland`, `Desktop=KDE` |
| XWayland display | `DISPLAY=:1` present | environment |
| Python | 3.13.5 (system and project venv) | `python3 --version` |
| Node / npm | v24.22.1 / 11.19.1 (nvm, no system install needed) | `node --version` |
| Docker (clean-container test) | NOT available | `docker` command missing |

## Check 1 — can the app run Ember's Python? GO

**1a. Spawning with a venv Python, reading structured stdout — PASS.**
A Node `child_process` script (same API Electron's main process uses) ran the
project venv's Python from any working directory, using `python -m ember`:

| Command run | exit | stdout | JSON valid | stderr |
|---|---|---|---|---|
| `python -m ember --help` | 0 | 1479 B text | n/a | empty |
| `python -m ember current-state --db <copy.db>` | 0 | 237 B | **yes** (`mode`,`count`,`items`) | empty |
| `python -m ember current-state --db <missing>` | 1 | 0 B | no | `error: QUERY-003 DbOpenFailed \| ... \| db file missing` (one parseable line) |

The database was a throwaway copy seeded in `/tmp/opencode/spike-probe/copy.db`
(two items, one supersedes link); the real knowledge base was never touched.
Startup of each child: ~0.95–1.0 s (venv Python + imports) — acceptable for a
desktop shell that runs one command per user action.

**Bridge trap found (record, do not forget at step 02):** `python -m ember.cli
--help` exits **0 with empty stdout and empty stderr** — `ember/cli.py` has no
`if __name__ == "__main__": main()` block (the entry point is `ember/__main__.py`
and the installed `ember` script). A bridge that spawns `-m ember.cli` would read
silence and could mistake it for success.

**1b. Frozen executable (PyInstaller) — PASS (mechanism and size).**
PyInstaller 6.22.3 (own venv), onefile build of the REAL Ember CLI with base
dependencies (click, openai, pydantic; `sentence-transformers` excluded):

- Frozen binary: `ember-real`, **20 MB**, built in ~32 s.
- `./ember-real current-state --db /tmp/opencode/spike-probe/copy.db` prints the
  same JSON document, exit 0 — **with no venv and no project source on the path**.
- Cold-start time (onefile self-extract included): 1.43–1.89 s over 3 runs.
- A hello-world stub frozen the same way is 8 MB and starts in 0.18 s (scale
  reference only).

**NOT VERIFIED: "a machine with no Python".** Docker is not available on this
machine, so the clean-container test (`01` §1, option (a) on a pristine Debian)
was not run. The frozen binary carries its own `libpython` (PyInstaller onefile),
and it ran correctly from `/tmp` with no Ember venv in scope, but a truly
Python-less system was not simulated. One manual check for the founder (5 min):
copy `ember-real` to a fresh Debian live-USB / VM without Python and run it.
The step file's option (c) ("require system Python") stays rejected either way:
a non-coder cannot install Python 3.12+ (`01` §1).

**1c. Embedded Python + installed package — PASS (mechanism), sizes below.**
A plain venv built from the system Python and `pip install ember` (base deps)
ran `current-state` correctly from `/tmp` with no repo source on the path.

## Check 2 — Electron launches (Windows/macOS CI) — NOT RUN (needs GitHub CI)

Electron 45.1.0 ran on THIS Debian desktop (see check 3), which is the system the
founder owns. The Windows/macOS launch check needs the one throwaway CI workflow
on `windows-latest`/`macos-latest` (`01` §1 question 2). This agent did not add
the workflow file (instructions: only the findings file may be committed), so:
**NOT VERIFIED: Windows/macOS launch; needs the step-02 CI workflow.** Per plan
§3 decision 2-A (recommended), Windows/macOS only ever get this launch check, no
public installer, so this does not gate the Debian decision.

## Check 3 — global shortcut + tray on the founder's Debian (Wayland/KDE) — GO

Electron probe app (Electron `45.1.0` exact-pinned; Chromium 156.0.8078.49;
Node 24.22.1 inside Electron), run on the real desktop, both platform routes:

| Route | Shortcut registered | Tray created | errors on stderr |
|---|---|---|---|
| default (X11/XWayland) | **true** (`CommandOrControl+Shift+E` and spec §10 default `CommandOrControl+Alt+E`) | **true** | warnings only, no failure |
| native Wayland (`ELECTRON_OZONE_PLATFORM_HINT=wayland`) | **true** | **true** | warnings only, no failure |

- The tray item registered with KDE's StatusNotifierWatcher on the live session
  bus: `qdbus6 org.kde.StatusNotifierWatcher /StatusNotifierWatcher ...RegisteredStatusNotifierItems`
  listed a new `:1.<id>/StatusNotifierItem` entry next to the existing `blueman`
  entry while the probe ran. This is objective evidence Plasma saw the icon;
  the founder should still confirm by eye on the next run (one command in
  "founder checks by hand" below).
- The Electron `globalShortcut` route reports success on Wayland through
  XWayland (X11 grab) — the spec §11 worry is **not confirmed** for KDE, but:
- **NOT VERIFIED: firing, not registering.** No key-synthesis tool exists on
  this machine (no `xdotool`/`ydotool`/`kdotool`), so nobody pressed the key
  during the probe. Registration success on Wayland does not guarantee the
  callback fires for a real global keypress on every Wayland compositor.
  Founder check (1 min): run the probe, press Ctrl+Alt+E anywhere, watch for
  `shortcutFired`.
- Fallback routes are implementable REGARDLESS of the shortcut result, all
  verified in the same probe run: application menu item (`File -> Add text`,
  built and set: true); tray menu with Quick add/Open/Quit (created: true);
  and a `--quick-add` command-line flag reaches the main process as
  `process.argv` (verified mechanism: custom flags pass through unmodified).

## Check 4 — key storage backend (safeStorage) — GO for decision 4-A

Electron `45.1.0` on this machine (both XWayland and native-Wayland runs):

- `safeStorage.getSelectedStorageBackend()` → **`kwallet6`** (KDE Wallet 6 —
  a real OS keyring, NOT the weak `basic_text` fallback).
- `safeStorage.isEncryptionAvailable()` → **true** (deprecated in 45, but the
  sync API is what the pinned docs describe; replacement async API exists).
- Round trip `encryptString` -> `decryptString` with a test secret → **ok**.

This means plan §3 decision 4-**A** (OS secure storage through safeStorage,
refuse + "session only" if weak/missing) is viable on the founder's machine as
is. The weak-backend refusal path must still be coded because a non-KDE
machine or headless session can select `basic_text` (Electron docs; not
observed here).

## Install size (decision 3 numbers), measured with `du -sm`

All numbers MB, this machine, Debian x86-64, Python 3.13:

| Component | Size (MB) | Notes |
|---|---|---|
| Electron runtime (`node_modules/electron/dist`) | **274** | Electron 45.1.0, Linux x64; the `electron` binary alone is 234 MB |
| Electron package + deps around it | +14 | `node_modules` total 288 |
| Python venv: ember + base deps (click, openai, pydantic) | **56** | runs `current-state` standalone |
| Python venv: + `sentence-transformers` + torch **CPU** wheel | **1413** (delta over base: **+1357**) | torch 2.15.0+cpu alone 805 MB, transformers 116 MB, sentence-transformers 6 MB; import verified. Installed with `--index-url https://download.pytorch.org/whl/cpu` to match the founder's real setup (their torch is 2.15.0+cpu, 809 MB). Plain PyPI instead pulls a **multi-GB CUDA wheel set** (nvidia_* packages; download observed at >400 MB before being stopped) — do NOT use plain PyPI for bundling. |
| Frozen real Ember CLI (PyInstaller onefile, base deps) | **20** | single file, no Python needed (mechanism verified) |
| Founder's existing full venv (has sentence-transformers 6.2.0) | **1433** | reference point (matches the 1413 spike measurement; the ~20 MB difference is dev/test packages) |
| Model weights downloaded on first `relate` use | NOT MEASURED | first-run download per spec story 45; not downloaded during the spike (story 107 exception applies to it; size not a spike question) |

So: base install (Electron 274 + frozen Python path 20, or venv path 56) is
roughly **~294–330 MB before the embedder**. Adding the embedder adds a
measured **+1357 MB** (1413 total for the venv with torch CPU) — so option B
(bundle the embedder in every install) lands near **1.7 GB** installed, roughly
5x the base. With decision 3-A (optional download on first Link-items use),
every install stays at base size and only users of Link items download ~1.3 GB
plus the model weights (weights size NOT MEASURED).

## Answers for the maintainer (plan §3)

- **Decision 2 (platform scope):** A is supported by evidence — Debian/Wayland
  works today (check 3 PASS on the founder's own session); Windows/macOS would
  only get CI launch checks, which are still unrun (check 2 NOT VERIFIED).
- **Decision 3 (embedder bundling):** both sizes recorded — base ~294–330 MB
  vs with-embedder ~1.7 GB installed (+1357 MB measured). A (optional download)
  keeps every install small; B is feasible but ~5x. Models download on
  first use either way unless weights are bundled (not measured).
- **Decision 4 (key storage):** backend on this machine is `kwallet6`, a real
  keyring — Go with A (safeStorage, refuse/session-only on weak backend).

## Recommendation (01 §6)

**A — Electron confirmed, continue.** All three founder-relevant checks pass
with real numbers: Python spawn + JSON (both venv and frozen), shortcut and
tray registered on the actual Wayland/KDE session, safeStorage on kwallet6,
and a base install measured near 300 MB. No reason to switch to Tauri.

## NOT VERIFIED (summary, honesty rule)

1. Frozen binary on a truly Python-less machine (no Docker; needs one manual
   live-USB/VM check, or accept venv-bundle path which only needs system
   Python at build time... NOT VERIFIED either — it also needs libc only, but
   the claim was not tested).
2. Shortcut FIRES on a real keypress (registration verified only).
3. Tray icon visible to the founder's eye (watcher registration verified).
4. Windows/macOS Electron launch (needs the step-02 CI workflow).
5. Model weights size on first `relate` run (not downloaded).

## Founder checks by hand (10 minutes total)

1. Re-run the probe from `/tmp/opencode/spike-app`: `npx electron .` inside it,
   press **Ctrl+Alt+E** anywhere → expect `shortcutFired` in the output.
2. With the probe still running, look at the Plasma system tray (bottom-right
   arrow if hidden) → expect a small blue dot icon named "Ember spike".
3. (Optional, closes NOT-VERIFIED 1): copy
   `/tmp/opencode/spike-pi/dist-real/ember-real` to any machine without Python
   and run `./ember-real current-state --db <some ember .db>` → expect JSON.

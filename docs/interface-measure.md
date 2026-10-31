# Interface measure (app step 13): before/after per job, and the real install sizes

Status: step 13 deliverable (spec stories 109 and 110, plan §3 decision 3-B). Measured on the
founder's machine (Debian x86-64, Wayland/KDE, Python 3.13, Electron 45.1.0), 2026-10-31.
Sources of every number: counted from `docs/commands.md` (the code-verified command inventory),
from the built screens (each flow is e2e-pinned), and from the packaging build this step made.
Nothing here is estimated from memory.

## 1. What the terminal asks of you that the interface does not

Shared set-up, terminal side (in front of EVERY job, before one command runs):

1. Create and activate a Python virtual environment (`python3 -m venv .venv`, `source .venv/bin/activate`).
2. Install the package (`pip install -e .`; for Link items also the extra: `pip install -e ".[relate]"`, ~1.4 GB).
3. Get an AI key through `scripts/ember-key-wizard.sh`, then in EVERY new shell: `set -a; source .env; set +a`.
4. Pass `--db PATH` on every command (or always work in the folder of your knowledge base file).
5. Read raw JSON documents (or an interactive prompt flow) and know which exit code meant what.

Shared set-up, interface side: the first-run wizard once (choose the knowledge-base file, paste
the key with an instant shape check, add your first text). No flags exist anywhere in the app;
the knowledge base is chosen once and remembered.

## 2. Per job (spec §13 table, completed from the real commands)

| Job | Terminal needs (counted from `docs/commands.md`) | Interface needs (the built screens) |
|---|---|---|
| Add | 2 commands (`capture`, `capture-source`); `--file` + `--db` every call; the key loaded via 2 setup lines per shell, env var name `EMBER_AI_API_KEY`; 4 confirm keys (`y`/`n`/`e`/`q`) with `e` re-asking type/statement/metadata; remember the 4 type names | Paste text → press button → press Confirm (Return), or Edit/Reject buttons (same keys on the keyboard, kept on purpose → parity is not lost, typing flags is). "Before sending" notice shown for you. |
| Look up | 5 commands (`current-state`, `list-items`, `topic-search`, `show-item`, `history`); 8 distinct flags (`--query`, `--status`, `--type`, `--limit`, `--offset`, `--item`, `--since` with a UTC offset, `--db`) — 18 flag positions across the 5 commands + `--db` ×5; parse JSON yourself | Type in one search box; 3 dropdown filters; click a row for the provenance view; the Ledger tab puts paging and the plain event words (Undone/Redone) behind a page control. 0 flags. |
| Link items | `pip install -e ".[relate]"` (~1.4 GB, and you must pick the CPU torch index `--index-url https://download.pytorch.org/whl/cpu` yourself — plain PyPI pulls multi-GB CUDA wheels, the spike's hard note); first `relate` downloads the model weights (~440 MB this machine); `relate --item N\|--latest --db`; 4 confirm keys (`y`/`n`/`s`/`q`); model-change wipes the embedding cache and you live with the rebuild | Click Link items, click the row (or pick newest), confirm (Return `y`, `n`, `s`, Esc all work). The bundle (decision 3-B) carries CPU torch AND the weights — no install, no download, no index choice. |
| Fix and close | 7 commands (`close-item`, `set-status`, `edit-item`, `remove-link`, `reverse-supersedes`, `undo`, `redo`); 8 distinct flags (`--item`, `--link`, `--reason`, `--field`, `--value`, `--to`, `--dry-run`, `--db`); only 2 human close reasons (`invalidated`/`expired` — machine reasons are refused); `rationale` edits only a Decision, `source` only a Finding, `statement` is forbidden; `--dry-run` discipline to preview safely | Pick the item from a list; press one action button (off-limits buttons say why); every destructive move shows its preview + Cancel BEFORE writing; Undo/Redo buttons labelled for you ("Undo Close item 3") from a dry-run the app runs itself. |
| Clean up | `maintain --dry-run --db` first, then `maintain --db`; 3 confirm keys (`y`/`n`/`q`) on up to 10 AI close questions; know yourself that the sweep needs no key but Phase 5 does | One pane: Preview (with per-item why, before→after heat marks), then Apply, then answer each question in one block (same keys), Stop always available. The not-undoable caution is shown for you (the drawer never forgets it — you must). |
| Keep safe | 3 commands (`backup TARGET_PATH`, `export [--out PATH]`, `db-check`) + `--db`; 3 flag positions; you must know the `.old-1..3` rotation rule, that export cannot be restored, and the never-target-the-database-itself refusal codes | Three buttons on one pane + a native save dialog; the health check runs itself when the pane opens; every failure line says "your knowledge base file is unchanged" and offers Retry. |

**The promise (spec decision 6), counted:** the terminal asks a memory of 17 commands' worth of
names/flags/vocabularies plus 5 standing set-up steps, re-typed per call; the interface asks one
first-run wizard (once), one file choice per job, and one click-or-Return per action. Flags to
remember in the interface: **0**. Setup steps at first use: 3 (the wizard's own screens).

## 3. Install sizes (decision 3-B: the embedder is IN every install)

Measured with `du -sm` during packaging (`npm --prefix app run package` also prints these):

| Component | Size (MB) |
|---|---|
| Electron runtime (Linux x64, electron 45.1.0) | 274 |
| App code + fonts + licences | <1 (du rounds to 0) |
| Bundled ember runtime (PyInstaller ONEDIR, CPU torch + sentence-transformers inside) | 1505 |
| — of which model weights (`BAAI/bge-base-en-v1.5`, safetensors + configs, deduplicated) | 419 |
| **Installed total** | **1779** (du; the control field says 1,821,696 KiB) |
| **The Debian package (.deb, xz-compressed)** | **515** (539,317,392 bytes) |

Paths, all real: staged tree `/…/pkg/ember-app` (installed 1779 MB), the .deb
`/…/pkg/ember-app_0.2.0-1_amd64.deb`, runtime source `app/dist/ember-runtime`
(built to `EMBER_RUNTIME_OUT`). The full report prints from `npm --prefix app run package`
(and survives in `<pack-root>/sizes.txt`).

The first build (before the duplicate-format trim) measured runtime 2338 MB / installed
2612 MB / .deb 893 MB — kept here so the trim's effect is honest, not folklore.

Speed: the frozen `current-state` answers in **1.12 s** (one child, venv comparison 0.95–1.0 s
from the spike) — ONEDIR pays none of ONEFILE's re-extraction cost, which is why the layout is
a folder, not the spike's 20 MB single file (the spike's number was the BASE build, embedder
excluded; it cannot be compared to a bundle that carries torch).

Decision context: decision 3-B lands exactly where the spike predicted (~1.7 GB with the
embedder, ~5x the ~300 MB base). The maintainer accepted this on 2026-10-30. The CPU torch
index is mandatory; the bundle build REFUSES a CUDA torch (checked at build time).

### Weights decision (the detail that was left to this step)

The weights (`BAAI/bge-base-en-v1.5`, the engine's own default, `EMBER_EMBEDDER_MODEL`) are
BUNDLED inside the runtime at `<app>/ember-runtime/models/hub` (a Hugging Face hub cache), and
the app points every child at them OFFLINE (`HF_HOME=<bundle>/models`, `HF_HUB_OFFLINE=1`,
`TRANSFORMERS_OFFLINE=1`, set only when a bundle is present). Consequence: the story-45
first-run download never happens; story 107 (no network except the AI service you chose) holds
with NO founder exception and no first-run waiting. Cost: the sizes above. This reading matches
the maintainer's sentence at the app gate: "no story-107 exception is needed if the weights ride
in the bundle".

### Bundle layout (the decision this step owned)

- `<app>/ember-runtime/` — PyInstaller ONEDIR of the real CLI (`bin` behaviour via one folder:
  onefile would re-extract ~1.5 GB on every command start; the spike's 20 MB number was the BASE
  build without the embedder).
- `<app>/bundle.json` — written by the packer; its presence makes the runtime REQUIRED, so a
  damaged install raises APP-007 at boot with the plain message (unit-tested by deleting the
  runtime), while a dev tree without the manifest keeps `ember` on PATH.
- The app's resolution order (`app/main/ember-command.js`): `EMBER_APP_COMMAND` env override
  (dev/tests, unchanged) → bundled runtime (required with manifest, opportunistic without) →
  `ember` on PATH.

## 4. CI and platforms (story 109; decision 2-A)

- `.github/workflows/test.yml` gains ONE matrix job `app-launch-check` (ubuntu-latest,
  windows-latest, macos-latest): creates the venv, installs Ember, `npm ci --prefix app`, runs
  the app's own import check (T9) on Linux, prints the Electron runtime size per OS, and runs
  `npm run check:launch` (open a throwaway knowledge base, one read command, `items: N`,
  exit 0). The pytest job is untouched. Windows/macOS are LAUNCH-CHECKED only — no installer
  exists for them (deferred GitHub issue #38 tracks installer work).
- `check:launch` is now cross-platform (Electron binary via `require('electron')`; Windows uses
  `python -m ember`; POSIX behaviour unchanged and re-run green on the founder's machine).
- CI RUNS: not yet run (needs a push; this lane never pushes) — NOT VERIFIED honestly.

## 5. Version in one place

The version is the `version` field of `app/package.json` ONLY (x.y.z, pinned by
`app/test/packaging.test.js`: no hardcoded copy anywhere in `app/main/`, About must read it
through `app.getVersion()`). The About box shows "Ember <version>" with the font/licence
credits (step 12), so an installed user can always name the exact build. This release's number:
0.2.0 (unchanged from step 02's freeze; bumping is the maintainer's release decision, not a
build step's).

## 6. Honesty ledger

- Windows and macOS: launch check ONLY (decision 2). Nobody has run the app on those systems
  beyond what CI will show; until a person with those machines checks, release notes must say
  "Windows and macOS are launch-checked only".
- The .deb is UNSIGNED (no signing key on this machine) and was built, not installed — the
  `dpkg -i` behaviour on the founder's machine is a 1-minute check listed in the build notes.
- CI workflow: syntax-validated locally; real runners not observed from this lane (never
  pushes).
- The first candidate for the zero-outside-request test (a main-process webRequest audit seam)
  was REVERTED: it crashed Electron 45.1.0's network service on this desktop. The shipped test
  observes requests passively through Playwright; the guarantee tested is the same.

Addendum, checks run against the REAL shipped artifacts (2026-10-31):

- The STAGED TREE (an `dpkg -x` equivalent of the install) passed the app's own launch check
  USING ITS BUNDLED RUNTIME: window up, `items: 0`, exit 0, `EMBER_APP_COMMAND` unset — the
  bundle.json manifest drove the resolution, so this exercised the packaged layout
  (electron + app + ember-runtime + manifest) exactly as an installed user's first minute.
- The frozen runtime's embedder works offline from the bundle: `ember relate --latest` on a
  real temp knowledge base, `env -i` clean environment + `HF_HOME=<bundle>/models` +
  `HF_HUB_OFFLINE=1`, reached `RELATE-035` (the AI-key question at Phase 3) — meaning Phase 2
  loaded torch + sentence-transformers + the shipped weights with zero network. Startup of the
  frozen `current-state`: 1.12 s.

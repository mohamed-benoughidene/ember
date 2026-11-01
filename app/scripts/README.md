# Packaging scripts (`app/scripts/`)

How this repo turns source code into the installable `.deb` package, and the
safety rules every script here enforces. Written for a developer who has
never seen this pipeline.

## The pipeline in one line

    app/scripts/build-ember-runtime.sh  ->  app/scripts/pack.js  ->  app/dist/release/*.deb

1. `build-ember-runtime.sh` freezes the Python engine into a standalone
   program and copies the AI model weights into it. The result is the
   "ember runtime" folder with a `.gate-ok` marker file proving it passed
   the gate.
2. `pack.js` stages the Electron app with that runtime inside and builds
   the `.deb` with the system `dpkg-deb`.
3. After building, `pack.js` runs `check-deb.sh` on the fresh `.deb`.
   Only a passing package is saved (with a dated report) into
   `app/dist/release/`. A failing check fails the whole pack and saves
   nothing but the report.

## The files

- `build-ember-runtime.sh`: the runtime builder. Uses PyInstaller (ONEDIR)
  to freeze the real `ember` CLI with the relate embedder (torch) plus the
  `BAAI/bge-base-en-v1.5` weights into `<out>/ember` + `models/hub`. Needs
  no Python on the target machine afterwards. Internally it runs
  `gate-ember-runtime.sh` (next file) BEFORE it replaces an old runtime,
  and writes `.gate-ok` only after that gate passed. A failed build never
  touches the previous runtime.
- `gate-ember-runtime.sh`: the standalone gate (ONE argument: a runtime
  folder). Runs the frozen program twice and demands honest behavior:
  `capture` without an API key exits 1 with exactly one stderr line
  starting `error: CAPTURE-008`, and `db-check` answers
  `version: 13` + `result: OK`. The gate keeps its log folder on failure
  and prints the full error. Pass = the marker is written by the build
  script, never by the gate itself.
- `check-deb.sh`: the `.deb` acceptance check (ONE argument: a `.deb`
  path; optional second argument: the release folder, default
  `app/dist/release/`). Inspects modes, symlink targets, migrations,
  weights and architecture with `dpkg-deb`. Refuses: any symlink pointing
  outside the package (also system paths like `/usr/lib/...` — every
  library is bundled, decision I12), any world-writable regular file,
  missing migrations `.sql` files, missing `model.safetensors`
  under `models/hub`, and `Architecture:` other than `amd64`. On PASS it
  saves the `.deb` + a dated report into the release folder and keeps only
  the newest 3 (decision D-21). On FAIL it exits non-zero and never saves
  the `.deb` (decision D-12). Runs alone on any `.deb` (so you can vet a
  suspect artifact); it is NOT run in CI (decision D-11) — it needs real
  packages.
- `pack.js`: the packer (`npm run package` from `app/`, never run bare).
  Its staging step is an exported, testable function (`stageBundle`):
  copy with `verbatimSymlinks: true` (a relative symlink stays relative),
  normalize modes (directories and executables 0755, other files 0644),
  refuse a runtime without `.gate-ok`, refuse a non-amd64 machine (read
  from `dpkg --print-architecture`, not from a label), and refuse ANY
  world-writable file in the stage as the last gate before
  `dpkg-deb --build`. It also writes `bundle.json` (app version, engine
  version, a content hash of the runtime) and the Debian control file
  (with `libnotify4`, `libatspi2.0-0`, `libuuid1`, `libsecret-1-0` in
  `Depends`). Merely requiring the module builds nothing
  (`require.main` guard).

## The rules, and WHY (a future developer's cheat sheet)

1. **CPU torch only (decision 3-B).** The pack venv's torch must come from
   `https://download.pytorch.org/whl/cpu`. Plain PyPI torch pulls multi-GB
   CUDA wheel sets: useless on a CPU-only machine and enormous in the
   bundle. The build script refuses a `+cu` torch.
2. **PyInstaller never in the maintainer `.venv`.** The build tool must
   not disturb the environment you develop in. Keep a COPY venv
   (see "One-time setup" below) and point `EMBER_PACK_VENV` at it. The
   build script refuses the repo `.venv` when it lacks PyInstaller, with
   exactly this message.
3. **The build scratch is multi-GB and lands NEXT TO `EMBER_RUNTIME_OUT`**
   (same disk, never `/tmp` — on many systems tmp is a small tmpfs).
4. **No runtime without `.gate-ok` gets packed** (story 12 in the spec).
   The marker exists only after the frozen program passed the gate, so the
   pack refuses a markerless runtime instead of shipping an untested one.
5. **The old runtime is touched only after the new one passed everything**
   (story 11): build, smoke, gate and marker all happen inside a scratch
   folder; the swap is the LAST step.
6. **Fail = nothing saved but the report** (D-12); **keep the newest 3**
   passing builds (D-21).

## Environment variables (all optional, read by the scripts)

| Variable | Meaning | Used by |
|---|---|---|
| `EMBER_PACK_VENV` | the venv with ember + CPU torch + PyInstaller | `build-ember-runtime.sh` |
| `EMBER_RUNTIME_OUT` | where the frozen runtime lands (must be an absolute path; `/` and the repo itself are refused) | `build-ember-runtime.sh` |
| `EMBER_MODEL_CACHE` | a Hugging Face hub cache that already holds `models--BAAI--bge-base-en-v1.5/model.safetensors`; the weights are COPIED into the bundle so the shipped app makes no first-run download | `build-ember-runtime.sh` |
| `EMBER_PACK_ROOT` | the pack's working root; the release folder defaults to `<pack root>/release` | `pack.js` |

## One-time setup (a machine that builds)

1. Make a COPY venv of the repo's locked stack (same pinned versions),
   plus `pyinstaller` in the copy. Torch must be installed from the CPU
   index. Never install PyInstaller into the repo's `.venv`.
2. Install `ember` into the COPY as an editable install pointing at the
   repo (`pip install -e <repo>`), so the build packages the live code.
3. Run the build on the real disk, not tmpfs:

       source <your pack env file>
       bash app/scripts/build-ember-runtime.sh    # the multi-minute step
       npm --prefix app run package               # builds the .deb + runs the check

   Expected result: `ember runtime ready at <EMBER_RUNTIME_OUT>`, the pack
   ends with the check passing, and `app/dist/release/` gains one `.deb` +
   one dated report.

On this machine (2026-11-01) the copy venv lives at
`/home/mo/lab/ember-pack/venv` and the variable file is
`/home/mo/lab/ember-pack/pack-env.sh` (machine-local, not part of the
repo).

## The tests that pin all of this

- `app/test/runtime-gate.test.js`: the gate's five behavior cases on stub
  runtimes.
- `app/test/runtime-build.test.js`: refusals (unsafe output paths,
  weightless or foreign model cache), the gate-before-swap flow (a failed
  gate leaves the old runtime with a canary file intact), bundle hygiene
  (no `__pycache__`, a broken `du` cannot fail the build).
- `app/test/pack-staging.test.js`: verbatim symlinks, safe modes,
  marker/amd64/world-writable refusals, `bundle.json` contents, and
  "merely requiring `pack.js` builds nothing".
- `app/test/check-deb.test.js`: one clean pass and one fixture per refusal
  reason, plus the keep-3 and save-report-not-deb policies.

Everything above is asserted by tests, so the README cannot silently drift
from the scripts: change a behavior, a test goes red.

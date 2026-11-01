# Batch 1: release artifact

**Source:** `archive/Plan.md` Batch 1. Decisions D-02, D-11, D-12, D-19, D-21, D-23. Findings from `archive/Problems.md`.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch1.md`). Not yet published.

## Problem Statement

The `.deb` only works on the machine that built it, and it is unsafe to install.

- 22 symlinks inside it point at `/home/mo/lab/ember/...`. On any other machine numpy, scipy and the model fail to load.
- 70 root-owned files are writable by every user, including the Electron binary. Any local account could replace the program that runs with a setuid sandbox.
- The runtime build can delete the last good runtime and leave a broken one that the packer still accepts.
- The build accepts any model cache, even one with no weights, which breaks the offline promise.
- The only packaging test reads script text, so all of this passes CI.
- Other people will install this soon (D-02).

## Solution

- The packer copies symlinks as they are and gives every file a safe mode.
- A local check script inspects every built `.deb` and refuses a bad one (D-11). It keeps each good `.deb` and its report in a gitignored repo folder, and only the last 3 builds (D-12, D-21).
- The runtime build never replaces a good runtime with an unchecked one.
- The build checks for the exact model and its weights.
- The packer refuses to build on anything but amd64 (D-19).
- `ember --version` exists. The engine and the app each report one version, each from one source; they may differ.

## User Stories

1. As someone installing Ember on my own machine, I want every library and the model to load, so that the app works outside the build machine.
2. As someone installing Ember, I want no installed file to be writable by other users, so that another account cannot replace the program.
3. As the founder, I want the packer to refuse output with any world-writable file, so that a mistake never ships.
4. As the founder, I want a check script that runs after every build, so that a bad `.deb` never looks finished.
5. As the founder, I want the check to fail on any symlink pointing at a build-machine path, so that portability is proven, not assumed.
6. As the founder, I want the check to confirm migration `.sql` files are present, so that a new install can create its database.
7. As the founder, I want the check to confirm the model weights are inside, so that the first relate never needs the network.
8. As the founder, I want the check to confirm the architecture is amd64, so that the label is always true.
9. As the founder, I want each good `.deb` and a dated check report saved in one gitignored repo folder, so that I can hand out or roll back a known-good build.
10. As the founder, I want only the last 3 builds kept, so that the folder stays around 1.6 GB.
11. As the founder, I want a failed runtime gate to leave the previous good runtime in place, so that a failed build costs nothing.
12. As the founder, I want the packer to refuse a runtime that did not pass the gate, so that a broken runtime cannot be packed.
13. As the founder, I want the build to check for the exact model and its weights file, so that a weightless bundle fails at build time.
14. As the founder, I want a relative output path to work or fail before the slow PyInstaller step, so that I don't lose 20 minutes.
15. As the founder, I want the build never to `rm -rf` an unchecked path, so that a wrong variable cannot delete my files.
16. As the founder, I want the build gate to require exactly one stderr line with the expected error code, so that a traceback cannot pass as success.
17. As the founder, I want `ember --version` to work, so that the build's version step stops printing an error.
18. As the founder, I want the app, the engine and `bundle.json` to report one version and a content hash, so that I know exactly what a `.deb` contains.
19. As the founder, I want the packer to stop on a non-amd64 machine, so that it never makes a mislabelled package.
20. As someone installing Ember, I want the package's dependency list to include every system library the app needs, so that install does not leave the app unable to store my key.
21. As the founder, I want the packer to use the runtime the build just made, so that a stale runtime never ships silently.
22. As the founder, I want build failure logs kept and the full error shown, so that I can see why it failed.
23. As the founder, I want `__pycache__` folders left out of the bundle, so that the package carries no build leftovers.
24. As the founder, I want the size report never to fail a good build, so that a reporting step cannot block a release.
25. As the founder, I want the build's model-cache checks to give the right answer under `pipefail`, so that a needed link is never deleted.
26. As a contributor, I want the packaging test to check the built output, not script text, so that a broken gate cannot pass.
27. As a contributor, I want the version test to check the one engine source, `app/package.json`, and a fixed list of known copies, so that a hardcoded version is caught (N2).
28. As a contributor, I want the gate to be its own script that runs on any runtime folder, so that I can test it without a full 20-minute build (N1).

## Implementation Decisions

### Packer
- Copies symlinks verbatim (relative targets stay relative).
- Normalizes modes while staging: 0755 for directories and executables, 0644 for other files. `chrome-sandbox` keeps the setuid mode set by `postinst`.
- Before building the `.deb`, asserts no staged file is world-writable. Refuses otherwise.
- Refuses unless the build machine is amd64 (D-19). Keeps `Architecture: amd64`.
- Reads the runtime from the location the build reports, and refuses a runtime without a gate-passed marker written by the build.
- `bundle.json` records the app version, the engine version, and a content hash of the runtime.
- `Depends` adds `libnotify4`, `libatspi2.0-0`, `libuuid1`, `libsecret-1-0`.

### `.deb` check script (new)
- A local script, run by the packer as its last step and runnable alone on any `.deb` (constitution: modules run alone on sample input).
- Checks: no symlink target outside the package, no world-writable file, migration `.sql` files present, model weights file present, architecture amd64.
- Writes a dated report. On pass, saves the `.deb` and the report to one gitignored repo folder and deletes builds beyond the newest 3 (D-12, D-21).
- On fail, exits non-zero, keeps the report, and does not save the `.deb`.
- Not run in CI (D-11).

### Runtime build script
- Builds into a temp location, runs the gate there, and replaces the old runtime only after the gate passes. Writes the gate-passed marker.
- The gate is its own script, taking the runtime folder as its argument (for example `app/scripts/gate-ember-runtime.sh <runtime-dir>`). The build script calls it before replacing the old runtime, and tests call it on stub runtimes (N1). Before the factor-out, the gate only ran after a full PyInstaller build (`app/scripts/build-ember-runtime.sh:174-202`).
- Canonicalizes the output path at start, and refuses an empty or unexpected path before any delete.
- Checks the configured model id and its `model.safetensors`.
- The gate requires exactly one stderr line that starts with the expected code.
- Keeps gate logs on failure and prints the whole error.
- Excludes `__pycache__`. The size report never changes the exit code. Model-cache checks avoid `grep -q` under `pipefail`.

### Version
- One version source for the engine. `ember --version` prints it.
- Engine and app versions are both recorded in `bundle.json`. They may differ, but each comes from one place.
- The version test (N2) checks the one engine source, `app/package.json`, and a fixed list of known copies (fixed or allow-listed). It does not try to discover every future place a version is written.

## Testing Decisions

**Good tests here** check the built output and the exit code, never script text.

**Seams (D-23):**
1. **The `.deb` check script.** Run it on small fixture `.deb` files built in the test with `dpkg-deb`: one clean, one with an absolute symlink, one with a world-writable file, one missing `.sql` files, one missing weights, one labelled arm64. Each bad one fails with a distinct reason. Retention: with 4 saved builds, the oldest is deleted.
2. **The packer's staging step** on a small fixture tree with a relative symlink and a mode-777 file: the staged tree keeps the relative link and has no world-writable file. It refuses a runtime without the gate-passed marker (story 12), and refuses on a non-amd64 machine name. This needs the packer to expose its staging step: today it is one `main()` with fixed input paths (`app/scripts/pack.js:49-119`), so it cannot yet run on a fixture tree (see `archive/spec-check-batch1.md`).
3. **The `ember` CLI:** `ember --version` exits 0 and prints the engine version.
4. **The gate script (N1):** run it on a stub `ember` folder. A stub that prints exactly one line starting with the expected code passes; a traceback, an empty output, or two lines fail (story 16). This needs no torch, no PyInstaller, and no CI build — the whole point of the factor-out (`archive/spec-check-batch1.md`, Decision 1, option A).

**Version test (N2):** a static test in this batch, the successor of `app/test/packaging.test.js:18-34` (today's only version-one-place test — a blanket replacement of that file would delete it). It asserts: the engine reads its version from the one source module, the app from `app/package.json:3`, and every known hardcoded copy is either the fixed value or on an allow-list. Today's known copies: `docs/T50-live-test.md:3` and `:203` hardcode `0.2.0`. It has nothing to assert until the one-source engine version (Implementation Decisions → Version) is landed.

**Prior art:** `app/test/packaging.test.js` (its four text-grep tests are replaced, its version test is succeeded by the Version test above). The Batch 0 key wizard test runs a script on a temp folder, the same pattern.

**Prove each test:** break the behavior on purpose (for example set `verbatimSymlinks` back) and see the test go red.

## Out of Scope

- Building or checking the `.deb` in CI (D-11).
- arm64 builds (D-19).
- Signing, upgrade paths, a public release.
- The rebuild with the Batch 2 error boundary. That happens at the end of Batch 2.
- An automatic scan that finds every future place a version is written. The known copies in the version test are a fixed list, updated by hand when a new copy appears (N2).

## Further Notes

- One `.deb` is about 540 MB, model included (483 MB of 1.82 GB installed). [Fact: `archive/assumption-check.md`]
- Decision (N1, made 2026-11-01): the runtime build gate moves into its own script, called by the build and callable by tests. For the record: before this factor-out, the gate ran only after a full PyInstaller build — it was inline in the build script, called the built binary, and had no mode that ran it alone (`app/scripts/build-ember-runtime.sh:174-202`; the venv checks at `:50-55` ran before everything). Option A was taken over keeping it inline (options and costs were in `archive/spec-check-batch1.md`, Decision 1).

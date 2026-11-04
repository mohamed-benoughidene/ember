# L3 App Step 13: packaging, size, no-network check, before/after measure

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §2, §3 decisions 2 and 3, §8. Spec decision 9, stories 107, 109, 110. Needs all earlier steps. (The three-system launch check starts in step 02 if decision 2 is B; this step finishes packaging.)
**RISK step (AGENTS.md §2):** adds packaging tools (packages) and edits `.github/workflows/` (new jobs, runner minutes). Show exact tool names and the workflow plan, and ask A or B before editing workflows.

## Constitution rules this step enforces
T9 (the app's own import check runs in CI), S1, D6 (versions), I13 (config at boot), B3.

## Deferred settings resolved by this step
- Python bundling method (chosen by step 01), built here.
- Whether GitHub's free runners cover the full build (step 01 proves only a hello-world).
- Platform scope (decision 2): with A, Windows and macOS stay launch checks and no public installer is made for them.

## 1. Boundary shapes (cite L2 §3, §5.8)
- Installers: Linux (Debian-friendly package or AppImage). With decision 2 = B: also Windows and macOS, unsigned; the install will warn and release notes say so plainly. Each carries the bundled `ember`, the fonts with their licence text, and the project licence.
- CI: the Python job stays; add a matrix job (`ubuntu-latest`, plus `windows-latest` and `macos-latest`) that builds the app and runs the launch check (open a temp knowledge base, run one read command, print the item count, exit 0).
- Story 107: a test that Electron makes zero outside requests during the E2E run (the content-security rule and no auto-update are asserted).
- Story 110: the deliverable `docs/interface-measure.md`: for each of the six jobs, what the terminal needs (command names, flags, numbers, set-up steps) against what the interface needs, counted from the real commands (spec §13 table, completed). Not invented: counts come from `docs/commands.md`.
- Install-size report per OS printed in the job log; the founder's acceptance recorded in Build Notes.
- Version number in one place, shown in About.

## 2. Tests
- Launch check on the chosen systems (automatic). The full E2E suite stays Linux-only.
- App import check (renderer imports no `fs`/`child_process`) runs in CI.
- Zero-outside-request test.
- Not covered by tests: manual behaviour on Windows or macOS (the founder has neither). Until a person with those machines runs the checklists of steps 11 and 12, the release notes say "Windows and macOS are launch-checked only".

## 3. Check commands (S1)
```
$ npm --prefix app run package            -> installer file(s) in app/dist, sizes printed
$ npm --prefix app run check:launch       -> exit 0, prints "items: N"
```
CI shows the launch checks green.

## 4. Error codes raised (L2 §6)
APP-007 if the bundled runtime is missing at launch (a test deletes it and expects the message).

## 5. Rollback
Revert the workflow commit; `app/dist` is git-ignored. Releases are not published by this step.

## 6. Done when
Launch checks green (real run links in Build Notes), sizes recorded, the founder's decision on size recorded, `docs/interface-measure.md` written, and `PROJECT_MAP.md` has one line per tracked file under `app/` (package manifest, lockfile, fonts, licence, CSS, tests, fixtures), because the docs-sync test fails on any tracked file without a line.

# L3 App Step 13: packaging, CI on three systems, install size

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §2, §8. Spec decision 9, story 109. Needs all earlier steps.
**RISK step (AGENTS.md §2):** adds CI jobs and packaging tools (packages), and changes `.github/workflows/`. Show the plan and ask A or B before editing workflows.

## Constitution rules this step enforces
T9 (architecture check in CI), S1, D6 (versions), I13 (config at boot), B3.

## Deferred settings resolved by this step
- Python bundling method (chosen in step 01), built here.
- Whether GitHub's free runners cover Windows and macOS builds (spec §11: not checked). Step 01 already uses them; this step confirms for the full build.

## 1. Boundary shapes
- Installers: Linux (Debian-friendly package or AppImage), Windows installer, macOS app bundle (unsigned; code signing and notarisation are NOT in V1 and the install will warn on macOS and Windows — state this to the founder).
- Each installer carries the bundled `ember`, the fonts and the font licence text, and the project's licence.
- CI: the existing Python job stays; add a matrix job (`ubuntu-latest`, `windows-latest`, `macos-latest`) that builds the app and runs a launch check: the app starts, opens a temp knowledge base, runs one read command, reports the item count, exits 0.
- Install-size report per OS, printed in the job log with real numbers; the founder's acceptance recorded in Build Notes.
- Version number: one place, shown in About.

## 2. Tests
- Launch check on all three systems (automatic). The full E2E suite stays Linux-only (cost).
- Architecture node test (renderer imports no `fs`/`child_process`) runs in CI.
- Not covered by tests: any manual behaviour on Windows or macOS; the founder has neither. A person with those machines runs the manual checklist from steps 11 and 12 before a public release. Until then the release notes say "Windows and macOS are launch-checked only".

## 3. Check command (S1)
```
$ npm --prefix app run package            -> installer file(s) in app/dist, sizes printed
$ npm --prefix app run check:launch       -> exit 0, prints "items: N"
```
CI shows three green launch checks.

## 4. Error codes raised
APP-007 if the bundled runtime is missing at launch (test deletes it and expects the message).

## 5. Rollback
Revert the workflow commit; remove `app/dist` (ignored by git). Releases are not published by this step.

## 6. Done when
Three green CI launch checks (real run links in Build Notes), sizes recorded, founder decision on size recorded, `PROJECT_MAP.md` updated for `app/`.

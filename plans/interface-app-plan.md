# L2 Plan: Interface App (the Electron desktop app)

Status: DRAFT 2026-10-30, not yet through the review gate. **Gated by step 01 (the spike).** Nothing is built.
Origin: `docs/ember-interface-spec.md` (the whole spec; 110 user stories), `docs/PRODUCT.md` and `docs/DESIGN.md` (approved by the founder 2026-10-30), `docs/PROTOTYPE-ember-interface-v3.html` (the approved look, made-up data).
L1: `plans/master-plan.md` §8, "Interface module amendment".
Needs first: `plans/engine-undo-plan.md` and `plans/interface-bridge-plan.md` built.
Branch: `ember-interface`.

## Plain words (for the founder)

This is the window. It holds no Ember rules. It starts `ember` commands in the background, reads their data, and draws the screens you approved. It keeps three things of its own: your settings, your AI key, and the window itself. Before any real code, step 01 checks the three things the spec said must be checked (can it run Ember's Python, does the popup shortcut work on Windows and Mac, how big is the install). If a check fails, we use Tauri and this plan is rewritten.

## §1 Purpose (one job)

Draw the six jobs, Settings, the quick popup and the menus over the bridge, in the approved look, and never do more than the matching command.

## §2 Facts this plan stands on

- Spec, `PRODUCT.md`, `DESIGN.md` and the prototype are approved; the prototype has made-up data and is NOT connected to Ember.
- Jobs and the commands behind them: spec §2 table (Add, Look up, Link items, Fix and close, Clean up, Keep safe) plus Undo and Redo.
- Key: passed to Ember as `EMBER_AI_API_KEY` in the child process environment (bridge L2 §2). No Python change.
- Typeface: Atkinson Hyperlegible Next/Mono, SIL OFL 1.1, self-hosted, licence text shipped (spec §8).
- Founder tests on Debian only; Windows and macOS get automatic launch checks only (spec decision 9). CI today is `ubuntu-latest` only (`.github/workflows/test.yml`).
- **Install size risk (Inference, unmeasured):** `relate` needs the optional package `sentence-transformers` (`pyproject.toml`), which pulls in a large machine-learning library. A bundled Python plus that package may make the install very large. Step 01 measures it. No number is claimed here.
- **Python runtime risk (Fact about the user, Inference about the fix):** a non-coder cannot install Python 3.12 or run `pip`. The app must carry or install its own Python/Ember. How is decided by step 01.
- Wayland may block global shortcuts (spec §11); the founder's session type is not yet known.

## §3 Decisions this plan makes (A/B, need the maintainer at the review gate)

1. **UI code style.** **A (recommended):** plain JavaScript, HTML and CSS, no UI framework, tokens from `DESIGN.md` as CSS variables. Fewest packages (AGENTS.md §2: every package is a risk), and the prototype is already plain HTML. **B:** a framework (React/Svelte). Faster for big UIs, more packages and more updates to watch.
2. **Test tools.** **A (recommended):** Node's built-in test runner for pure logic, and Playwright's Electron support for end-to-end. Both are dev-only. **B:** Node built-in runner only, no end-to-end. Cheaper, but the keyboard, focus and 200% text checks stay manual. Adding either is a package add and is confirmed again at step 02 with exact names and versions.

## §4 Module layout (location only; internals are the implementer's)

```
app/package.json                 (Electron + dev tools; versions pinned at step 02)
app/main/                        (Electron main process: windows, menus, tray, shortcut, bridge client, stores)
app/renderer/                    (screens, components, styles; no Node access)
app/preload/                     (the one narrow, named list of calls the renderer may make)
app/shared/                      (pure: error-line parser, event types, plain-sentence table, settings schema)
app/assets/fonts/ + LICENSE text (Atkinson)
app/test/                        (node tests, e2e)
```
Rule: the renderer talks only through the preload list; the main process is the only place that starts `ember`.

## §5 Design

### §5.1 Bridge client (main process)
`runCommand(name, args) -> {ok, data} | {ok:false, error:{code,name,where,detail}}` for one-shot commands (`--format json`, error line parsed per bridge L2 §5.2). `runConfirmSession(name, args)` for `capture`, `relate`, `maintain` with `--confirm json`: an object that emits `block`, `prompt`, `message`, `summary` events and accepts `answer(text)` and `stop()` (closing stdin). One child process per call; no shared state. The knowledge base path is always passed as `--db`.

### §5.2 Screens (spec §5, §2, user stories 1 to 110) — see steps 04 to 10
Every screen has normal, loading, empty, error and no-key states. Errors show inside the block that failed with what failed and a Retry. No bare code on screen; the code is available on request ("Details").

### §5.3 Settings store
A JSON file in the OS user-data folder (Electron's `app.getPath('userData')`), holding exactly the four settings of spec decision 8 plus last pane and knowledge base path. Written atomically (write temp, rename). Unreadable file → defaults and a notice, never a crash (`APP-004`). Saves itself with a quiet "Saved" (story 81).

### §5.4 Key store
Uses the operating system's secure storage through Electron's `safeStorage`; if the OS offers none (some Linux sessions), the app says so and offers "use for this session only" rather than writing the key in plain text (`APP-003`). The key is never written to a log, an error, or the ledger. Remove is clearly marked careful (story 89).

### §5.5 Quick popup and shortcut
A small always-on-top window, Add only (stories 90 to 95). Global shortcut defaults per spec §10; registration failure → tray icon with "Quick add / Open Ember / Quit" (`APP-005`). The popup uses the same Add component as the full window.

### §5.6 Plain-sentence table (`app/shared/`)
A pure table `code -> {title, what, next}` for every engine and bridge code the app can show (story 102). Unknown code → generic title naming the family, never a blank. A test walks `ember/**/errors.py` and fails when a code has no entry (so the table cannot drift).

### §5.7 Menus (spec §9)
One menu definition built from the spec table; Undo/Redo labels name the action ("Undo Close item 3") from the last undo plan's dry-run; items disabled, never hidden. Windows/Linux put the same menus in the window.

### §5.8 Motion and accessibility
One motion: the heat mark settles (~250 ms, transform/opacity only, off with Reduce Motion). Text size five steps to 200%; spacing in rem; contrast 4.5:1; every control has a name and a visible focus ring (spec 96 to 104).

## §6 Error codes (new namespace `APP-`, stable, never reused, I17)

| Code | Name | Raised at |
|---|---|---|
| APP-000 | AppError | base, never raised directly |
| APP-001 | BridgeSpawnFailed | cannot start `ember` |
| APP-002 | BridgeOutputInvalid | stdout is not the expected JSON / event line |
| APP-003 | KeyStoreUnavailable | OS secure storage missing or refused |
| APP-004 | SettingsUnreadable | settings file corrupt; defaults used |
| APP-005 | ShortcutRegistrationFailed | global shortcut refused; tray fallback |
| APP-006 | KnowledgeBaseMissing | chosen file not found or not an Ember file |
| APP-007 | RuntimeMissing | bundled Python/Ember not found at launch |

Engine and bridge codes are shown through the §5.6 table.

## §7 Test targets (T1 to T4)

1. **Unit (node, no Electron):** error-line parser; event parser; plain-sentence table coverage (walk every `errors.py` code); settings schema validation and atomic write; menu builder (labels, disabled state); text-size/rem math; shortcut-conflict warnings (Control on a Mac, no modifier, standard Mac shortcut).
2. **Contract:** the app's bridge client runs against a real temp knowledge base created by Python test helpers: every job's data matches the matching `ember` command output (spec "one test seam"); forbidden actions stay forbidden through the app (edit a statement, set a Closed item's status, back up onto the source file).
3. **E2E (Playwright, Linux only in CI):** first run, Add with a fake AI, Look up, Fix and close with Undo, Clean up, Keep safe, Settings survive a restart, 200% text no horizontal overflow, keyboard-only pass of one flow, Reduce Motion honoured.
4. **Not covered by tests (say so, check another way):** look and feel (screenshot review at 1440, 768, 390 px, per spec); real screen readers; global shortcut on every system; Windows/macOS behaviour beyond a launch check; install size on the founder's machine. Manual checklist is written in step 12.

## §8 Steps (L3), bottom-up

| # | File | Phase |
|---|---|---|
| 01 | `plans/steps/app/01-spike-three-checks.md` | The three checks + Python packaging. Gate. |
| 02 | `plans/steps/app/02-shell-bridge-client-stores.md` | Electron shell, bridge client, settings and key stores |
| 03 | `plans/steps/app/03-design-system.md` | Tokens, fonts and licence, heat mark, states, motion |
| 04 | `plans/steps/app/04-first-run-home-lookup.md` | First run, Home, Look up |
| 05 | `plans/steps/app/05-add.md` | Add + the confirm UI |
| 06 | `plans/steps/app/06-link-items.md` | Link items |
| 07 | `plans/steps/app/07-fix-and-close-undo.md` | Fix and close + Undo and Redo |
| 08 | `plans/steps/app/08-clean-up.md` | Clean up (sweep) |
| 09 | `plans/steps/app/09-keep-safe.md` | Backup, export, health check, open file |
| 10 | `plans/steps/app/10-settings.md` | Settings panes |
| 11 | `plans/steps/app/11-quick-popup-tray.md` | Quick popup, shortcut, tray |
| 12 | `plans/steps/app/12-menus-keyboard-accessibility.md` | Menu bar, keyboard, accessibility pass |
| 13 | `plans/steps/app/13-packaging-and-ci.md` | Installers, CI on three systems, size |

## §9 Deferred to L3
- Exact Electron version and package list (step 02, confirmed by A/B).
- Python bundling method (step 01 decides; step 13 builds it).
- Popup placement options and default (step 11).
- Font language subsets (step 03; spec §8 says the build must include the ones users need — decided with the founder).
- Help content for the Help menu (out of scope; item disabled, spec).
- Search in the title bar, drag and drop (spec "Still open"): not in V1 unless the founder decides before step 04/05.

## §Z Constitution compliance

- **B1** one job: draw and relay. **B2** Python is reached only through the bridge commands. **B3** all rules stay in Python; the app depends on the stable bridge contract. **B4** the app hides Electron, OS storage and shortcuts from the screens. **B5** a small preload surface.
- **D1** the app stores no Ember data of its own. **D2** nothing derived is stored. **D3** counts and statuses come from the commands, never recomputed. **D4** every child-process line is untrusted and validated once at the bridge client. **D5/D6** settings schema is versioned with a number.
- **P2** UI → bridge client → command layer → logic → data. **P4** bridge client, key store, settings store, shortcut and tray are adapters behind small interfaces that tests fake.
- **I1-I4** names by job, typed shapes. **I5-I7** named `APP-` errors handled at the edge, never swallowed. **I9** validate at the client. **I13** settings loaded once at boot and passed down. **I15** child process timeouts and a retry limit on every call. **I17-I21** stable codes, entity ids (item/link ids) carried, no key in any error.
- **T1** parsers/builders pure. **T2** Electron/OS effects at the edge. **T3** fakes for stores and shortcuts. **T4** pyramid §7. **T5/T6** observable behaviour. **T9** an architecture check (a small node test) asserts the renderer imports no `fs`, `child_process` or Electron main APIs.
- **S1** every step has a launch/check command. **S2** `app/test/` runs alone. **S3/S4** the bridge contract and preload list are documented.

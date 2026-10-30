# L2 Plan: Interface App (the Electron desktop app)

Status: DRAFT 2, 2026-10-30. Revised after the first review round (4 reviewers). Not yet approved. **Gated by step 01 (the spike).** Nothing is built.
Origin: `docs/ember-interface-spec.md` (the whole spec; 123 user stories), `docs/PRODUCT.md` and `docs/DESIGN.md` (approved by the founder 2026-10-30), `docs/PROTOTYPE-ember-interface-v3.html` (the approved look, made-up data).
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
- Wayland may block global shortcuts (spec §11); the founder's session type is not yet known. **User task today:** run `echo $XDG_SESSION_TYPE` and `echo $XDG_CURRENT_DESKTOP` on the Debian machine and tell me the answers (Inference, to verify: a GNOME session on Wayland may also hide tray icons, so the tray fallback is not enough alone; §5.5 adds a menu route).
- A child process cannot use in-process fakes. The AI can be faked across a process boundary by a local server on `EMBER_AI_BASE_URL`. The embedder cannot be faked (bridge L2 §2, decision D2).
- Electron's `safeStorage` on Linux without a keyring may use a weak backend (Inference from Electron's documentation; **verify for the pinned version in step 01**, do not rely on this sentence).

## §3 Decisions for the maintainer at the L2 gate (A/B)

1. **Spike timing.** **A (recommended):** run the spike (step 01) FIRST, before Undo starts. It needs neither Undo nor the Bridge, and it answers the biggest unknowns (Python for a non-coder, install size, Wayland, Electron on three systems) before weeks of other work rest on a guess. **B:** run it after the Bridge, as the draft order had it. Undo then Bridge then App stays the build order for real code either way.
2. **Platform scope for V1.** **A (recommended):** Debian is the only supported system for V1; Windows and macOS stay CI launch checks (no public installer). The founder owns no Windows or macOS machine and the installers would be unsigned (a non-coder meets "unknown publisher" warnings). **B:** ship all three unsigned with a one-page "how to open it" guide and a named volunteer tester. Spec decision 9 still holds in both.
3. **Link items and the embedder.** `relate` needs `sentence-transformers` (large) and downloads a model on first run (story 45), which conflicts with story 107 ("no network request except the AI service"). **A (recommended):** the base app ships small; Link items is an optional download, shown plainly on first use, with a founder exception to story 107 for that download. **B:** bundle the embedder in every install (larger, simpler, still a download of model weights unless they are bundled too). The spike records both sizes.
4. **AI key storage (secrets, AGENTS.md §2).** **A (recommended):** OS secure storage only; if the backend is weak or missing, the app refuses to save and offers "use for this session only". **B:** a key file in the user-data folder with owner-only permissions (0600), described plainly to the user. Affects: 0 existing keys; nothing stored today. Undo: Settings -> remove key. In both, the key reaches Ember only as an environment variable of the child process.
5. **Key test (stories 5 and 8).** No command tests a key. **A (recommended):** length and shape check now, and the real test happens at the first Add with a plain "key refused" message; stories 5 and 8 are marked PARTIAL and the founder signs that off. **B:** a new read-only `ember check-key` command (a cheap AI call, a 23rd command) added to the Bridge plan before its closeout.
6. **UI code style.** **A (recommended):** plain JavaScript, HTML and CSS, no UI framework (fewest packages, the prototype is already plain HTML). **B:** a framework (React or Svelte).
7. **Test tools.** **A (recommended):** Node's built-in test runner plus Playwright's Electron support (dev-only). **B:** Node's runner only (keyboard, focus and 200% text checks stay manual). Either is a package add, confirmed again at step 02 with exact names and versions.

Also decided in the plan, not by choice: the settings file lives in Electron's user-data folder (0 existing settings files); the popup look is a proposal the founder reviews at step 11.

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
`runCommand(name, args) -> {ok, data} | {ok:false, error:{code,name,where,detail}}` for one-shot commands (`--format json`, error line parsed per bridge L2 §5.2). `runConfirmSession(name, args)` for `capture`, `relate`, `maintain` with `--confirm json`: an object that emits `block`, `prompt`, `message`, `summary` events and accepts `answer(text)` and `stop()` (closing stdin). One child process per call; no shared state. The knowledge base path is always passed as `--db`. **Retry rule (I15 applies to external services; here it is limited):** read commands (`list-items`, `show-item`, the query commands, `db-check`) get a timeout and one automatic retry. **Write commands get a timeout and NO automatic retry** (a repeated `undo` or `close-item` could run twice); after a write timeout the app re-reads state, then offers Retry (`APP-008`).

### §5.2 Screens (spec §5, §2, user stories 1 to 123) — see steps 04 to 13
Every screen has normal, loading, empty, error and no-key states. Errors show inside the block that failed with what failed and a Retry. No bare code on screen; the code is available on request ("Details").

**Job -> commands (all 18 current commands are reachable, plus the four new ones):**

| Job | Commands |
|---|---|
| Add | `capture` (Add uses it with `--file`); `capture-source` is NOT used by the app (it only stores a source; Add stores it as part of `capture`) |
| Look up | `list-items`, `topic-search`, `show-item`, `history`; `current-state` and `why` stay available (Home may use `current-state`; `show-item` replaces `why` for the provenance view because it also carries "Challenged by" and "Replaced by") |
| Link items | `relate` |
| Fix and close | `set-status`, `close-item`, `edit-item`, `remove-link`, `reverse-supersedes`, `set-validated`, `clear-validated`, `undo`, `redo` |
| Clean up | `maintain` |
| Keep safe | `backup`, `export`, `db-check` |

**Story coverage (story -> step file number in §8):** 1-9 -> 04 (and 02, 10 for the key); 10-15 -> 04; 16-29 -> 05; 30-41 -> 04; 42-48 -> 06; 49-62 -> 07; 63-69 -> 08; 70-77 -> 09; 78-89 -> 10; 90-95 -> 11; 96-100 -> 03 helper + 12; 101-104 -> 03 + 12; 105-106 -> 02 and every contract test; **107 -> 13 (network check)**; 108 -> 03; 109 -> 13 (or 01/02 per decision 2); **110 -> 13 (`docs/interface-measure.md`)**; 111-121 -> 07 (+ Undo L2); 122 -> 04 (ledger words) ; 123 -> 07. Each L3 step lists its own stories one by one, not as a range.

Every screen has normal, loading, empty, error and no-key states. Errors show inside the block that failed with what failed and a Retry. No bare code on screen; the code is available on request ("Details").

### §5.3 Settings store
A JSON file in the OS user-data folder (Electron's `app.getPath('userData')`), holding exactly the four settings of spec decision 8 plus last pane and knowledge base path. Written atomically (write temp, rename). Unreadable file → defaults and a notice, never a crash (`APP-004`). Saves itself with a quiet "Saved" (story 81).

### §5.4 Key store
Per decision 4. Default proposal: the OS secure storage through Electron's `safeStorage`; if the backend is weak or missing, the app says so and offers "use for this session only" rather than writing the key in plain text (`APP-003`). Which backend is in use is printed by the spike on the founder's Debian machine. The key is never written to a log, an error, or the ledger. Remove is clearly marked careful (story 89).

### §5.5 Quick popup and shortcut
A small window, Add only (stories 90 to 95; "always on top" is a proposal the founder reviews at step 11). Global shortcut defaults per spec §10. Registration failure -> tray icon with "Quick add / Open Ember / Quit" (`APP-005`). Because a tray may not show on every desktop, there are two more routes that always work: the menu item File -> Add text (opens the popup) and a launch option on the app (`ember-app --quick-add`). The popup uses the same Add component as the full window.

### §5.6 Plain-sentence table (`app/shared/`)
A pure table `code -> {title, what, next}` for every engine and bridge code the app can show (story 102). Unknown code → generic title naming the family, never a blank. A test walks `ember/**/errors.py` and fails when a code has no entry (so the table cannot drift).

### §5.7 Menus (spec §9)
One menu definition built from the spec table; Undo/Redo labels name the action ("Undo Close item 3") from the last undo plan's dry-run; items disabled, never hidden. Windows/Linux put the same menus in the window.

### §5.8 Network, motion and accessibility
Story 107: the app makes no network request of its own. A content-security rule blocks outside hosts in the window, auto-update is off, and a step 13 test asserts zero outside requests during the E2E run (the only network use is `ember` talking to the AI service the user chose).

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
| APP-008 | BridgeTimeout | a child process exceeded its time limit (reads retry once, writes never) |

Engine and bridge codes are shown through the §5.6 table.

## §7 Test targets (T1 to T4)

1. **Unit (node, no Electron):** error-line parser; event parser; plain-sentence table coverage (walk every `errors.py` code); settings schema validation and atomic write; menu builder (labels, disabled state); text-size/rem math; shortcut-conflict warnings (Control on a Mac, no modifier, standard Mac shortcut).
2. **Contract:** the app's bridge client runs against a real temp knowledge base created by Python test helpers: every job's data matches the matching `ember` command output (spec "one test seam"); forbidden actions stay forbidden through the app (edit a statement, set a Closed item's status, back up onto the source file).
3. **Shared accessibility helper (step 03):** a test helper that scans for unnamed interactive elements and horizontal overflow at the Largest size; every screen step (04 to 11) runs it in its own E2E and lists that in its Done-when.
4. **E2E (Playwright, Linux only in CI):** the fake AI is a local HTTP server on `EMBER_AI_BASE_URL`; first run, Add with a fake AI, Look up, Fix and close with Undo, Clean up, Keep safe, Settings survive a restart, 200% text no horizontal overflow, keyboard-only pass of one flow, Reduce Motion honoured.
5. **Not covered by tests (say so, check another way):** Link items end to end with the real embedder (bridge decision D2); look and feel (screenshot review at 1440, 768, 390 px, per spec); real screen readers; global shortcut on every system; Windows/macOS behaviour beyond a launch check; install size on the founder's machine. Manual checklist is written in step 12.

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
| 12 | `plans/steps/app/12-menus-keyboard-accessibility.md` | Menu builder, manual accessibility checklist |
| 13 | `plans/steps/app/13-packaging-and-ci.md` | Installers, size, no-network check, before/after measure |

## §9 Deferred to L3
- Exact Electron version and package list (step 02, confirmed by A/B).
- Python bundling method (step 01 decides; step 13 builds it).
- Popup placement options and default (step 11).
- Font language subsets (step 03; spec §8 says the build must include the ones users need — decided with the founder).
- Key test (decision 5) and platform scope (decision 2) follow the maintainer's answers.
- Help content for the Help menu (out of scope; item disabled, spec).
- Search in the title bar, drag and drop (spec "Still open"): not in V1 unless the founder decides before step 04/05.

## §Z Constitution compliance

- **B1** one job: draw and relay. **B2** Python is reached only through the bridge commands. **B3** all rules stay in Python; the app depends on the stable bridge contract. **B4** the app hides Electron, OS storage and shortcuts from the screens. **B5** a small preload surface.
- **D1** the app stores no Ember data of its own. **D2** nothing derived is stored. **D3** counts and statuses come from the commands, never recomputed. **D4** every child-process line is untrusted and validated once at the bridge client. **D5/D6** settings schema is versioned with a number.
- **P2** UI -> bridge client -> command layer (the Python side is one-way, so P2 is claimed only for the app's own layers). **P4** bridge client, key store, settings store, shortcut and tray are adapters behind small interfaces that tests fake.
- **I1-I4** names by job, typed shapes. **I5-I7** named `APP-` errors handled at the edge, never swallowed. **I9** validate at the client. **I13** settings loaded once at boot and passed down. **I15** timeouts on every call; retry limit on reads only. **I17-I21** stable codes, entity ids (item/link ids) carried, no key in any error.
- **T1** parsers/builders pure. **T2** Electron/OS effects at the edge. **T3** fakes for stores and shortcuts. **T4** pyramid §7. **T5/T6** observable behaviour. **T9** has no JavaScript equivalent; the app has its OWN check (a small node test asserting the renderer imports no `fs`, `child_process` or Electron main APIs). **I15** is applied to reads only (§5.1).
- **S1** every step has a launch/check command. **S2** `app/test/` runs alone. **S3/S4** the bridge contract and preload list are documented.

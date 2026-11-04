'use strict';

// [shortcut graveyard fix] Boots here must not really register the global
// shortcut — every real bind left a stale KDE portal entry on the founder's
// machine. Nothing in this file asserts registration; the scenarios that do
// (popup.js, settings.js) opt out explicitly.
process.env.EMBER_APP_SHORTCUT_REFUSED ??= '1';

/**
 * The screen-lifetime E2E (Batch 5 chunk 12; F5, findings 4.9 #1/#2).
 * Runs against the real Electron shell with the fake ember stub
 * (helpers/shell.js launchShell, FAKE_MODE=app) — deterministic, no
 * Python and no AI.
 *
 * The fake engine's `app` mode does not speak `db-check`, so Keep
 * safe's auto-running health check comes back with the house error
 * line — the check "returns", which is all this batch needs. To make
 * the return DEFINITELY late (the story navigates within 200 ms; a
 * fast racing answer could not reproduce F5 dependably), the
 * scenario's EMBER_APP_COMMAND points at a throwaway node wrapper
 * written into the scenario's own workDir that holds ONLY the
 * `db-check` invocation for CHECK_DELAY_MS before exec-ing the real
 * fake-ember stub (stdio inherited, exit code passed through); every
 * settled child appends one line to a workDir log. NOTE: the main
 * process ALSO runs its own boot-time db-check (the Edit menu's
 * undo-label gate, main.js undoLabelsSafeForFile), so the test never
 * assumes the first log line is the screen's — it reads the CHANGE in
 * the count after Keep safe opens, and case B takes its proof from
 * the DOM itself.
 *
 *  Case A (F5; Plan.md "Done when", first half): open Keep safe (the
 *    health check auto-runs), navigate to Settings within 200 ms,
 *    settle the Settings AI-connection pane, type gibberish key text;
 *    after the health check returns, Settings must still be on screen,
 *    the typed text intact, and nothing may repaint over Settings in
 *    the seconds that follow.
 *  Case B (the normal case): a late Keep-safe result does NOT paint
 *    anything outside Keep safe — and staying on Keep safe, the
 *    settled check state still shows inside it.
 *
 *  Batch 5 chunk 13 adds two more cases over the REAL `ember` from the
 *  venv (the add.js/cleanup.js harness patterns — a real temp knowledge
 *  base with the AI faked at EMBER_AI_BASE_URL; no key ever rides the
 *  environment, the test key is kept in the app via setSessionKey):
 *
 *  Case Add (plan case B; stories 3, 4; findings 4.9 #3/#4/#5): visit
 *    Add three times — the middle of the first visit leaves a live
 *    confirm session waiting on its question — then press y. Only the
 *    CURRENT screen may react: the fresh Add form has no session, so
 *    nothing may answer, and the background session must keep waiting
 *    (a new add afterwards is refused with "already running").
 *  Case Sweep (plan case C; story 4; finding 4.9 #17): leave Clean up
 *    mid-sweep. On leaving, its dispose must stop the running sweep
 *    session (the same stop the Stop button uses), and its
 *    document-level sweep keys must be dead on the OTHER pane —
 *    pressing y on Home must answer nothing, and no further sweep
 *    events may arrive after leaving.
 *
 *  Batch 5 chunk 19 closes the window lifetime (stories 5-8; findings
 *  4.9 #6/#7; D-24) with two more cases over the plain fake shell:
 *
 *  Case D (story 5, story 6's route; D-24): close the main window the
 *    way the titlebar X does (a real BrowserWindow 'close' event) —
 *    the app PROCESS must stay alive and the window must hide to the
 *    tray (still there, just not visible, NOT destroyed); then the
 *    "Open Ember" route — driven through the REAL preload door
 *    (`window.ember.quickOpenMain`, the same handler the tray's Open
 *    Ember item and the popup's story-93 link reach today) — must show
 *    the SAME window again, with the same still-working page.
 *  Case E (stories 7, 8; 4.9 #7): launching a second instance against
 *    the same profile folder must NOT start a second Ember — the
 *    second process exits and the FIRST window keeps the app: still
 *    one main process, still exactly one Ember window, and the first
 *    window holds the focus again.
 *    Focus note (probed 2026-11-02): under Xvfb the window-level
 *    `BrowserWindow.isFocused()` flickers (4/30 true reads right after
 *    show()+focus(), under a real WM too), but the renderer read the
 *    user actually experiences — `document.hasFocus()` (where the
 *    keyboard lands) — was 30/30 stable. Case E asserts hasFocus().
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile, execFileSync } = require('node:child_process');
const { promisify } = require('node:util');
const { _electron } = require('playwright');
const { APP_ROOT, REPO_ROOT, FAKE_EMBER, PYTHON } = require('../util');
const { launchShell } = require('./helpers/shell.js');
const { startFakeAiServer } = require('../helpers/fake-ai-server.js');

const execFileP = promisify(execFile);
/** The REAL ember from the venv (add.js/cleanup.js harness pattern;
 * the worktree's .venv symlink points at the repo venv). */
const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');
/** A fake OpenAI-shape key, kept in the app via setSessionKey — no key
 * ever rides an environment variable (Batch 0's key-stripped rule). */
const TEST_KEY = 'sk-or-v1-ember-e2e-fake-key-0123456789';

/** How long the throwaway wrapper holds every `db-check` child. Well
 * past the 200 ms navigation budget, so ordering is never a race. */
const CHECK_DELAY_MS = 1500;
/** The gibberish key text typed into the AI-connection pane (no real
 * key — it is never saved; story 2's "typed key text"). */
const TYPED_KEY = 'sk-not-a-real-key-gibberish-0123456789';

function fail(what) {
  throw new Error(what);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The number of settled `db-check` children recorded in `file` (the
 * wrapper appends one line per settled child). Missing file = 0.
 */
function dbCheckLogCount(file) {
  try {
    return fs
      .readFileSync(file, 'utf8')
      .split('\n')
      .filter((line) => line.includes('db-check')).length;
  } catch {
    return 0;
  }
}

/**
 * Wait until the db-check log is quiet: at least one entry, and no new
 * entry for QUIET_MS. Main's boot-time undo-label gate also runs
 * db-check children, so the caller must compare against the count this
 * returns, never assume zero.
 */
async function waitForDbChecksQuiet(file, quietMs = 2500, timeoutMs = 30000) {
  const started = Date.now();
  let last = 0;
  let stableSince = 0;
  for (;;) {
    const count = dbCheckLogCount(file);
    if (count !== last) {
      last = count;
      stableSince = Date.now();
    }
    if (count >= 1 && Date.now() - stableSince >= quietMs) return count;
    if (Date.now() - started > timeoutMs) {
      throw new Error(`timed out waiting for the db-check log to go quiet in ${file}`);
    }
    await sleep(250);
  }
}

/** Poll until the settled-children count reaches `wanted`. */
async function waitForDbCheckCount(file, wanted, timeoutMs = 20000) {
  const started = Date.now();
  for (;;) {
    if (dbCheckLogCount(file) >= wanted) return;
    if (Date.now() - started > timeoutMs) {
      throw new Error(`timed out waiting for ${wanted} settled db-check children in ${file}`);
    }
    await sleep(100);
  }
}

/**
 * Launch one shell whose ember command is the real fake-ember stub
 * behind the db-check-delaying wrapper. Everything the wrapper needs
 * rides launchShell's extraEnv seam (no helper changes).
 */
async function launchLifetimeShell(workDir) {
  const wrapper = path.join(workDir, 'slow-ember.cjs');
  const done = path.join(workDir, 'children-done.log');
  const spawnLog = path.join(workDir, 'spawn.log');
  fs.writeFileSync(
    wrapper,
    `${[
      "'use strict';",
      '// Throwaway e2e wrapper (Batch 5 chunk 12): holds ONLY `db-check`',
      '// for a fixed time, then speaks to the real fake-ember stub. Every',
      '// settled child appends one line to EMBER_CHILD_LOG (exit code kept).',
      'const { spawn } = require("node:child_process");',
      'const fs = require("node:fs");',
      'const args = process.argv.slice(2);',
      `const delay = args.includes("db-check") ? ${CHECK_DELAY_MS} : 0;`,
      'setTimeout(() => {',
      '  const child = spawn(process.execPath, [process.env.EMBER_SLOW_FAKE, ...args], { stdio: "inherit" });',
      '  child.on("exit", (code) => {',
      '    try { if (process.env.EMBER_CHILD_LOG) fs.appendFileSync(process.env.EMBER_CHILD_LOG, args.join(" ") + "\\n"); } catch {}',
      '    process.exit(typeof code === "number" ? code : 1);',
      '  });',
      `}, delay);`,
    ].join('\n')}\n`,
  );
  const shell = await launchShell({
    workDir,
    mode: 'app',
    extraEnv: {
      // space-split is today's EMBER_APP_COMMAND rule (chunk 17 changes
      // it): no spaces in any of these throwaway paths.
      EMBER_APP_COMMAND: `node ${wrapper}`,
      EMBER_SLOW_FAKE: FAKE_EMBER,
      EMBER_CHILD_LOG: done,
      FAKE_SPAWN_LOG: spawnLog,
    },
  });
  return { ...shell, done, spawnLog };
}

/** Shuts the shell down even when a global shortcut holds it open. */
async function closeShell(app, workDir) {
  await Promise.race([
    app.close(),
    new Promise((resolve) =>
      setTimeout(() => {
        try { app.process().kill('SIGKILL'); } catch { /* already gone */ }
        resolve();
      }, 5000),
    ),
  ]);
  fs.rmSync(workDir, { recursive: true, force: true });
}

/** Plan.md "Done when", asserted as one named check: Settings is still
 * on screen — no Keep safe repaint anywhere — and the typed key text
 * sits intact in the AI-connection pane's key field. */
async function assertSettingsIntact(win, when) {
  const keepsafePanes = await win.locator('[data-testid="keepsafe-pane"]').count();
  if (keepsafePanes !== 0) fail(`the late Keep-safe result painted over or beside Settings (${when}): keepsafe pane count ${keepsafePanes}`);
  const settingsPane = await win.locator('[data-testid="settings-ai"]').count();
  if (settingsPane !== 1) fail(`Settings is no longer on screen (${when}): settings-ai pane count ${settingsPane}`);
  const value = await win.inputValue('[data-testid="settings-key-input"]');
  if (value !== TYPED_KEY) fail(`the typed key text was lost (${when}): ${JSON.stringify(value)}`);
}

/* ---------------- case A: the F5 reproduction ---------------- */

async function staleResultCannotPaint() {
  process.stdout.write('--- case A: Keep safe opens, Settings within 200 ms, then the check returns (F5) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lifetime-'));
  const { app, done } = await launchLifetimeShell(workDir);
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    // Let main's own boot-time db-check children (the undo-label gate)
    // finish; from here the count only moves when OUR screen spawns one.
    const before = await waitForDbChecksQuiet(done);

    // Open Keep safe: the health check auto-runs on open (story 75).
    await win.click('#nav button[data-job="keepsafe"]');
    await win.waitForSelector('[data-testid="keepsafe-pane"]');

    // Navigate to Settings within the story's 200 ms budget, switch to
    // the AI-connection pane, open its key form (not connected: "Set
    // up the connection"; otherwise "Replace key"), and type gibberish
    // into the key field. The pane's own key-status read settles BEFORE
    // the typing, so afterwards the ONLY result still in flight is the
    // Keep-safe health check.
    await win.click('#nav button[data-job="settings"]');
    await win.waitForSelector('[data-testid="settings-appearance"]');
    await win.click('[role="tab"][data-pane="ai"]');
    await win.waitForSelector('[data-testid="settings-ai"]');
    await win.waitForSelector('[data-testid="ai-status"]');
    const setUp = win.locator('[data-testid="ai-set-up"]');
    if ((await setUp.count()) !== 0) await setUp.click();
    else await win.click('[data-testid="ai-replace"]');
    await win.waitForSelector('[data-testid="settings-key-input"]:not([hidden])');
    await win.fill('[data-testid="settings-key-input"]', TYPED_KEY);

    // Wait for the health check to actually RETURN (one settled child
    // more than the quiet baseline), then a settle for the IPC hop.
    await waitForDbCheckCount(done, before + 1);
    await win.waitForTimeout(800);

    // "Settings is still on screen after the health check returns",
    // the typed key text is intact (Plan.md "Done when"), and nothing
    // repaints over Settings in the seconds that follow.
    await assertSettingsIntact(win, 'right after the check returned');
    await win.waitForTimeout(2000);
    await assertSettingsIntact(win, 'two seconds later');
    process.stdout.write('case A OK: Settings is still on screen after the health check returns; the typed key text is intact\n');
  } finally {
    await closeShell(app, workDir);
  }
}

/* ---------------- case B: the normal case ---------------- */

async function lateResultPaintsInsideKeepSafe() {
  process.stdout.write('--- case B: staying on Keep safe, the late check result still paints inside it ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lifetime-stay-'));
  const { app } = await launchLifetimeShell(workDir);
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    // Open Keep safe and STAY: the check must still reach the pane.
    // The settled check state (the fake engine refuses db-check, so
    // the house error area is the settled state) IS the DOM proof that
    // the check returned and painted inside Keep safe.
    await win.click('#nav button[data-job="keepsafe"]');
    await win.waitForSelector('[data-testid="keepsafe-pane"]');
    await win.waitForSelector('[data-testid="ks-check-body"]');
    await win.waitForSelector('[data-testid="ks-check-error"]', { timeout: 30000 });

    const stillKeepsafe = await win.locator('[data-testid="keepsafe-pane"]').count();
    if (stillKeepsafe !== 1) fail(`Keep safe lost its pane while staying on it: count ${stillKeepsafe}`);
    const homePanes = await win.locator('[data-testid="home-pane"]').count();
    if (homePanes !== 0) fail(`the settled result painted outside Keep safe: home pane count ${homePanes}`);
    process.stdout.write('case B OK: the late Keep-safe result painted inside Keep safe only\n');
  } finally {
    await closeShell(app, workDir);
  }
}

/* ================== chunk 13: over the real ember ==================
   From here the harness follows the add.js / cleanup.js pattern: the
   REAL `ember` child from the venv, a REAL temp knowledge base, and a
   local fake OpenAI server on EMBER_AI_BASE_URL. Deterministic, no
   network, and no AI key ever in the environment. */

const ADD_NOTE = 'We decided to use SQLite for local storage. We assume the team ships weekly.';
const ADD_PROPOSALS = [
  { type: 'Decision', statement: 'Use SQLite for local storage', source_quote: 'use SQLite for local storage', confidence: 0.9 },
  { type: 'Assumption', statement: 'The team ships weekly', source_quote: 'the team ships weekly', confidence: 0.8 },
];

/** Two confirmed answers links make items 7 and 9 stale (the sweep's
 * shortlist); copied from e2e/cleanup.js's SEED_TWO_STALE. */
const SEED_TWO_STALE = `
import sys
from pathlib import Path
from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_link_with_confirmation, insert_source

db = sys.argv[1]
Path(db).touch()
conn = open_maintain_database(db)
try:
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type='Finding', statement='auth measured')
    insert_item(conn, source_id=source_id, item_id=7, item_type='Question', statement='should we cache tokens?', status_origin='manual')
    insert_item(conn, source_id=source_id, item_id=9, item_type='Question', statement='which auth backend?', status_origin='manual')
    insert_link_with_confirmation(conn, 1, 7, 'answers', created_at='2026-01-01T00:00:00+00:00')
    insert_link_with_confirmation(conn, 1, 9, 'answers', created_at='2026-01-01T00:00:00+00:00')
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (7, NULL, 'status_origin', 'derived', 'manual',"
        " '2026-01-02T00:00:00+00:00', 'user_set_status')"
    )
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (9, NULL, 'status_origin', 'derived', 'manual',"
        " '2026-01-02T00:00:00+00:00', 'user_set_status')"
    )
    conn.commit()
finally:
    conn.close()
`;

/** Launch one shell over the REAL ember with a REAL temp knowledge
 * base (the add.js launchApp / cleanup.js launch shape). The test key
 * is kept in the app afterwards via setSessionKey — never in the env. */
async function launchRealEmberShell(workDir, kbPath, lastPane, aiUrl) {
  const configDir = path.join(workDir, 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  const stateHome = path.join(workDir, 'state');
  fs.mkdirSync(stateHome, { recursive: true });
  fs.writeFileSync(
    path.join(userData, 'settings.json'),
    `${JSON.stringify(
      {
        schema: 1,
        textSize: 'default',
        colourTheme: 'system',
        quickPopup: { shortcut: 'CommandOrControl+Alt+N', position: 'bottom-right' },
        menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
        menuHidden: [],
        lastPane,
        knowledgeBasePath: kbPath,
      },
      null,
      2,
    )}\n`,
  );
  const env = {
    ...process.env,
    XDG_CONFIG_HOME: configDir,
    XDG_STATE_HOME: stateHome,
    EMBER_APP_DB: kbPath,
    EMBER_APP_COMMAND: EMBER,
    EMBER_AI_BASE_URL: aiUrl, // the local fake server (never a network host)
  };
  // The operator's real keys must never reach the child; fake-session
  // leftovers from other scenarios must stay out too.
  delete env.EMBER_AI_API_KEY;
  delete env.OPENROUTER_API_KEY;
  delete env.FAKE_MODE;
  delete env.FAKE_SESSION_DIE;
  delete env.FAKE_SESSION_DIE_CODE;
  delete env.FAKE_SESSION_SCRIPT;
  delete env.FAKE_SESSION_IDLE;
  delete env.FAKE_CRASH_ID;
  if (env.EMBER_AI_API_KEY !== undefined || env.OPENROUTER_API_KEY !== undefined) {
    fail('an AI key survived the strip and would reach the launched app');
  }
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  const win = await app.firstWindow();
  await win.waitForSelector('#nav button');
  const kept = await win.evaluate((k) => window.ember.setSessionKey(k), TEST_KEY);
  if (!kept || !kept.ok) fail('the test key could not be kept in the test app');
  // The boot render predates the key: re-open the pane exactly like
  // add.js's goToAdd does, so the form (not the no-key gate) shows.
  await win.click(`#nav button[data-job="${lastPane}"]`);
  return { app, win };
}

async function closeRealEmberShell(app, workDir, ai = null) {
  await app.close().catch(() => {});
  if (ai) await ai.close().catch(() => {});
  fs.rmSync(workDir, { recursive: true, force: true });
}

/** Read one item's live row through the engine's own door (cleanup.js). */
async function itemRow(dbPath, id) {
  const { stdout } = await execFileP(EMBER, ['list-items', '--db', dbPath]);
  const doc = JSON.parse(stdout);
  return doc.items.find((it) => it.id === Number(id));
}

/* ---------- plan case B (stories 3, 4; 4.9 #3/#4/#5) ---------- */

async function addKeysDieWithTheScreen() {
  process.stdout.write('--- case Add (plan case B): visit Add three times, press y — only the CURRENT session reacts ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lifetime-add-'));
  const kbPath = path.join(workDir, 'kb.db');
  const ai = await startFakeAiServer({ content: JSON.stringify(ADD_PROPOSALS) });
  const { app, win } = await launchRealEmberShell(workDir, kbPath, 'add', ai.url);
  try {
    // Add visit 1 (boot opened Add): start a session; the engine asks
    // about proposal 1 and waits for an answer.
    await win.waitForSelector('[data-testid="add-text-input"]');
    await win.fill('[data-testid="add-text-input"]', ADD_NOTE);
    await win.click('[data-testid="add-start"]');
    try {
      await win.waitForSelector('[data-testid="proposal"]', { timeout: 30000 });
    } catch (err) {
      const flowText = await win
        .locator('#pane')
        .innerText()
        .catch(() => '(pane unreadable)');
      const codeEl = await win
        .locator('[data-testid="error-code"]')
        .first()
        .evaluate((el) => {
          el.hidden = false;
          return el.textContent;
        })
        .catch(() => '(no error code block)');
      throw new Error(`the first add session never reached its proposal (ai calls: ${ai.calls.length}; error-code: ${codeEl}): ${flowText.slice(0, 400)}`);
    }

    // Leave mid-question, then visit Add twice more — three screens
    // total. (With the bug, every visit piles one more keydown handler
    // onto the outliving pane and none ever dies.)
    await win.click('#nav button[data-job="home"]');
    await win.waitForSelector('[data-testid="home-pane"]');
    await win.click('#nav button[data-job="add"]');
    await win.waitForSelector('[data-testid="add-text-input"]');
    await win.click('#nav button[data-job="home"]');
    await win.waitForSelector('[data-testid="home-pane"]');
    await win.click('#nav button[data-job="add"]');
    await win.waitForSelector('[data-testid="add-text-input"]');

    // Press y on the third visit: THIS screen is a fresh form with no
    // session, so nothing may react. With the bug, the hidden screens'
    // handlers answer the still-running session behind this screen —
    // the engine's engine WRITES the confirmed proposal to the ledger
    // without any user action (I7: the engine writes only on confirm).
    await win.locator('#pane').focus();
    await win.keyboard.press('y');
    await win.waitForTimeout(4000);
    const itemsDoc = JSON.parse(execFileSync(EMBER, ['list-items', '--db', kbPath], { encoding: 'utf8', cwd: REPO_ROOT }));
    if (itemsDoc.total !== 0) {
      fail(
        `pressing y after leaving Add made a HIDDEN screen answer the running session (stories 3/4; 4.9 #3): ` +
          `the engine wrote ${itemsDoc.total} item(s) to the ledger without any key on the CURRENT screen`,
      );
    }

    // The background session must still be the one running (nothing
    // was answered): starting a new add here is refused.
    await win.fill('[data-testid="add-text-input"]', ADD_NOTE);
    await win.click('[data-testid="add-start"]');
    await win.waitForSelector('[data-testid="state-error"], [data-testid="add-flow"] [data-testid="proposal"]', { timeout: 30000 });
    const refusal = await win.locator('[data-testid="state-error"]').count();
    if (refusal !== 1) {
      const flowText = await win.locator('#pane').innerText();
      fail(
        `pressing y after leaving Add made a HIDDEN screen answer the running session (stories 3/4; 4.9 #3): ` +
          `the add start was not refused, so the background session was spent by a phantom key; the screen shows: ${flowText.slice(0, 300)}`,
      );
    }
    const errText = await win.textContent('[data-testid="state-error"]');
    process.stdout.write(`case Add OK: y on the fresh form answered nothing; the background session still runs (start refused: ${errText.trim().slice(0, 120)}…)\n`);
  } finally {
    await closeRealEmberShell(app, workDir, ai);
  }
}

/** How many of THIS knowledge base's real `ember maintain --confirm`
 * sweep children are still alive (the process table; the sweep child
 * is uniquely named by its temp knowledge-base path). */
function liveSweepChildren(kbPath) {
  const out = execFileSync('ps', ['-eo', 'args'], { encoding: 'utf8' });
  return out
    .split('\n')
    .filter((line) => line.includes(`maintain --db ${kbPath}`) && line.includes('--confirm json') && !line.includes('--dry-run'))
    .length;
}

/* ---------- plan case C (story 4; 4.9 #17) ---------- */

async function leavingCleanupStopsTheSweep() {
  process.stdout.write('--- case Sweep (plan case C): leave Clean up mid-sweep — no sweep events arrive after leaving; the sweep keys act only on Clean up ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lifetime-cleanup-'));
  const kbPath = path.join(workDir, 'kb.db');
  execFileSync(PYTHON, ['-c', SEED_TWO_STALE, kbPath], { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] });
  // The default canned answer proposes the close for EVERY stale
  // question, so a surviving (unstopped) sweep visibly moves on.
  const ai = await startFakeAiServer({});
  const { app, win } = await launchRealEmberShell(workDir, kbPath, 'cleanup', ai.url);
  try {
    await win.waitForSelector('[data-testid="pane-cleanup"]');
    await win.click('[data-action="cleanup-preview"]');
    // SEED_TWO_STALE has zero dry-run status changes but two stale
    // questions — the shortlist, not the table (cleanup.js scenario 2).
    try {
      await win.waitForSelector('[data-testid="cleanup-stale-list"]', { timeout: 30000 });
    } catch (err) {
      const flowText = await win
        .locator('#pane')
        .innerText()
        .catch(() => '(pane unreadable)');
      const codeEl = await win
        .locator('[data-testid="error-code"]')
        .first()
        .evaluate((el) => {
          el.hidden = false;
          return el.textContent;
        })
        .catch(() => '(no error code block)');
      throw new Error(`the sweep preview never showed its table: ${flowText.slice(0, 400)} (error-code: ${codeEl})`);
    }
    await win.click('[data-testid="cleanup-apply"]');
    await win.waitForSelector('[data-testid="sweep-proposal"]', { timeout: 30000 });
    // The proposal's own question must be OPEN (the Confirm button
    // renders only while the engine's prompt is unanswered).
    await win.waitForSelector('[data-testid="sweep-confirm"]', { timeout: 30000 });
    if (ai.calls.length !== 1) fail(`the sweep should have asked the AI for the first candidate only, saw ${ai.calls.length} calls`);

    // LEAVE mid-sweep, to Home.
    await win.click('#nav button[data-job="home"]');
    await win.waitForSelector('[data-testid="home-pane"]');

    // On Home the sweep keys must be dead (4.9 #17), and leaving must
    // have stopped the sweep session (story 4 — the Stop button's own
    // stop: handle.stop(), which closes the engine's stdin). Press y a
    // few times and give any SURVIVING session time to be visible.
    await win.locator('#pane').focus();
    for (let i = 0; i < 3; i += 1) {
      await win.keyboard.press('y');
      await win.waitForTimeout(700);
    }
    await win.waitForTimeout(3000);

    if (ai.calls.length !== 1) {
      fail(`sweep events kept arriving after leaving Clean up (story 4; 4.9 #17): the fake AI was called ${ai.calls.length} times, expected 1`);
    }
    const row7 = await itemRow(kbPath, 7);
    if (row7.status !== 'Active') {
      fail(`the sweep's phantom y wrote to the ledger after the user left (story 4): item 7 is ${row7.status}, expected Active`);
    }
    const alive = liveSweepChildren(kbPath);
    if (alive !== 0) {
      fail(
        `leaving Clean up mid-sweep left the sweep RUNNING (story 4; 4.9 #17): ` +
          `${alive} real "ember maintain --confirm" child for this knowledge base was still alive ` +
          `after leaving, and the loop's document-level keys were still armed outside Clean up`,
      );
    }
    process.stdout.write('case Sweep OK: the sweep was stopped on leaving; y on Home answers nothing and writes nothing (1 AI call, item 7 Active, no sweep child alive)\n');
  } finally {
    await closeRealEmberShell(app, workDir, ai);
  }
}

/* ================== chunk 19: the window closes, the app stays ======
   Stories 5-8 over the plain fake shell (launchShell, FAKE_MODE=app):
   no knowledge base work here, just the app shell's own lifetime. */

/** Read the whole Ember-window state from the main process in one hop
 * (the same main-process window reads the popup e2e trusts over the
 * Playwright-forced document visibility). */
function readEmberWindow(app) {
  return app.evaluate(({ BrowserWindow }) => {
    const w = BrowserWindow.getAllWindows().find((x) => x.getTitle() === 'Ember');
    return w
      ? { there: true, visible: w.isVisible(), countOfWindows: BrowserWindow.getAllWindows().length }
      : { there: false, visible: false, countOfWindows: BrowserWindow.getAllWindows().length };
  });
}

async function waitEmberVisible(app, want, timeoutMs = 15000) {
  const started = Date.now();
  for (;;) {
    const state = await readEmberWindow(app);
    if (state.there && state.visible === want) return state;
    if (Date.now() - started > timeoutMs) {
      throw new Error(`the Ember window never became ${want ? 'visible' : 'hidden'} (${JSON.stringify(state)})`);
    }
    await sleep(100);
  }
}

/** The user-experienced focus read (see the header note): does this
 * first window's page hold the keyboard? */
function firstWindowHasFocus(win) {
  return win.evaluate(() => document.hasFocus());
}

/* ---------- chunk 19 case D (story 5, story 6's route; D-24) ---------- */

async function closingTheWindowKeepsEmberAlive() {
  process.stdout.write('--- case D: close the main window — the process stays, "Open Ember" shows it again ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lifetime-tray-'));
  const { app } = await launchShell({ workDir });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    // Close the window exactly the way the titlebar X does: a real
    // BrowserWindow 'close' event (page.close() would tear the page
    // down itself and prove nothing about the app's close handling).
    await app.evaluate(({ BrowserWindow }) => {
      const w = BrowserWindow.getAllWindows().find((x) => x.getTitle() === 'Ember');
      w.close();
    });

    // The OLD behaviour quits the whole app here; give that plenty of
    // room so a green run can never pass by racing ahead of a quit.
    await sleep(2500);

    // 1) the app process must still be alive...
    let ready = false;
    try {
      ready = await app.evaluate(({ app: theApp }) => theApp.isReady());
    } catch (err) {
      fail(`the app PROCESS DIED when the main window was closed (story 5; D-24): ${String(err.message).split('\n')[0]}`);
    }
    if (!ready) fail('the app PROCESS DIED when the main window was closed (story 5; D-24): the main process past the closed event is not ready');

    // 2) ...and the window must be hidden to the tray, NOT destroyed.
    let state = null;
    try {
      state = await readEmberWindow(app);
    } catch (err) {
      fail(`the window is gone after closing (story 5; D-24): ${String(err.message).split('\n')[0]}`);
    }
    if (!state.there) fail('closing the window DESTROYED it (the Ember window no longer exists; story 5 keeps it in the tray)');
    if (state.visible) fail('after closing, the window is still VISIBLE — it must hide to the tray (D-24)');

    // 3) "Open Ember" (the REAL route: the tray item and the popup's
    // story-93 link both land on openMainRequest via the preload door)
    // must show the SAME window again — the one page, still working.
    const opened = await win.evaluate(() => window.ember.quickOpenMain());
    if (!opened || opened.ok !== true) fail(`the "Open Ember" route refused to show the window again: ${JSON.stringify(opened)}`);
    await waitEmberVisible(app, true);
    await win.waitForSelector('[data-testid="home-pane"]');
    process.stdout.write('case D OK: closing the window left the process alive, the window hidden in the tray; "Open Ember" showed the same, still-working window\n');
  } finally {
    await closeShell(app, workDir);
  }
}

/* ---------- chunk 19 case E (stories 7, 8; 4.9 #7) ---------- */

async function secondLaunchGoesToTheFirstWindow() {
  process.stdout.write('--- case E: a second launch exits and the FIRST window keeps the app ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lifetime-single-'));
  let app = null;
  let app2 = null;
  try {
    ({ app } = await launchShell({ workDir }));
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    // The second launch: the SAME throwaway profile folder, so it keys
    // on the same single-instance lock (the lock lives on the userData
    // path; every launchShell scenario has its own, never the dev's).
    let second;
    try {
      ({ app: app2 } = await launchShell({ workDir }));
      const exit = await new Promise((resolve) => {
        const timer = setTimeout(() => resolve({ stillRunning: true }), 20000);
        app2.process().once('exit', (code) => {
          clearTimeout(timer);
          resolve({ code });
        });
      });
      if (exit.stillRunning) {
        second = { stillRunning: true };
      } else if (exit.code !== 0) {
        second = { exitCode: exit.code };
      } else {
        second = { exitCode: 0 };
      }
    } catch (err) {
      // The driver could not even connect: the second instance died at
      // boot — that is the lock working, just before any window rode it.
      second = { bootExit: String(err.message ?? err).split('\n')[0] };
    }
    const problems = [];
    if (second.stillRunning) {
      problems.push('the second instance is STILL RUNNING as its own Ember process — two mains (story 8)');
    } else if (second.exitCode !== undefined && second.exitCode !== 0) {
      problems.push(`the second instance exited abnormally (code ${second.exitCode}) — that is a crash, not the single-instance exit`);
    }
    process.stdout.write(`the second launch ended as: ${JSON.stringify(second)}\n`);

    // Still ONE main process: the first app must keep answering.
    let alive = false;
    try {
      alive = await app.evaluate(({ app: theApp }) => theApp.isReady());
    } catch (err) {
      problems.push(`the FIRST app also stopped answering (${String(err.message).split('\n')[0]})`);
    }
    if (alive === false && !problems.some((p) => p.startsWith('the FIRST app'))) {
      problems.push('the FIRST app no longer answers — the first window lost its app');
    }

    // Still exactly ONE Ember window, and it is the shown one.
    let state = null;
    try {
      state = await readEmberWindow(app);
    } catch (err) {
      problems.push(`the first window could not be read anymore (${String(err.message).split('\n')[0]})`);
    }
    if (state) {
      const emberWindows = await app.evaluate(
        ({ BrowserWindow }) => BrowserWindow.getAllWindows().filter((x) => x.getTitle() === 'Ember').length,
      );
      if (emberWindows !== 1) problems.push(`expected exactly one Ember window, found ${emberWindows} (a second window was started)`);
      if (!state.visible) problems.push('the FIRST window is not shown anymore after the second launch');
    }

    // The first window holds the user's focus again (the user-experienced
    // focus read; see the header note on the isFocused() flicker).
    let hadFocus = false;
    const started = Date.now();
    while (Date.now() - started < 5000) {
      try {
        if (await firstWindowHasFocus(win)) { hadFocus = true; break; }
      } catch (err) {
        break;
      }
      await sleep(100);
    }
    if (!hadFocus) problems.push('the FIRST window does not hold the focus after the second launch');

    if (problems.length > 0) fail(`case E failed (stories 7, 8; 4.9 #7): ${problems.join('; ')}`);
    process.stdout.write('case E OK: the second instance exited (single-instance exit) and the FIRST window kept the app: one process, one shown window, the focus back on it\n');
  } finally {
    if (app2) await app2.close().catch(() => {});
    if (app) await closeShell(app, workDir);
  }
}

async function main() {
  await staleResultCannotPaint();
  await lateResultPaintsInsideKeepSafe();
  await addKeysDieWithTheScreen();
  await leavingCleanupStopsTheSweep();
  await closingTheWindowKeepsEmberAlive();
  await secondLaunchGoesToTheFirstWindow();
  process.stdout.write("e2e screen-lifetime OK: a stale screen's late result paints nothing; staying on Keep safe still gets the result; leaving a screen disposes its keys and stops its sweep; closing the window keeps the process (Open Ember shows it again); a second launch focuses the first window\n");
}

main().catch((err) => {
  process.stderr.write(`e2e screen-lifetime FAILED: ${err.message}\n`);
  process.exit(1);
});

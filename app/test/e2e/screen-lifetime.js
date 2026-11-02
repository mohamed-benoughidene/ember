'use strict';

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
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { FAKE_EMBER } = require('../util');
const { launchShell } = require('./helpers/shell.js');

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

async function main() {
  await staleResultCannotPaint();
  await lateResultPaintsInsideKeepSafe();
  process.stdout.write("e2e screen-lifetime OK: a stale screen's late result paints nothing; staying on Keep safe still gets the result\n");
}

main().catch((err) => {
  process.stderr.write(`e2e screen-lifetime FAILED: ${err.message}\n`);
  process.exit(1);
});

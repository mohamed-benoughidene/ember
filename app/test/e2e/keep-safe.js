'use strict';

/**
 * The step-09 E2E (dev-only, Linux; app step file §2-§3, ticket A38).
 * Unlike the step-04 screen e2e this runs against the REAL `ember`
 * (the worktree's own Python, via the main checkout's venv) on REAL
 * temp knowledge bases seeded by the project's Python test helpers —
 * no AI is needed for any flow here (backup, export, db-check and the
 * open-file switch run keyless).
 *
 * Scenarios:
 *  1. HEALTH CHECK + BACK UP + rotation (story 75, 70-71): the check
 *     runs on open and reads in plain words; a backup twice to one
 *     name shows the kept older copy (.old-1); the result line carries
 *     location, format version and item count.
 *  2. EXPORT (73-74): a text file lands on disk; the one-line honesty
 *     about "cannot be restored into Ember" shows; unchanged note.
 *  3. THE FORBIDDEN ACTIONS (72, 77): save location = the knowledge
 *     base itself -> the engine's BACKUP-003 / EXPORT-002 refusals in
 *     plain words, the code behind Details, and the live file unchanged.
 *  4. DRIFT + Reduce Motion (75, 99/104): a real drifted file reports
 *     DRIFT with Retry and what to do next; with Reduce Motion nothing
 *     animates.
 *  5. OPEN A DIFFERENT FILE (76): a v12 backup passes the db-check
 *     gate (no floor for v12), one confirmation names the file and says
 *     the current file is unchanged, the setting changes, the app ends
 *     up on the opened file.
 *  6. OPEN REFUSED (76 + APP-006): a non-Ember file is refused with a
 *     clear message and the current file stays chosen.
 *
 * The native save/open dialogs cannot be driven by Playwright, so the
 * main process honors EMBER_APP_SAVE_PATH / EMBER_APP_PICK_PATH as the
 * dialog's answer (test seams, same family as EMBER_APP_COMMAND). The
 * step-03 accessibility helper runs on every state shown here.
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { _electron } = require('playwright');
const { APP_ROOT, REPO_ROOT, PYTHON } = require('../util');
const { runAccessibilityScan } = require('../helpers/a11y-scan.mjs');

if (!fs.existsSync(PYTHON)) throw new Error(`the project venv python is missing at ${PYTHON} — the e2e cannot run`);
if (!process.cwd().startsWith(REPO_ROOT)) process.chdir(REPO_ROOT); // python -m ember must find the WORKTREE code

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function fail(what) {
  throw new Error(what);
}

/** Seed a REAL knowledge base with the project's Python helpers. */
function seedKb(kind) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-ks-'));
  const dbPath = path.join(dir, 'kb.db');
  execFileSync(PYTHON, ['-c', `from tests.bridge import harness; harness.${kind}(${JSON.stringify(dbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  if (!fs.existsSync(dbPath)) fail(`the seeder did not create ${dbPath}`);
  return dbPath;
}

/** A REAL untouched v12 knowledge base (the undo suite's builder). */
function seedV12() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-ksv12-'));
  const dbPath = path.join(dir, 'v12.db');
  execFileSync(PYTHON, ['-c', `from tests.test_v12_read_never_migrates import _build_v12_db; _build_v12_db(${JSON.stringify(dbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  return dbPath;
}

/** A REAL drifted knowledge base: one enforcement trigger dropped. */
function seedDrift() {
  const dbPath = seedKb('seed_pair');
  execFileSync(
    PYTHON,
    ['-c', `import sqlite3; c = sqlite3.connect(${JSON.stringify(dbPath)}); c.execute("DROP TRIGGER items_closed_reason_insert"); c.commit()`],
    { cwd: REPO_ROOT },
  );
  return dbPath;
}

/**
 * One real Electron shell per scenario. `useDbOverride` (default) sets
 * EMBER_APP_DB; leaving it off drives the SETTINGS path (the open-file
 * switch sits in settings, so scenario 5/6 seed the settings file).
 */
async function launchShell({ workDir, dbPath, useDbOverride = true, savePath = null, pickPath = null, lastPane = null }) {
  const configDir = path.join(workDir, 'config');
  fs.mkdirSync(path.join(configDir, 'ember-app'), { recursive: true });
  if (!useDbOverride || lastPane) {
    const kb = dbPath ?? path.join(workDir, 'settings-kb.db');
    let seed = seedSettingsTextFor(kb);
    if (lastPane) seed = seed.replace('"lastPane": "home"', `"lastPane": "${lastPane}"`);
    fs.writeFileSync(path.join(configDir, 'ember-app', 'settings.json'), seed);
  }
  const env = {
    ...process.env,
    XDG_CONFIG_HOME: configDir,
    EMBER_APP_COMMAND: `${PYTHON} -m ember`,
    PYTHONPATH: REPO_ROOT, // python -m ember must import the WORKTREE code even though Electron's cwd is app/
  };
  if (useDbOverride) env.EMBER_APP_DB = dbPath;
  if (savePath) env.EMBER_APP_SAVE_PATH = savePath;
  if (pickPath) env.EMBER_APP_PICK_PATH = pickPath;
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  return { app, configDir };
}

/** The exact settings.json the store writes (schema 1), inline so this file stays self-contained. */
function seedSettingsTextFor(kbPath, lastPane = 'home') {
  return `${JSON.stringify(
    {
      schema: 1,
      textSize: 'default',
      colourTheme: 'system',
      quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' },
      menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
      menuHidden: [],
      lastPane,
      knowledgeBasePath: kbPath,
    },
    null,
    2,
  )}\n`;
}

async function assertCleanScan(win, label) {
  const { violations, checked } = await runAccessibilityScan(win, {
    prepare: (page) => page.evaluate(() => document.documentElement.classList.add('big')),
    cleanup: (page) => page.evaluate(() => document.documentElement.classList.remove('big')),
  });
  if (violations.length > 0) {
    fail(`a11y scan on ${label} found ${violations.length}: ${JSON.stringify(violations, null, 2)}`);
  }
  process.stdout.write(`a11y scan clean on ${label} (${checked.tabbableCount} tabbable controls)\n`);
}

async function gotoKeepSafe(win) {
  await win.locator('#nav button[data-job="keepsafe"]').click();
  await win.waitForSelector('[data-testid="keepsafe-pane"]');
}

/* ---------------- scenario 1: health check + backup + rotation ---------------- */

async function checkAndBackup() {
  process.stdout.write('--- health check + backup (real KB) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ks-e2e-backup-'));
  const dbPath = seedKb('seed_pair');
  const target = path.join(workDir, 'backup.db');
  const { app } = await launchShell({ workDir, dbPath, savePath: target });
  try {
    const win = await app.firstWindow();
    await gotoKeepSafe(win);

    // Story 75: the check runs on open; every line reads in plain words.
    await win.waitForSelector('[data-testid="ks-check-verdict"]');
    const verdict = await win.textContent('[data-testid="ks-check-verdict"]');
    if (!/No problems found/.test(verdict)) fail(`a healthy file must say so (story 75): ${verdict.slice(0, 200)}`);
    const rows = await win.locator('[data-testid="ks-check-row"]').allTextContents();
    if (rows.length !== 8) fail(`the report has 8 lines and 8 plain rows are expected, saw ${rows.length}: ${JSON.stringify(rows)}`);
    for (const row of rows) {
      if (/^(version|floors|triggers|link_compat|foreign_key_check|reversal replay|group_id|result):/.test(row.trim())) {
        fail(`a report row leaked the raw machine line: "${row}"`);
      }
    }
    if (!rows.some((r) => /File format version 13/.test(r))) fail(`the version must read in plain words: ${JSON.stringify(rows)}`);
    await assertCleanScan(win, 'Keep safe (check OK)');

    // Story 70-71: one button; the engine's report becomes the result
    // line; a second run keeps the older copy as .old-1 and says so.
    await win.click('[data-testid="ks-backup-run"]');
    await win.waitForSelector('[data-testid="ks-backup-result"]');
    let result = await win.textContent('[data-testid="ks-backup-result"]');
    if (!result.includes(target)) fail(`story 71: the result line must name the file location: ${result}`);
    if (!/File format version 13/.test(result)) fail(`story 71: the format version must show: ${result}`);
    if (!/\b2 items\b/.test(result)) fail(`story 71: the item count must show (seed_pair has 2 items): ${result}`);
    if (!/unchanged/.test(result)) fail(`story 77: the result must say the knowledge base is unchanged: ${result}`);
    if (/old-1/.test(result)) fail('a FIRST backup must not claim an older copy was kept');

    await win.click('[data-testid="ks-backup-run"]');
    await win.waitForFunction(() => /old-1/.test((document.querySelector('[data-testid="ks-backup-result"]') ?? { textContent: '' }).textContent));
    result = await win.textContent('[data-testid="ks-backup-result"]');
    if (!result.includes(`${target}.old-1`)) fail(`the rotated copy must be named: ${result}`);
    if (!fs.existsSync(`${target}.old-1`)) fail('the engine must really keep the older copy on disk');
    process.stdout.write('backup + rotation OK: twice to one name keeps .old-1 and says so (stories 70-71)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
    fs.rmSync(path.dirname(dbPath), { recursive: true, force: true });
  }
}

/* ---------------- scenario 2: export ---------------- */

async function exportFlow() {
  process.stdout.write('--- export (real KB) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ks-e2e-export-'));
  const dbPath = seedKb('seed_pair');
  const target = path.join(workDir, 'export.txt');
  const { app } = await launchShell({ workDir, dbPath, savePath: target });
  try {
    const win = await app.firstWindow();
    await gotoKeepSafe(win);
    await win.waitForSelector('[data-testid="ks-check-verdict"]'); // the pane settled

    const row = await win.textContent('[data-testid="ks-export"]');
    if (!/cannot be restored into Ember/.test(row)) fail(`story 74: the export row must state the one-line honesty: ${row.slice(0, 200)}`);

    await win.click('[data-testid="ks-export-run"]');
    await win.waitForSelector('[data-testid="ks-export-result"]');
    const result = await win.textContent('[data-testid="ks-export-result"]');
    if (!result.includes(target)) fail(`the result line must name the export location: ${result}`);
    if (!/unchanged/.test(result)) fail(`story 77: the export result must say the knowledge base is unchanged: ${result}`);
    if (fs.statSync(target).size < 100) fail('the export file must really exist with content on disk');
    // The app reads no export JSON: the file is plain text, and the
    // screen shows no imported numbers of its own (D3).
    const head = fs.readFileSync(target, 'utf8').slice(0, 400);
    if (/^\{/.test(head.trim())) fail('the export must be a plain text file any editor can read, not JSON');
    await assertCleanScan(win, 'Keep safe (export written)');
    process.stdout.write('export OK: real bytes on disk, honesty line shown (stories 73-74)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
    fs.rmSync(path.dirname(dbPath), { recursive: true, force: true });
  }
}

/* ---------------- scenario 3: the forbidden actions ---------------- */

async function forbiddenActions() {
  process.stdout.write('--- forbidden actions: onto the knowledge base itself ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ks-e2e-forbid-'));
  const dbPath = seedKb('seed_pair');
  const hashBefore = sha256(dbPath);
  const { app } = await launchShell({ workDir, dbPath, savePath: dbPath });
  try {
    const win = await app.firstWindow();
    await gotoKeepSafe(win);
    await win.waitForSelector('[data-testid="ks-check-verdict"]');

    // Story 72: backing up ONTO the knowledge base itself must be
    // prevented — the engine refuses, the app says it in plain words.
    await win.click('[data-testid="ks-backup-run"]');
    await win.waitForSelector('[data-testid="ks-backup-error"]');
    const backupError = await win.textContent('[data-testid="ks-backup-error"]');
    if (!/refuses to write over your knowledge base/i.test(backupError)) fail(`story 72: the refusal must be in plain words: ${backupError.slice(0, 300)}`);
    if (!/unchanged/.test(backupError)) fail(`story 77: the refusal must say the file is unchanged: ${backupError.slice(0, 300)}`);
    await win.locator('[data-testid="ks-backup-error"] [data-action="show-details"]').click();
    await win.waitForSelector('[data-testid="ks-backup-error-code"]:not([hidden])');
    const backupCode = await win.textContent('[data-testid="ks-backup-error-code"]');
    if (!/BACKUP-003/.test(backupCode)) fail(`the engine's code belongs behind Details: ${backupCode}`);

    // EXPORT-002: the same story for export.
    await win.click('[data-testid="ks-export-run"]');
    await win.waitForSelector('[data-testid="ks-export-error"]');
    const exportError = await win.textContent('[data-testid="ks-export-error"]');
    if (!/knowledge base file itself/i.test(exportError)) fail(`EXPORT-002 must read in plain words: ${exportError.slice(0, 300)}`);
    await win.locator('[data-testid="ks-export-error"] [data-action="show-details"]').click();
    await win.waitForSelector('[data-testid="ks-export-error-code"]:not([hidden])');
    const exportCode = await win.textContent('[data-testid="ks-export-error-code"]');
    if (!/EXPORT-002/.test(exportCode)) fail(`the engine's export code belongs behind Details: ${exportCode}`);

    await assertCleanScan(win, 'Keep safe (refusals shown)');
    if (sha256(dbPath) !== hashBefore) fail('the hash proof: refusals must leave the live file byte-identical');
    process.stdout.write('forbidden actions OK: BACKUP-003/EXPORT-002 in plain words, the live file byte-identical (stories 72, 77)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
    fs.rmSync(path.dirname(dbPath), { recursive: true, force: true });
  }
}

/* ---------------- scenario 4: drift + reduce motion ---------------- */

async function driftAndMotion() {
  process.stdout.write('--- drift + retry + reduce motion ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ks-e2e-drift-'));
  const dbPath = seedDrift();
  const { app } = await launchShell({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await gotoKeepSafe(win);
    await win.waitForSelector('[data-testid="ks-check-verdict"]');
    const verdict = await win.textContent('[data-testid="ks-check-verdict"]');
    if (!/do not match/.test(verdict)) fail(`DRIFT must say what it is in plain words (story 75): ${verdict.slice(0, 300)}`);
    if (!/Try again/.test(verdict)) fail('DRIFT must offer Retry and name what to do next');
    const rows = await win.locator('[data-testid="ks-check-row"]').allTextContents();
    if (!rows.some((r) => /safety triggers are missing/.test(r))) fail(`the drifted line must read in plain words: ${JSON.stringify(rows)}`);
    if (verdict && !/changed nothing/.test(verdict)) fail(`the check must say it changed nothing: ${verdict.slice(0, 300)}`);

    // Retry re-runs the check (DRIFT stays DRIFT on the same file).
    await win.click('[data-testid="ks-check-retry"]');
    await win.waitForFunction(() => {
      const v = document.querySelector('[data-testid="ks-check-verdict"]');
      return v !== null && /do not match/.test(v.textContent);
    });
    await assertCleanScan(win, 'Keep safe (DRIFT state)');

    // Reduce Motion honoured: nothing animates even while redrawing.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    await win.locator('#nav button[data-job="lookup"]').click();
    await win.waitForSelector('[data-testid="lookup-pane"] [role="tab"]');
    await gotoKeepSafe(win);
    await win.waitForSelector('[data-testid="ks-check-verdict"]');
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('svg, .skel')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    process.stdout.write('drift OK: DRIFT words + Retry, Reduce Motion honoured (stories 75, 99/104)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
    fs.rmSync(path.dirname(dbPath), { recursive: true, force: true });
  }
}

/* ---------------- scenario 5: open a different (v12 backup) file ---------------- */

async function openDifferentFile() {
  process.stdout.write('--- open a different knowledge base (v12 backup, story 76) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ks-e2e-open-'));
  const currentKb = seedKb('seed_pair');
  const v12File = seedV12();
  const { app } = await launchShell({ workDir, dbPath: currentKb, useDbOverride: false, pickPath: v12File });
  try {
    const win = await app.firstWindow();
    await gotoKeepSafe(win);
    const current = await win.textContent('[data-testid="ks-open-current"]');
    if (current.trim() !== currentKb) fail(`the pane must name the current file: ${current}`);

    // Pick -> ONE confirmation naming the file and saying the current
    // file is unchanged (step file §1).
    await win.click('[data-testid="ks-open-pick"]');
    await win.waitForSelector('[data-testid="ks-open-confirm"]');
    const confirm = await win.textContent('[data-testid="ks-open-confirm"]');
    if (!confirm.includes(v12File)) fail(`the confirmation must name the chosen file: ${confirm.slice(0, 300)}`);
    if (!/stays exactly as it is/.test(confirm)) fail(`the confirmation must say the current file is unchanged: ${confirm.slice(0, 300)}`);
    await assertCleanScan(win, 'Keep safe (open-file confirmation)');

    // The v12 file passes the db-check gate (no floor for v12) and the
    // setting changes; the result names the new file and the old one.
    await win.click('[data-testid="ks-open-confirm-yes"]');
    await win.waitForSelector('[data-testid="ks-open-result"]');
    const result = await win.textContent('[data-testid="ks-open-result"]');
    if (!result.includes(v12File)) fail(`the switch result must name the new file: ${result}`);
    if (!/unchanged/.test(result)) fail(`the switch result must say the previous file is unchanged: ${result}`);

    // The app really moved: after the reload the setting says so, and
    // the health check on the opened file still reports no floor drift
    // for v12 (it opens; the first WRITE would migrate it).
    await win.click('[data-testid="ks-open-reload"]');
    await win.waitForSelector('[data-testid="keepsafe-pane"]', { timeout: 60000 }).catch(() => {});
    await gotoKeepSafe(win);
    const currentAfter = await win.textContent('[data-testid="ks-open-current"]');
    if (currentAfter.trim() !== v12File) fail(`after the switch the app must use the opened file, saw ${currentAfter}`);
    await win.waitForSelector('[data-testid="ks-check-verdict"]');
    const v12Verdict = await win.textContent('[data-testid="ks-check-verdict"]');
    if (!/No problems found/.test(v12Verdict)) fail(`a healthy v12 file must pass the check (no floor): ${v12Verdict.slice(0, 300)}`);
    const versionRow = (await win.locator('[data-testid="ks-check-row"]').allTextContents()).find((r) => /File format version 12/.test(r));
    if (!versionRow) fail('the v12 file must read as version 12, not silently migrated by a read');
    process.stdout.write('open different file OK: a v12 backup opened as the knowledge base, nothing migrated (story 76)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 6: open refused (APP-006) ---------------- */

async function openRefused() {
  process.stdout.write('--- open refused (corrupt file, APP-006) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ks-e2e-open-bad-'));
  const currentKb = seedKb('seed_pair');
  const garbage = path.join(workDir, 'garbage.db');
  fs.writeFileSync(garbage, 'this is not a knowledge base, it is a text file');
  const { app } = await launchShell({ workDir, dbPath: currentKb, useDbOverride: false, pickPath: garbage });
  try {
    const win = await app.firstWindow();
    await gotoKeepSafe(win);
    await win.click('[data-testid="ks-open-pick"]');
    await win.waitForSelector('[data-testid="ks-open-error"]');
    const shown = await win.textContent('[data-testid="ks-open-error"]');
    if (!/not a knowledge base/i.test(shown)) fail(`a garbage pick must be refused in plain words: ${shown.slice(0, 300)}`);
    const current = await win.textContent('[data-testid="ks-open-current"]');
    if (current.trim() !== currentKb) fail('a refused pick must leave the current file chosen');
    const effective = await win.evaluate(() => window.ember.getState().then((s) => s.effectiveKbPath));
    if (effective !== currentKb) fail(`the setting must not change after a refusal, saw ${effective}`);
    await assertCleanScan(win, 'Keep safe (open refused, APP-006)');
    process.stdout.write('open refused OK: APP-006 in plain words, the setting unchanged (story 76 + APP-006)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
    fs.rmSync(path.dirname(currentKb), { recursive: true, force: true });
  }
}

async function main() {
  await checkAndBackup();
  await exportFlow();
  await forbiddenActions();
  await driftAndMotion();
  await openDifferentFile();
  await openRefused();
  process.stdout.write('e2e keep-safe OK: all six scenarios green (real ember, real temp knowledge bases, no AI touched)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e keep-safe FAILED: ${err.message}\n`);
  process.exit(1);
});

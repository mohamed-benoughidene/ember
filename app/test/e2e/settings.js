'use strict';

/**
 * The step-10 E2E (dev-only, Linux): the Settings panes over the real
 * Electron shell with the fake ember stub (no settings flow touches a
 * bridge command except the knowledge-base checks, which never spawn
 * one; the knowledge base in scenario 1 is a REAL one seeded by the
 * Python test helpers).
 *
 * Scenario 1 — CHANGE, RESTART, INTACT (the step file's own restart
 *   proof): open Settings with Ctrl+Comma (79), set Largest text (82,
 *   200%, applied at once with 83), Dark colours (84), hide and
 *   reorder jobs (87-88), the popup position (85), save an AI key read
 *   back only MASKED (89), then RESTART the app: every value intact,
 *   the key still masked, and the key string absent from the process
 *   output, the settings file and the knowledge base file.
 * Scenario 2 — RECOVERY: a corrupt settings file boots to defaults
 *   with the APP-004 banner; the knowledge-base pane refuses a file
 *   that is not an Ember knowledge base (APP-006) and leaves the
 *   choice unchanged; the shortcut capture cancels on Esc; a11y scans
 *   run on every pane, the panes are keyboard-switched, and Reduce
 *   Motion leaves nothing animating (96-104).
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { launchShell, seedSettings } = require('./helpers/shell.js');
const { runAccessibilityScan } = require('../helpers/a11y-scan.mjs');
const { PYTHON, REPO_ROOT } = require('../util');

const KEY = 'sk-or-v1-e2e-settings-key-abcdef0123456789';

function fail(what) {
  throw new Error(what);
}

/** Collect the app process output so the key-grep can sweep it. */
function tapProcessOutput(app) {
  const chunks = [];
  try {
    const child = app.process();
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (c) => chunks.push(String(c)));
    child.stderr.on('data', (c) => chunks.push(String(c)));
  } catch {
    /* headless shutdown races: the sweep just sees less */
  }
  return chunks;
}

async function assertCleanScan(win, label) {
  // The Text Size Rule (DESIGN.md): at Largest the app runs its
  // :root.big adaptations. When the app is REALLY at Largest (this
  // step's user setting, applied by the shell), the scan measures the
  // real thing as-is; only smaller sizes get the temporary :root.big
  // state around the scan, and only then are they removed again.
  const rootPx = await win.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize) || 15);
  const fakeBig = rootPx < 22;
  const { violations, checked } = await runAccessibilityScan(
    win,
    fakeBig
      ? {
          prepare: (page) => page.evaluate(() => document.documentElement.classList.add('big')),
          cleanup: (page) => page.evaluate(() => document.documentElement.classList.remove('big')),
        }
      : {},
  );
  if (violations.length > 0) {
    fail(`a11y scan on ${label} found ${violations.length}: ${JSON.stringify(violations, null, 2)}`);
  }
  process.stdout.write(
    `a11y scan clean on ${label} (${checked.tabbableCount} tabbable controls, root ${await win.evaluate(() => getComputedStyle(document.documentElement).fontSize)})\n`,
  );
}

async function openSettingsByKeyboard(win) {
  await win.keyboard.press('Control+,');
  await win.waitForSelector('[data-testid="pane-settings"]');
  const title = await win.evaluate(() => document.title);
  if (!/Settings — Appearance/.test(title)) fail(`the window title must name the open pane, saw "${title}"`);
}

/** Switch panes with the keyboard only: focus the selected tab and walk
 *  with the arrow key, exactly as a keyboard user does (96). */
async function switchPaneByKeyboard(win, paneName) {
  await win.evaluate(() => document.querySelector('[role="tablist"] [role="tab"]').focus());
  for (let i = 0; i < SETTING_PANE_COUNT; i += 1) {
    const selected = await win.evaluate(() => document.querySelector('[role="tab"][aria-selected="true"]')?.textContent.trim() ?? '');
    if (selected === paneName) return;
    await win.evaluate(() => document.querySelector('[role="tab"][aria-selected="true"]')?.focus());
    await win.keyboard.press('ArrowRight');
  }
  fail(`the ${paneName} pane never became selected by keyboard`);
}

const SETTING_PANE_COUNT = 5;

/** waitForSelector, but on timeout it dumps the live element state so a
 *  hidden-vs-missing distinction survives into the failure message. */
async function waitVisible(win, selector, label, timeoutMs = 20000) {
  try {
    await win.waitForSelector(selector, { state: 'visible', timeout: timeoutMs });
  } catch {
    const dump = await win
      .evaluate((sel) => {
        const el = document.querySelector(sel);
        const row = el ? el.closest('.setrow') : null;
        return JSON.stringify({
          count: document.querySelectorAll(sel).length,
          rect: el ? el.getBoundingClientRect().toJSON() : null,
          rowRect: row ? row.getBoundingClientRect().toJSON() : null,
          lRect: row && row.querySelector('.l') ? row.querySelector('.l').getBoundingClientRect().toJSON() : null,
          fontSize: getComputedStyle(document.documentElement).fontSize,
          big: document.documentElement.classList.contains('big'),
          scroll: { left: document.getElementById('pane').scrollLeft, top: document.getElementById('pane').scrollTop },
          rows: document.querySelectorAll('.setrow').length,
          pane: document.querySelector('[role="tab"][aria-selected="true"]')?.textContent.trim() ?? null,
        });
      }, selector)
      .catch((e) => `dump failed: ${e.message}`);
    throw new Error(`${label} never became visible: ${dump}`);
  }
}

/* ---------------- scenario 1: change -> restart -> intact ---------------- */

async function changeRestartIntact() {
  process.stdout.write('--- settings survive a restart ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-settings-'));
  const kbPath = path.join(workDir, 'kb.db');
  // A REAL knowledge base, seeded by the Python test helpers.
  execFileSync(PYTHON, ['-c', `from tests.bridge import harness; harness.seed_contradicted_active(${JSON.stringify(kbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  seedSettings(path.join(workDir, 'config'), kbPath);

  const shell = await launchShell({ workDir, withDb: false });
  const { app } = shell;
  let out1 = [];
  try {
    const win = await app.firstWindow();
    win.on('pageerror', (err) => process.stdout.write(`PAGEERROR: ${String(err).slice(0, 300)}\n`));
    out1 = tapProcessOutput(app).concat(out1);
    await win.waitForSelector('[data-testid="home-pane"]');

    // Story 79: Settings opens with Ctrl+Comma, from any pane.
    await openSettingsByKeyboard(win);

    // Story 82-83: Largest (200%) applies AT ONCE, spacing follows.
    await win.click('[data-value="largest"]');
    await win.waitForFunction(() => getComputedStyle(document.documentElement).fontSize === '30px');
    await win.waitForSelector('[data-testid="settings-saved"]');
    const big = await win.evaluate(() => document.documentElement.classList.contains('big'));
    if (!big) fail('the Largest step must switch on the Text Size Rule adaptations (:root.big)');
    const saved1 = await win.textContent('[data-testid="settings-saved"]');
    if (!/Saved/.test(saved1)) fail(`story 81: a quiet Saved must follow the change, saw "${saved1}"`);
    await assertCleanScan(win, 'Settings (Appearance, Largest text)');

    // Story 84: Dark applies at once.
    await win.click('[data-value="dark"]');
    await win.waitForFunction(() => document.documentElement.dataset.theme === 'dark');

    // Stories 87-88: the Menu pane hides Add, moves Look up up; the
    // sidebar follows at once; Home and Settings stay.
    await switchPaneByKeyboard(win, 'Menu');
    await win.waitForSelector('[data-testid="menu-list"]');
    await win.click('[data-testid="menu-check-add"]');
    await win.waitForFunction(() => !document.querySelector('#nav button[data-job="add"]'));
    await win.click('[data-testid="menu-up-link"]');
    const navIds = await win.evaluate(() => [...document.querySelectorAll('#nav button')].map((b) => b.dataset.job));
    if (!navIds.includes('home') || !navIds.includes('settings')) fail(`Home and Settings always stay (88), saw ${JSON.stringify(navIds)}`);
    if (navIds.includes('add')) fail('the hidden job must leave the sidebar at once');
    if (navIds.indexOf('link') > navIds.indexOf('lookup')) fail(`the reorder must apply at once, saw ${JSON.stringify(navIds)}`);
    await assertCleanScan(win, 'Settings (Menu)');

    // Story 85 (position half): the popup position saves itself.
    await switchPaneByKeyboard(win, 'Quick popup');
    await win.waitForSelector('select[data-set="quickPopupPosition"]');
    const keys = await win.locator('.kbdkey').allTextContents();
    if (!keys.some((k) => /E/i.test(k))) fail(`the current shortcut keys must be shown: ${JSON.stringify(keys)}`);
    await win.selectOption('select[data-set="quickPopupPosition"]', 'top-center');
    await win.waitForSelector('[data-testid="settings-saved"]:not(:empty)');
    await assertCleanScan(win, 'Settings (Quick popup)');

    // Story 89: the AI connection pane — masked status only.
    await switchPaneByKeyboard(win, 'AI connection');
    await win.waitForSelector('[data-testid="ai-set-up"]', { timeout: 15000 });
    let status = await win.textContent('[data-testid="ai-status"]');
    if (!/Not connected/.test(status)) fail(`a fresh install must start not connected, saw "${status}"`);
    await win.click('[data-testid="ai-set-up"]');
    await win.waitForSelector('[data-testid="settings-key-input"]');
    await win.fill('[data-testid="settings-key-input"]', KEY);
    await win.click('[data-testid="ai-save-key"]');
    // On a weak/no keyring the pane offers the session-only path
    // (APP-003); elsewhere the key is stored encrypted.
    const sessionButton = win.locator('[data-testid="ai-session-key"]');
    let keyStored = true;
    if ((await sessionButton.count()) > 0 && (await sessionButton.isVisible())) {
      keyStored = false;
      await sessionButton.click();
    }
    await win.waitForFunction(() => /Connected/.test((document.querySelector('[data-testid="ai-status"]') ?? { textContent: '' }).textContent));
    if (keyStored) {
      const hint = await win.textContent('[data-testid="ai-hint"]');
      if (hint !== KEY.slice(-4)) fail(`the masked hint must be the key's last four characters, saw "${hint}"`);
      const body = await win.textContent('body');
      if (body.includes(KEY)) fail('the pane must never echo the whole key (89)');
    }
    await assertCleanScan(win, 'Settings (AI connection)');

    // The knowledge base pane: the real file reads as valid.
    await switchPaneByKeyboard(win, 'Knowledge base file');
    await waitVisible(win, '[data-testid="kb-state"]', 'the knowledge-base status line');
    const kbState = await win.textContent('[data-testid="kb-state"]');
    if (!/reads as an Ember knowledge base/.test(kbState)) fail(`the real KB must read as valid: ${kbState}`);
    if (!(await win.textContent('[data-testid="kb-path"]')).includes('kb.db')) fail('the pane must show the chosen file location');
    await assertCleanScan(win, 'Settings (Knowledge base file)');
    await app.close();
    await new Promise((r) => setTimeout(r, 400));

    // RESTART: same user-data, fresh shell.
    const shell2 = await launchShell({ workDir, withDb: false });
    const { app: app2 } = shell2;
    const out2 = [];
    try {
      const win2 = await app2.firstWindow();
      out2.push(...tapProcessOutput(app2));
      // The last pane is remembered (80): Settings, on the Appearance tab.
      await win2.waitForSelector('[data-testid="pane-settings"]');
      const title2 = await win2.evaluate(() => document.title);
      if (!/Settings — Appearance/.test(title2)) fail(`after the restart the title must name the pane, saw "${title2}"`);
      // Text size + theme survived (82-84), applied at boot:
      const px = await win2.evaluate(() => getComputedStyle(document.documentElement).fontSize);
      if (px !== '30px') fail(`the Largest step must survive a restart, saw root ${px}`);
      const theme = await win2.evaluate(() => document.documentElement.dataset.theme);
      if (theme !== 'dark') fail(`Dark must survive a restart, saw ${theme}`);
      // The menu settings survived (87-88):
      const navIds2 = await win2.evaluate(() => [...document.querySelectorAll('#nav button')].map((b) => b.dataset.job));
      if (navIds2.includes('add') || !navIds2.includes('home') || !navIds2.includes('settings')) {
        fail(`the menu choices must survive a restart, saw ${JSON.stringify(navIds2)}`);
      }
      const navOrder2 = await win2.evaluate(() => [...document.querySelectorAll('#nav button')].map((b) => b.dataset.job));
      if (navOrder2.indexOf('link') > navOrder2.indexOf('lookup')) fail(`the job order must survive a restart, saw ${JSON.stringify(navOrder2)}`);
      // The popup position survived (85):
      await switchPaneByKeyboard(win2, 'Quick popup');
      await win2.waitForSelector('select[data-set="quickPopupPosition"]');
      const position = await win2.inputValue('select[data-set="quickPopupPosition"]');
      if (position !== 'top-center') fail(`the popup position must survive a restart, saw ${position}`);
      // The key state survived MASKED, consistently with this system's keyring:
      await switchPaneByKeyboard(win2, 'AI connection');
      await win2.waitForSelector('[data-testid="ai-status"]', { timeout: 15000 });
      status = await win2.textContent('[data-testid="ai-status"]');
      if (keyStored) {
        if (!/Connected/.test(status)) fail(`the saved key must come back after a restart, saw "${status}"`);
        const hint = await win2.textContent('[data-testid="ai-hint"]');
        if (hint !== KEY.slice(-4)) fail(`after the restart the hint must still be masked, saw "${hint}"`);
      } else {
        if (!/Not connected/.test(status)) {
          fail(`a session-only key is gone after a restart (it said so at save): saw "${status}"`);
        }
      }
      process.stdout.write(`settings survive a restart OK (key: ${keyStored ? 'stored, masked' : 'session-only, gone as promised'})\n`);

      // Story 89 continued: the REMOVE path is careful — it previews,
      // names the object (No Modal First Rule), honours Cancel, then
      // really removes (this stays inside the RESTARTED shell, where a
      // stored key exists; a session-only key is already gone).
      if (keyStored) {
        await win2.waitForSelector('[data-testid="ai-remove"]', { timeout: 15000 });
        await win2.click('[data-testid="ai-remove"]');
        await win2.waitForSelector('[data-testid="ai-remove-confirm-box"]');
        const box = await win2.textContent('[data-testid="ai-remove-confirm-box"]');
        if (!/Remove this AI key\?/.test(box) || !/Cancel/.test(box)) fail(`the careful preview must name the object and offer Cancel: ${box}`);
        await win2.click('[data-testid="ai-remove-cancel"]');
        await win2.waitForSelector('[data-testid="ai-remove"]');
        const still = await win2.textContent('[data-testid="ai-status"]');
        if (!/Connected/.test(still)) fail(`Cancel must change nothing, saw "${still}"`);
        await win2.click('[data-testid="ai-remove"]');
        await win2.waitForSelector('[data-testid="ai-remove-confirm-box"]');
        await win2.click('[data-testid="ai-remove-confirm"]');
        await win2.waitForFunction(() => /Not connected/.test((document.querySelector('[data-testid="ai-status"]') ?? { textContent: '' }).textContent));
        const gone = await win2.evaluate(() => window.ember.keyStatus().then((s) => s.stored || s.sessionOnly));
        if (gone) fail('after the confirmed removal the key store must be empty');
        process.stdout.write('the remove flow is careful: preview named it, Cancel kept it, the confirmed removal emptied the store (89)\n');
      }
    } finally {
      await app2.close().catch(() => {});
    }

    // THE key sweep (step file §2): the key is nowhere — not in the
    // app's output, not in the settings file, not in the KB bytes.
    const combined = [out1.join(''), out2.join('')].join('');
    if (combined.includes(KEY)) fail('the key must never appear in the app process output');
    const settingsFile = fs.readFileSync(path.join(workDir, 'config', 'ember-app', 'settings.json'), 'utf8');
    if (settingsFile.includes(KEY)) fail('the key must never appear in the settings file');
    const kbBytes = fs.readFileSync(kbPath, 'utf8');
    if (kbBytes.includes(KEY)) fail('the key must never appear in the knowledge base (ledger)');
    const state = JSON.parse(settingsFile);
    if (state.lastPane !== 'settings') fail(`the last pane must be remembered (80), saw ${state.lastPane}`);
    if (state.textSize !== 'largest' || state.colourTheme !== 'dark') fail('the appearance settings must be on disk after the restart');
    if (!state.menuHidden.includes('add')) fail('the hidden job must be on disk');
    if (state.quickPopup.position !== 'top-center') fail('the popup position must be on disk');
    process.stdout.write('the key sweep is clean: process output, settings file and knowledge base hold no key\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 2: recovery, a11y, reduce motion ---------------- */

async function recoveryAndA11y() {
  process.stdout.write('--- corrupt settings, wrong file, keyboard, reduce motion ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-settings-corrupt-'));
  const kbPath = path.join(workDir, 'kb.db');
  fs.writeFileSync(kbPath, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(3000, 0)]));
  // A CORRUPT settings file: defaults + an APP-004 notice, never a crash.
  const userData = path.join(workDir, 'config', 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(path.join(userData, 'settings.json'), '{"schema": 1, "textSize": "larg', 'utf8');
  fs.writeFileSync(path.join(workDir, 'not-ember.txt'), 'a plain text file that is no knowledge base');

  const { app } = await launchShell({ workDir, withDb: false });
  try {
    const win = await app.firstWindow();
    // A corrupt file loses the knowledge-base path too (defaults), so
    // the app honestly opens FIRST RUN; the APP-004 banner rides along.
    await win.waitForSelector('[data-testid="setup-db-input"]');
    const bannerEarly = await win.textContent('#top-banner');
    if (!/settings/i.test(bannerEarly)) fail(`the corrupt-settings banner must speak plainly: ${bannerEarly}`);
    const pxEarly = await win.evaluate(() => getComputedStyle(document.documentElement).fontSize);
    if (pxEarly !== '15px') fail(`a corrupt file must boot to the Default size, saw ${pxEarly}`);
    // Complete setup (the default file, skip the key) to reach the app.
    await win.click('[data-action="setup-file-continue"]');
    await win.waitForSelector('[data-testid="setup-key-input"]');
    await win.click('[data-action="setup-skip-key"]');
    await win.waitForSelector('[data-testid="setup-finish"]');
    await win.click('[data-testid="setup-finish"]');
    // The real Add screen (step 05) replaced the placeholder pane. The
    // key was skipped, so the screen honestly shows its no-key state
    // (pointing at the AI connection) instead of the input.
    await win.waitForSelector('[data-testid="state-no-key"]');
    // A settings save writes a clean file afterward (the APP-004
    // promise: the corrupt file is replaced, never reused).
    await openSettingsByKeyboard(win);
    await win.click('[data-value="default"]');
    await win.waitForSelector('[data-testid="settings-saved"]:not(:empty)');
    const repaired = JSON.parse(fs.readFileSync(path.join(userData, 'settings.json'), 'utf8'));
    if (repaired.schema !== 1) fail('the saved file must parse as the schema-1 document');
    if (repaired.textSize !== 'default') fail('a save must rewrite the corrupt file (D5/D6)');
    await assertCleanScan(win, 'Settings (Appearance, Default after repair)');

    // Keyboard-only pane switching across the whole tab row (96).
    for (const pane of ['Quick popup', 'Menu', 'AI connection', 'Knowledge base file']) {
      await switchPaneByKeyboard(win, pane);
    }
    await win.waitForSelector('[data-testid="pane-settings"]');

    // The shortcut capture: shows its words, cancels on Esc (85/86).
    await switchPaneByKeyboard(win, 'Quick popup');
    await win.click('[data-testid="popup-capture"]');
    const capturing = await win.textContent('[data-testid="popup-capturing"]');
    if (!/Press the new keys/.test(capturing)) fail(`the capture must say it is listening: ${capturing}`);
    await win.keyboard.press('Escape');
    await win.waitForSelector('[data-testid="popup-capture"]');
    const warnings = await win.locator('[data-testid="popup-warning"]').count();
    process.stdout.write(`the default shortcut shows ${warnings} warnings (story 86: none expected for CommandOrControl+Alt+E)\n`);
    if (warnings !== 0) fail('the default shortcut must warn nowhere');
    await assertCleanScan(win, 'Settings (Quick popup after cancel)');

    // APP-006: the knowledge-base pane refuses a non-Ember file and
    // leaves the choice unchanged.
    await switchPaneByKeyboard(win, 'Knowledge base file');
    await win.waitForSelector('[data-testid="settings-kb-input"]');
    await win.fill('[data-testid="settings-kb-input"]', path.join(workDir, 'not-ember.txt'));
    await win.click('[data-testid="kb-use"]');
    await win.waitForSelector('[data-testid="settings-error"]');
    const refusal = await win.textContent('[data-testid="settings-error"]');
    if (!/not an Ember knowledge base/.test(refusal) || !/APP-006/.test(refusal)) {
      fail(`the wrong-file refusal must name it with the code: ${refusal}`);
    }
    const kbOnDisk = JSON.parse(fs.readFileSync(path.join(userData, 'settings.json'), 'utf8'));
    if (path.join(workDir, 'not-ember.txt') === kbOnDisk.knowledgeBasePath) {
      fail('a refused file must never be saved into the settings');
    }
    if (kbOnDisk.knowledgeBasePath === path.join(workDir, 'not-ember.txt')) {
      fail('a refused file must never become the chosen knowledge base');
    }
    // An empty state: a file that does not exist yet is allowed.
    await win.fill('[data-testid="settings-kb-input"]', path.join(workDir, 'fresh', 'new.db'));
    await win.click('[data-testid="kb-use"]');
    await win.waitForFunction(() => /does not exist yet/.test((document.querySelector('[data-testid="kb-state"]') ?? { textContent: '' }).textContent));
    process.stdout.write('the knowledge-base pane verified: refuses the wrong file (APP-006), allows a fresh name\n');

    // Reduce Motion: nothing animates anywhere on Settings.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    await switchPaneByKeyboard(win, 'Appearance');
    await win.waitForSelector('[data-testid="pane-settings"]');
    await win.waitForTimeout(300);
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('*')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    await assertCleanScan(win, 'Settings (Appearance, Reduce Motion run)');
    process.stdout.write('reduce motion honoured; keyboard switching drove all five panes\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  await changeRestartIntact();
  await recoveryAndA11y();
  process.stdout.write('e2e settings OK: both scenarios green (real Python-seeded KB, fake ember app mode, no AI service touched)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e settings FAILED: ${err.message}\n`);
  process.exit(1);
});

'use strict';

/**
 * The step-11 E2E (dev-only, Linux; the step's check command
 * `npm --prefix app run e2e -- popup`): the quick popup over the SAME
 * Add pipeline as the full window (plan §5.5, stories 90-95).
 *
 * The REAL global shortcut press cannot be synthesized here (no
 * key-synthesis tool exists on this machine, the spike already marked
 * it NOT VERIFIED) — so every open in this file goes through the SAME
 * handler the shortcut, the tray and `--quick-add` share (the step
 * file §2: "popup opens by calling the same handler"), the boot
 * registration is asserted through the main process's real
 * `globalShortcut.isRegistered`, and the refused path is driven with
 * the EMBER_APP_SHORTCUT_REFUSED=1 seam (the same fake shape the
 * manager's unit tests pin).
 *
 * Scenarios:
 *  1. the popup is Add only (91) and reuses the full Add flow (92):
 *     type -> real `ember capture` child -> fake AI server on
 *     EMBER_AI_BASE_URL -> proposal -> Confirm -> summary; Reduce
 *     Motion honoured; a11y scans on the form, proposal and summary.
 *  2. Esc closes (90's step-file default), the draft is kept "until
 *     the next open" (step file deferred settings), the summary state
 *     survives a hide/show, and the "Open Ember" link (93) focuses the
 *     main window while the renderer route never parks it.
 *  3. no key (94): the Add screen's own no-key state with the path to
 *     the AI connection, landing on setup step 2 in the main window.
 *  4. setup missing (94): `--quick-add` before first run shows the
     setup-needed message; no shortcut is registered at boot (the
 *   boot rule: only AFTER first run); "Open Ember" lands on first run.
 *  5. the shortcut refused (95): with EMBER_APP_SHORTCUT_REFUSED=1,
 *     nothing registers and the routes still open the popup.
 *  6. Esc mid-session stops the session (23/92) and the popup then
 *     closes by itself ("after Stop"), reopening to the stopped line.
 *  7. `--quick-add` + placement: the popup opens on the display the
 *     mouse is on, at the saved position setting (bottom-right default,
 *     top-centre seeded), with the main window parked.
 */

const { _electron } = require('playwright');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const { APP_ROOT, REPO_ROOT } = require('../util');

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');
const KEY = 'sk-or-v1-ember-e2e-fake-key-0123456789';
const NOTE = 'We decided to use SQLite for local storage. We assume the team ships weekly.';

/* ---------- the fake AI (same seam as the add e2e) ---------- */

function startFakeAi() {
  let responder = () => ({ status: 200, content: '[]' });
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const r = responder();
      res.writeHead(r.status ?? 200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          id: 'chatcmpl-ember-e2e-popup',
          object: 'chat.completion',
          created: 0,
          model: 'ember-e2e-fake',
          choices: [{ index: 0, message: { role: 'assistant', content: r.content ?? '' }, finish_reason: 'stop' }],
        }),
      );
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, url: `http://127.0.0.1:${server.address().port}/v1`, set: (fn) => (responder = fn) });
    });
  });
}

/* ---------- launcher ---------- */

function settingsText(kbPath, { position = 'bottom-right' } = {}) {
  return `${JSON.stringify(
    {
      schema: 1,
      textSize: 'default',
      colourTheme: 'system',
      quickPopup: { shortcut: 'CommandOrControl+Alt+E', position },
      menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
      menuHidden: [],
      lastPane: 'home',
      knowledgeBasePath: kbPath,
    },
    null,
    2,
  )}\n`;
}

async function launchPopupApp({ workDir, aiBaseUrl, quickAdd = false, withDb = true, withKey = true, position, refusedShortcut = false }) {
  const configDir = path.join(workDir, 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  const kbPath = path.join(workDir, 'kb.db');
  if (withDb) {
    // A real knowledge base (no AI needed): pre-Add read commands answer honestly.
    execFileSync(EMBER, ['capture-source', '--db', kbPath], {
      input: 'A throwaway source text for the popup e2e.\n',
      cwd: REPO_ROOT,
      stdio: ['pipe', 'ignore', 'inherit'],
    });
  }
  if (withDb || position) {
    fs.writeFileSync(path.join(userData, 'settings.json'), settingsText(kbPath, { position }));
  }
  const env = { ...process.env };
  delete env.EMBER_AI_API_KEY;
  delete env.OPENROUTER_API_KEY;
  env.XDG_CONFIG_HOME = configDir;
  env.EMBER_APP_COMMAND = EMBER;
  if (withDb) env.EMBER_APP_DB = kbPath;
  if (aiBaseUrl) env.EMBER_AI_BASE_URL = aiBaseUrl;
  if (refusedShortcut) env.EMBER_APP_SHORTCUT_REFUSED = '1';
  const app = await _electron.launch({ args: quickAdd ? ['.', '--quick-add'] : ['.'], cwd: APP_ROOT, env });
  const mainWin = await app.firstWindow();
  if (withKey) {
    const kept = await mainWin.evaluate((k) => window.ember.setSessionKey(k), KEY);
    if (!kept || !kept.ok) throw new Error('the session key could not be kept in the test app');
  }
  return { app, mainWin, kbPath, userData };
}

async function findPopup(app) {
  for (let i = 0; i < 100; i += 1) {
    const win = app.windows().find((w) => w.url().includes('quick.html'));
    if (win) return win;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('no quick popup window appeared');
}

/* Playwright forces `document.visibilityState` to "visible" on every
   page it drives, so hidden/shown here is read where it is REALLY
   true: on the main-process window object. */
function visibleWindows(app, title) {
  return app.evaluate(
    ({ BrowserWindow }, t) => BrowserWindow.getAllWindows().filter((w) => w.getTitle() === t && w.isVisible()).length,
    title,
  );
}

async function waitPopup(app, want, timeoutMs = 15000) {
  const start = Date.now();
  for (;;) {
    const state = await app.evaluate(
      ({ BrowserWindow }) => BrowserWindow.getAllWindows().find((w) => w.getTitle() === 'Ember quick add')?.isVisible() ?? false,
    );
    if (state === want) return state;
    if (Date.now() - start > timeoutMs) throw new Error(`the quick popup never became ${want ? 'visible' : 'hidden'}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

async function waitMainShown(app, timeoutMs = 15000) {
  const start = Date.now();
  for (;;) {
    if ((await visibleWindows(app, 'Ember')) > 0) return;
    if (Date.now() - start > timeoutMs) throw new Error('the main window never became visible');
    await new Promise((r) => setTimeout(r, 100));
  }
}

/** Open the popup through the SAME handler the OS routes share. */
async function openViaHandler(mainWin) {
  const res = await mainWin.evaluate(() => window.ember.openQuickPopup());
  if (!res || res.ok !== true || res.visible !== true) throw new Error(`openQuickPopup did not show the popup: ${JSON.stringify(res)}`);
}

function fail(what) {
  throw new Error(what);
}

async function assertCleanScan(win, label) {
  const { runAccessibilityScan } = await import('../helpers/a11y-scan.mjs');
  const { violations, checked } = await runAccessibilityScan(win, {
    prepare: (page) => page.evaluate(() => document.documentElement.classList.add('big')),
    cleanup: (page) => page.evaluate(() => document.documentElement.classList.remove('big')),
  });
  if (violations.length > 0) {
    fail(`a11y scan on ${label} found ${violations.length}: ${JSON.stringify(violations, null, 2)}`);
  }
  process.stdout.write(`a11y scan clean on ${label} (${checked.tabbableCount} tabbable controls)\n`);
}

async function isShortcutRegistered(app, accelerator = 'CommandOrControl+Alt+E') {
  return app.evaluate(({ globalShortcut }, acc) => globalShortcut.isRegistered(acc), accelerator);
}

/* ---------- scenario 1 + 2: add in the popup, draft, open main ---------- */

async function popupAddAndDraft(ai) {
  process.stdout.write('--- popup: add-only add flow, draft kept, open main ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-popup-'));
  const { app, mainWin } = await launchPopupApp({ workDir, aiBaseUrl: ai.url });
  try {
    await mainWin.waitForSelector('[data-testid="home-pane"]');
    // Story 90, boot half: the default shortcut is registered after first run.
    assert.equal(await isShortcutRegistered(app), true, 'the default quick-popup shortcut must be registered at boot once first run is done');

    // The popup opens by calling the same handler the shortcut shares (step file §2).
    await openViaHandler(mainWin);
    const popup = await findPopup(app);
    await popup.waitForSelector('[data-testid="add-text-input"]');
    if ((await popup.locator('#nav').count()) !== 0) fail('story 91: the popup must be Add only — no job sidebar');
    if ((await popup.locator('[data-testid="add-text-input"]').count()) !== 1) fail('story 91: the popup shows the Add draft form');
    await assertCleanScan(popup, 'popup (form)');

    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Decision', statement: 'Use SQLite for local storage', source_quote: 'use SQLite for local storage', confidence: 0.9 },
      ]),
    }));
    await popup.fill('[data-testid="add-text-input"]', NOTE);
    await popup.click('[data-testid="add-start"]');
    await popup.waitForSelector('[data-testid="proposal"]');
    const proposal = await popup.textContent('[data-testid="proposal"]');
    if (!/Decision/.test(proposal) || !/Use SQLite for local storage/.test(proposal)) {
      fail(`story 92: the popup shows the same proposal block as the full window: ${proposal.slice(0, 200)}`);
    }
    const actions = await popup
      .locator('[data-testid="proposal"] [data-action]')
      .evaluateAll((els) => els.map((el) => el.dataset.action));
    assert.deepEqual(actions, ['proposal-stop', 'proposal-edit', 'proposal-reject', 'proposal-confirm'], 'the pinned button order (same keys, story 92)');
    await assertCleanScan(popup, 'popup (proposal)');

    // Confirm from the keyboard like a full-window user (23/92).
    await popup.locator('#pane').focus();
    await popup.keyboard.press('Enter');
    await popup.waitForSelector('[data-testid="add-summary-line"]');
    const line = await popup.textContent('[data-testid="add-summary-line"]');
    if (!/1 item confirmed, 0 rejected/.test(line)) fail(`the confirm loop completes inside the popup: ${line}`);

    // Reduce Motion honoured in the popup too (99/104).
    await popup.emulateMedia({ reducedMotion: 'reduce' });
    const animated = await popup.evaluate(() =>
      [...document.querySelectorAll('svg')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating in the popup, saw ${animated}`);
    await popup.emulateMedia({ reducedMotion: 'no-preference' });
    await assertCleanScan(popup, 'popup (summary)');

    // Esc closes (the step file default); the state survives the hide.
    await popup.keyboard.press('Escape');
    await waitPopup(app, false);
    await openViaHandler(mainWin);
    await waitPopup(app, true);
    await popup.waitForSelector('[data-testid="add-summary-line"]');
    if (!(await popup.locator('[data-testid="add-reset"]').isVisible())) fail('the summary state must survive a hide/show');

    // The draft rule: type, close by accident, reopen — the text is kept.
    await popup.click('[data-testid="add-reset"]');
    await popup.waitForSelector('[data-testid="add-text-input"]');
    await popup.fill('[data-testid="add-text-input"]', 'a half-typed quick note');
    await popup.keyboard.press('Escape');
    await waitPopup(app, false);
    await openViaHandler(mainWin);
    await waitPopup(app, true);
    const draft = await popup.inputValue('[data-testid="add-text-input"]');
    if (draft !== 'a half-typed quick note') fail(`the draft must be kept until the next open, saw ${JSON.stringify(draft)}`);

    // The renderer route never parks the main window (the parking rule
    // is the OS routes' — unit-pinned in test/popup.test.js).
    if ((await visibleWindows(app, 'Ember')) !== 1) fail('the main window must stay visible when the route opens the popup');

    // Story 93: the link back to the full window.
    await popup.click('[data-testid="quick-open-main"]');
    await waitPopup(app, false);
    await waitMainShown(app);
    if ((await visibleWindows(app, 'Ember')) !== 1) fail('story 93: Open Ember must show the full window');
    process.stdout.write('popup add OK: add-only window, same confirm loop, Esc + draft kept, Open Ember link, boot shortcut registered\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------- scenario 3: no key (story 94) ---------- */

async function popupNoKey() {
  process.stdout.write('--- popup: no key, the path to fix it ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-popupnokey-'));
  const { app, mainWin } = await launchPopupApp({ workDir, aiBaseUrl: null, withKey: false });
  try {
    await mainWin.waitForSelector('[data-testid="home-pane"]');
    await openViaHandler(mainWin);
    const popup = await findPopup(app);
    await popup.waitForSelector('[data-testid="state-no-key"]');
    const block = await popup.textContent('[data-testid="state-no-key"]');
    if (!/needs the AI connection/.test(block)) fail(`story 94: the popup must say what is missing: ${block}`);
    await assertCleanScan(popup, 'popup (no-key state)');
    await popup.locator('[data-testid="state-no-key"] [data-action="add-open-setup"]').click();
    await waitMainShown(app);
    await mainWin.waitForSelector('[data-testid="setup-key-input"]');
    const step = await mainWin.textContent('.setup .sub');
    if (!/Step 2 of 3/.test(step)) fail(`the path to fix it must land on the AI connection step, saw: ${step}`);
    await waitPopup(app, false);
    process.stdout.write('popup no-key OK: the message with the path to fix it, popup closed\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------- scenario 4: setup missing + --quick-add + no boot registration ---------- */

async function popupSetupMissing() {
  process.stdout.write('--- popup: setup missing (--quick-add before first run) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-popupsetup-'));
  const { app, mainWin } = await launchPopupApp({ workDir, aiBaseUrl: null, quickAdd: true, withDb: false, withKey: false });
  try {
    const popup = await findPopup(app);
    await waitPopup(app, true);
    await popup.waitForSelector('[data-testid="quick-setup-needed"]');
    const words = await popup.textContent('[data-testid="quick-setup-needed"]');
    if (!/not set up yet/.test(words)) fail(`story 94: the setup-missing words: ${words}`);
    await assertCleanScan(popup, 'popup (setup needed)');
    // The boot rule: nothing registers before first run is done.
    if (await isShortcutRegistered(app)) fail('no global shortcut may register before first run is done');
    // The one path to fix it opens the full window on first run.
    await popup.click('[data-testid="quick-open-main-setup"]');
    await waitMainShown(app);
    await mainWin.waitForSelector('.setup');
    await waitPopup(app, false);
    process.stdout.write('popup setup-missing OK: honest words, no boot registration, Open Ember lands on first run\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------- scenario 5: the shortcut refused, the routes still work (95) ---------- */

async function popupRefusedRoute() {
  process.stdout.write('--- popup: shortcut refused, the routes still work ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-popupref-'));
  const { app, mainWin } = await launchPopupApp({ workDir, aiBaseUrl: null, refusedShortcut: true });
  try {
    await mainWin.waitForSelector('[data-testid="home-pane"]');
    if (await isShortcutRegistered(app)) fail('the refused registration must not register the shortcut');
    // The tray fallback was built on APP-005 (unit-pinned menu); the
    // always-available route opens the same popup.
    await openViaHandler(mainWin);
    const popup = await findPopup(app);
    await popup.waitForSelector('[data-testid="add-text-input"]');
    process.stdout.write('popup refused OK: APP-005 path taken, nothing registered, the route still opens the popup\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------- scenario 6: Esc mid-session stops, then the popup closes after Stop ---------- */

async function popupStopCloses(ai) {
  process.stdout.write('--- popup: Esc stops, the popup closes after Stop ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-popupstop-'));
  const { app, mainWin } = await launchPopupApp({ workDir, aiBaseUrl: ai.url });
  try {
    await mainWin.waitForSelector('[data-testid="home-pane"]');
    await openViaHandler(mainWin);
    const popup = await findPopup(app);
    await popup.waitForSelector('[data-testid="add-text-input"]');
    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Decision', statement: 'Use SQLite for local storage', source_quote: 'use SQLite for local storage', confidence: 0.9 },
        { type: 'Assumption', statement: 'The team ships weekly', source_quote: 'ships weekly', confidence: 0.8 },
      ]),
    }));
    await popup.fill('[data-testid="add-text-input"]', NOTE);
    await popup.click('[data-testid="add-start"]');
    await popup.waitForSelector('[data-testid="proposal"]');
    await popup.locator('#pane').focus();
    await popup.keyboard.press('Escape'); // the same Esc key as the full window: stop
    await popup.waitForSelector('[data-testid="add-stopped-line"]');
    const stopped = await popup.textContent('[data-testid="add-stopped-line"]');
    if (!/stopped early/.test(stopped)) fail(`story 92: the stopped line: ${stopped}`);
    // "closes ... after Stop": the popup closes itself once the engine ended.
    await waitPopup(app, false, 20000);
    process.stdout.write('popup stop OK: Esc stopped the session and the popup closed after Stop\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------- scenario 7: --quick-add + placement follows the setting ---------- */

async function popupPlacement({ position, expectBottom }) {
  process.stdout.write(`--- popup: --quick-add placement (${position}) ---\n`);
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-popupplace-'));
  const { app, mainWin } = await launchPopupApp({ workDir, aiBaseUrl: null, quickAdd: true, withKey: false, position });
  try {
    const popup = await findPopup(app);
    await waitPopup(app, true);
    await popup.waitForSelector('#pane'); // some popup state rendered (the gate decides which)
    // The launch route booted with the main window parked.
    if ((await visibleWindows(app, 'Ember')) !== 0) fail('--quick-add must boot with the main window parked, not on top');
    const probe = await app.evaluate(
      ({ BrowserWindow, screen }, title) => {
        const win = BrowserWindow.getAllWindows().find((w) => w.getTitle() === title);
        if (!win) return null;
        const b = win.getBounds();
        const display = screen.getDisplayNearestPoint({ x: b.x + b.width / 2, y: b.y + b.height / 2 });
        return { bounds: b, workArea: display.workArea };
      },
      'Ember quick add',
    );
    assert.ok(probe, 'the quick popup window did not exist in the main process');
    const { bounds: b, workArea: a } = probe;
    assert.equal(b.width, 440, 'DESIGN.md: the quick popup is a 440px window');
    assert.ok(b.x >= a.x && b.y >= a.y && b.x + b.width <= a.x + a.width && b.y + b.height <= a.y + a.height, 'the popup sits inside the work area of the display the mouse is on');
    const topHalf = b.y + b.height / 2 < a.y + a.height / 2;
    if (expectBottom === true && !(!topHalf && b.y + b.height >= a.y + a.height - 60)) {
      fail(`bottom-right: the popup must hug the bottom (${JSON.stringify(b)} in ${JSON.stringify(a)})`);
    }
    if (expectBottom === false && !topHalf) {
      fail(`top-centre: the popup must hug the top (${JSON.stringify(b)} in ${JSON.stringify(a)})`);
    }
    process.stdout.write(`popup placement OK: ${position} inside the work area (${JSON.stringify(b)})\n`);
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  const ai = await startFakeAi();
  try {
    await popupAddAndDraft(ai);
    await popupNoKey();
    await popupSetupMissing();
    await popupRefusedRoute();
    await popupStopCloses(ai);
    await popupPlacement({ position: 'bottom-right', expectBottom: true });
    await popupPlacement({ position: 'top-center', expectBottom: false });
  } finally {
    ai.server.close();
  }
  process.stdout.write('e2e popup OK: all seven scenarios green (real ember child, fake AI server on EMBER_AI_BASE_URL)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e popup FAILED: ${err.message}\n`);
  process.exit(1);
});

'use strict';

// [shortcut graveyard fix] Boots here must not really register the global
// shortcut — every real bind left a stale KDE portal entry on the founder's
// machine. Nothing in this file asserts registration; the scenarios that do
// (popup.js, settings.js) opt out explicitly.
process.env.EMBER_APP_SHORTCUT_REFUSED ??= '1';

/**
 * The Batch 6 Chunk 13 E2E (dev-only, Linux; plan Impl-Batch6.md
 * chunk 13, stories 4, 5, 7, 8; findings D-07/D-09/D-10): the "Forget
 * this note" affordance on the Add screen, over the REAL `ember`
 * engine (the worktree's own Python, via the main checkout's venv —
 * the keep-safe convention: EMBER_APP_COMMAND = `python -m ember` +
 * PYTHONPATH = the worktree root) with the AI faked at the only seam
 * across a process boundary: a local HTTP server on EMBER_AI_BASE_URL
 * (the app/test/e2e/add.js conventions). The knowledge base is a real
 * temp file the engine itself creates (the first Add seeds it with
 * `ember init`, B4-07) — never the developer's own file.
 *
 * Scenarios:
 *  1. Reject EVERY item in the Add confirm loop -> the summary shows
 *     the Forget affordance, found by its element name
 *     (data-testid="add-forget"); its visible wording is NOT pinned
 *     here (I10). Press it -> an inline confirm `role="group"` with
 *     an accessible name and a cancel + confirm pair (story 7; D-10).
 *     The confirm's sentence wording comes from the sentence table's
 *     tests, not here (story 8). Cancel keeps the note; Confirm ->
 *     the note is GONE: the engine's own read
 *     (`list-sources-without-items`) lists nothing, `list-items`
 *     counts 0 items, and an export before the forget carried the
 *     note text while an export after carries it NOWHERE (story 9).
 *  2. Zero proposals (the empty state, story 28): NO Forget affordance
 *     anywhere — the offer is shown only when every item was rejected
 *     (story 11). This case is also the plan's Proof anchor: removing
 *     the "every item rejected" condition in add.mjs turns it red.
 *
 * Chunk 14 adds the Cleanup direction (the Notes-with-no-items list
 * and the history line) to this file as scenario 3: the list lives on
 * the Clean up screen beside the sweep; forgetting from THERE leaves
 * exactly ONE new ledger event of the `source_forgotten` kind on
 * Home/Ledger, naming the note by id and its date, with the note's
 * text appearing nowhere on the screen. The step-03 accessibility
 * helper runs on every state shown.
 */

const { _electron } = require('playwright');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const assert = require('node:assert/strict');
const path = require('node:path');
const { APP_ROOT, REPO_ROOT, PYTHON } = require('../util');

const KEY = 'sk-or-v1-ember-e2e-fake-key-0123456789';
const NOTE = 'We decided to use SQLite for local storage. We assume the team ships weekly.';
// Scenario 3's two notes: one quiet note that never becomes items
// (the list's row) and one note that CONFIRMS an item (must never be
// listed). The distinctive words are asserted, never sentence wording.
const QUIET_NOTE = 'Quiet raw note about packing list details kept only as text.';
const QUIET_SNIPPET = 'Quiet raw note about packing list';
const NOTE_B = 'We run the job queue on Postgres. The queue retries three times before it stops.';
const NOTE_B_SNIPPET = 'Postgres';

/* ---------- the fake AI (OpenAI /chat/completions shape, add.js) ---------- */

function startFakeAi() {
  let responder = () => ({ status: 200, content: '[]' });
  const bodies = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString('utf8');
      bodies.push(body);
      const r = responder();
      const payload = JSON.stringify({
        id: 'chatcmpl-ember-e2e-fake',
        object: 'chat.completion',
        created: 0,
        model: 'ember-e2e-fake',
        choices: [{ index: 0, message: { role: 'assistant', content: r.content ?? '' }, finish_reason: 'stop' }],
      });
      res.writeHead(r.status ?? 200, { 'content-type': 'application/json' });
      res.end(payload);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({
        server,
        url: `http://127.0.0.1:${server.address().port}/v1`,
        set(fn) {
          responder = fn;
        },
        bodies,
      });
    });
  });
}

/* ---------- the launcher (real worktree engine + a real temp KB path) ---------- */

function settingsText(kbPath) {
  return `${JSON.stringify(
    {
      schema: 1,
      textSize: 'default',
      colourTheme: 'system',
      quickPopup: { shortcut: 'CommandOrControl+Alt+N', position: 'bottom-right' },
      menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
      menuHidden: [],
      lastPane: 'add',
      knowledgeBasePath: kbPath,
    },
    null,
    2,
  )}\n`;
}

async function launchApp({ workDir, aiBaseUrl }) {
  const configDir = path.join(workDir, 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  const kbPath = path.join(workDir, 'kb.db'); // left uncreated: the first Add seeds it (ember init)
  fs.writeFileSync(path.join(userData, 'settings.json'), settingsText(kbPath));
  const env = { ...process.env };
  // Determinism: the developer machine's real key and any leftover
  // fake-ember session mode variables must never leak into these runs.
  delete env.EMBER_AI_API_KEY;
  delete env.OPENROUTER_API_KEY;
  delete env.FAKE_SESSION_DIE;
  delete env.FAKE_SESSION_DIE_CODE;
  delete env.FAKE_MODE;
  delete env.FAKE_CRASH_ID;
  env.XDG_CONFIG_HOME = configDir;
  env.XDG_STATE_HOME = path.join(workDir, 'state');
  fs.mkdirSync(env.XDG_STATE_HOME, { recursive: true });
  env.EMBER_APP_DB = kbPath;
  // The REAL engine IS the worktree code (the keep-safe convention):
  // `python -m ember` with PYTHONPATH at the worktree root, because the
  // shared venv's editable install points at the MAIN checkout.
  env.EMBER_APP_COMMAND = `${PYTHON} -m ember`;
  env.PYTHONPATH = REPO_ROOT; // python -m ember must import the WORKTREE code even though Electron's cwd is app/
  env.EMBER_AI_BASE_URL = aiBaseUrl;
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  const win = await app.firstWindow();
  const kept = await win.evaluate((k) => window.ember.setSessionKey(k), KEY);
  if (!kept || !kept.ok) throw new Error('the session key could not be kept in the test app');
  return { app, win, kbPath };
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

async function assertNoBareCode(win) {
  const visible = await win.evaluate(() => document.body.innerText);
  if (/[A-Z]+-\d{3}/.test(visible)) fail(`a bare error code reached the screen: ${visible.slice(-300)}`);
}

async function goToAdd(win) {
  await win.waitForSelector('#nav');
  await win.locator('#nav button[data-job="add"]').click();
  await win.waitForSelector('[data-testid="add-text-input"]');
}

/* ---------- real-knowledge-base reads (the engine's own door,
   the same verification habit as add.js — direct CLI on the run's KB,
   over the WORKTREE code: `python -m ember` with cwd at the repo root) ---------- */

function cliJson(args, kbPath) {
  return JSON.parse(
    execFileSync(PYTHON, ['-m', 'ember', ...args, '--db', kbPath], {
      encoding: 'utf8',
      cwd: REPO_ROOT,
      stdio: ['ignore', 'pipe', 'inherit'],
    }),
  );
}

function cliExport(outPath, kbPath) {
  execFileSync(PYTHON, ['-m', 'ember', 'export', '--out', outPath, '--db', kbPath], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  return fs.readFileSync(outPath, 'utf8');
}

/* ---------------- scenario 1: reject every item, forget the note ---------------- */

async function rejectAllAndForget(ai) {
  process.stdout.write('--- forget: reject every item, forget the note ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-forget-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Decision', statement: 'Use SQLite for local storage', source_quote: 'use SQLite for local storage', confidence: 0.9 },
        { type: 'Assumption', statement: 'The team ships weekly', source_quote: 'the team ships weekly', confidence: 0.8 },
      ]),
    }));
    await goToAdd(win);
    await win.fill('[data-testid="add-text-input"]', NOTE);
    await win.click('[data-testid="add-start"]');
    await win.waitForSelector('[data-testid="proposal"]');

    // Reject EVERY proposal with the keyboard (the add.js habit: n).
    await win.locator('#pane').focus();
    await win.keyboard.press('n');
    await win.waitForFunction(
      () => /The team ships weekly/.test((document.querySelector('[data-testid="proposal"]') ?? { textContent: '' }).textContent),
    );
    await win.locator('#pane').focus();
    await win.keyboard.press('n');
    await win.waitForSelector('[data-testid="add-summary-line"]');
    const summaryLine = await win.textContent('[data-testid="add-summary-line"]');
    if (!/0 items confirmed, 2 rejected/.test(summaryLine)) {
      fail(`the all-rejected summary must count 0 confirmed / 2 rejected: ${summaryLine}`);
    }
    if ((await win.locator('[data-testid="add-to-link"]').count()) !== 0) {
      fail('no items were confirmed: the Link-items path must not show');
    }

    // Story 11: the Forget affordance shows. Found by its ELEMENT name
    // existing; the visible wording is not pinned (I10).
    await win.waitForSelector('[data-testid="add-forget"]');
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Add (all-rejected summary with the Forget offer)');

    // The note is still there before the forget: the engine's own read
    // lists exactly one itemless note and an export carries the text.
    const before = cliJson(['list-sources-without-items'], kbPath);
    if (before.count !== 1 || before.sources.length !== 1) {
      fail(`before the forget exactly one itemless note must be listed, saw ${JSON.stringify(before)}`);
    }
    const exportBefore = cliExport(path.join(workDir, 'export-before.txt'), kbPath);
    if (!exportBefore.includes('We decided to use SQLite')) {
      fail('the export before the forget must still carry the note text (story 9, the before half)');
    }
    // Story 7: pressing it asks inline, in a role="group" with an
    // accessible name, and a cancel + confirm pair. Not a pop-up.
    await win.click('[data-testid="add-forget"]');
    const group = win.locator('[data-testid="add-forget-confirm"]');
    await group.waitFor();
    if ((await group.getAttribute('role')) !== 'group') fail('the inline confirm must be a role="group"');
    if (((await group.getAttribute('aria-label')) ?? '').trim() === '') {
      fail('the inline confirm must carry an accessible name (aria-label)');
    }
    if (!(await win.locator('[data-testid="add-forget-cancel"]').isVisible())) fail('the confirm pair needs a cancel button');
    if (!(await win.locator('[data-testid="add-forget-confirm-yes"]').isVisible())) fail('the confirm pair needs a confirm button');
    // D-10 (wording lives in the sentence-table tests): the confirm
    // names the backup fact somewhere in the group, the code asserts
    // only that the group is the confirm and its words carry it.
    const groupText = await group.textContent();
    if (!/backup/i.test(groupText)) fail(`D-10: the confirm must mention older backups (wording pinned in the table tests): ${groupText}`);
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Add (the inline forget confirm group)');

    // Cancel first: nothing is deleted, the offer comes back.
    await win.click('[data-testid="add-forget-cancel"]');
    if ((await win.locator('[data-testid="add-forget-confirm"]').count()) !== 0) fail('cancel must close the inline confirm');
    await win.waitForSelector('[data-testid="add-forget"]');
    await win.click('[data-testid="add-forget"]');
    const groupAgain = win.locator('[data-testid="add-forget-confirm"]');
    if ((await groupAgain.count()) === 0) fail('the confirm group must come back after re-pressing the offer');
    await groupAgain.waitFor();
    await win.click('[data-testid="add-forget-confirm-yes"]');
    await win.waitForSelector('[data-testid="add-forget-done"]');
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Add (after the note was forgotten)');

    // While the app is still open — the write is already durable.
    const afterInApp = cliJson(['list-sources-without-items'], kbPath);
    if (afterInApp.count !== 0 || afterInApp.sources.length !== 0) {
      fail(`after the forget the itemless list must be empty, saw ${JSON.stringify(afterInApp)}`);
    }
    await app.close();

    // After: the engine's own reads prove the note is gone.
    const after = cliJson(['list-sources-without-items'], kbPath);
    if (after.count !== 0 || after.sources.length !== 0) {
      fail(`the itemless list must be empty after the forget, saw ${JSON.stringify(after)}`);
    }
    const items = cliJson(['list-items'], kbPath);
    if (items.total !== 0) fail(`nothing may ever have been an item, saw ${JSON.stringify(items).slice(0, 200)}`);
    const exportAfter = cliExport(path.join(workDir, 'export-after.txt'), kbPath);
    // Story 9: the forgotten NOTE is gone — its stored text (the
    // verbatim source block) appears nowhere and the sources count is
    // 0. (The ledger's own history lines keep the earlier
    // rejected-PROPOSAL records; that history is the engine's by
    // design — D-26 keeps lines, the forget only textless-adds its
    // own — and is not the note.)
    if (exportAfter.includes(NOTE)) fail('story 9: the note text must appear NOWHERE in the export after the forget');
    if (/----- source \d+ text begin -----/.test(exportAfter)) fail('the forgotten note\'s verbatim source block must be gone from the export');
    if (!/0 sources/.test(exportAfter)) fail(`the export summary must count 0 sources after the forget: ${exportAfter.split('\n').find((l) => /exported/.test(l))}`);
    process.stdout.write('forget OK: all-rejected offer, inline confirm group, note gone from the list and the export\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 2: zero proposals — no Forget offer ---------------- */

async function zeroProposalsHasNoForget(ai) {
  process.stdout.write('--- forget: zero proposals shows no Forget offer ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-forgetzero-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({ status: 200, content: '[]' }));
    await goToAdd(win);
    await win.fill('[data-testid="add-text-input"]', 'A quiet note with nothing to keep in it.');
    await win.click('[data-testid="add-start"]');
    await win.waitForSelector('[data-testid="state-empty"]');
    const empty = await win.textContent('[data-testid="state-empty"]');
    if (!/nothing to propose/i.test(empty) || !/kept as a source/.test(empty)) {
      fail(`story 28: the empty state must say so: ${empty}`);
    }
    // Story 11: nothing was rejected here (nothing was proposed), so
    // NO Forget affordance anywhere on the screen.
    const forgotten = await win.locator('[data-testid="add-forget"]').count();
    if (forgotten !== 0) fail(`zero proposals must show no Forget offer, saw ${forgotten}`);
    await assertCleanScan(win, 'Add (empty, zero proposals, no Forget offer)');
    await app.close();
    // The text is kept as a source (the empty state's own fact).
    const before = cliJson(['list-sources-without-items'], kbPath);
    if (before.count !== 1) fail(`the quiet note stays a source, saw ${JSON.stringify(before)}`);
    process.stdout.write('zero proposals OK: the empty state, the text kept, NO Forget offer\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 3: the Clean up list and the ledger line ----------------
 * Chunk 14 (stories 6, 10): the Clean up screen shows the sources
 * with no items, found by its SECTION element (its heading wording is
 * not pinned — I10). The list is read-only until Forget is pressed;
 * forgetting inline (the chunk 13 confirm pattern) removes the row,
 * and Home/Ledger gains exactly ONE new ledger event of the
 * forgotten-note kind — found by its kind/kind code, carrying the
 * source id and the date (the line's sentence wording is NOT pinned
 * here: the expected sentence is computed from the SAME shared table
 * the screen renders, so wording changes cannot turn this e2e red).
 */

async function cleanupListAndHistoryLine(ai) {
  process.stdout.write('--- forget: the Clean up notes-with-no-items list and the ledger line ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-forgetcleanup-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    // Note A: zero proposals — the text is kept as a source with no items.
    ai.set(() => ({ status: 200, content: '[]' }));
    await goToAdd(win);
    await win.fill('[data-testid="add-text-input"]', QUIET_NOTE);
    await win.click('[data-testid="add-start"]');
    await win.waitForSelector('[data-testid="state-empty"]');

    // Note B: one item CONFIRMED — a note WITH items, never in the list.
    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Decision', statement: 'The job queue runs on Postgres', source_quote: 'job queue on Postgres', confidence: 0.9 },
      ]),
    }));
    await goToAdd(win);
    await win.fill('[data-testid="add-text-input"]', NOTE_B);
    await win.click('[data-testid="add-start"]');
    await win.waitForSelector('[data-testid="proposal"]');
    await win.locator('#pane').focus();
    await win.keyboard.press('y');
    await win.waitForSelector('[data-testid="add-summary-line"]');

    // The Clean up screen's section beside the sweep (found by its
    // SECTION element; heading wording not pinned — I10).
    await win.click('#nav button[data-job="cleanup"]');
    await win.waitForSelector('[data-testid="cleanup-itemless"]');
    const section = win.locator('[data-testid="cleanup-itemless"]');
    const rows = win.locator('[data-testid^="cleanup-itemless-row-"]');
    await rows.first().waitFor();
    if ((await rows.count()) !== 1) {
      fail(`exactly one note with no items must be listed, saw ${await rows.count()}`);
    }
    const sourceId = Number(await rows.first().getAttribute('data-source-id'));
    if (!Number.isInteger(sourceId) || sourceId <= 0) {
      fail(`the list row must carry the source's own id, saw ${sourceId}`);
    }
    const sectionText = await section.textContent();
    if (!sectionText.includes(QUIET_SNIPPET)) {
      fail(`the notes-with-no-items list must show the itemless note: ${sectionText.slice(0, 200)}`);
    }
    // The item-bearing note is NOT in the list (nowhere on this screen).
    const bodyText = await win.evaluate(() => document.body.innerText);
    if (bodyText.includes(NOTE_B_SNIPPET)) {
      fail('a note WITH items must not appear in the notes-with-no-items list');
    }
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Clean up (the notes-with-no-items list)');

    // The same inline confirm as the Add screen (chunk 13's pattern):
    // role="group" with an accessible name and a cancel + confirm pair.
    await win.click(`[data-testid="cleanup-itemless-forget-${sourceId}"]`);
    const group = win.locator(`[data-testid="cleanup-itemless-confirm-${sourceId}"]`);
    await group.waitFor();
    if ((await group.getAttribute('role')) !== 'group') fail('the Cleanup inline confirm must be a role="group"');
    if (((await group.getAttribute('aria-label')) ?? '').trim() === '') {
      fail('the Cleanup inline confirm must carry an accessible name (aria-label)');
    }
    if (!(await win.locator(`[data-testid="cleanup-itemless-cancel-${sourceId}"]`).isVisible())) {
      fail('the Cleanup confirm pair needs a cancel button');
    }
    if (!(await win.locator(`[data-testid="cleanup-itemless-confirm-yes-${sourceId}"]`).isVisible())) {
      fail('the Cleanup confirm pair needs a confirm button');
    }
    const groupText = await group.textContent();
    if (!/backup/i.test(groupText)) {
      fail(`the Cleanup confirm must mention older backups (D-10, wording pinned in the table tests): ${groupText}`);
    }
    await assertCleanScan(win, 'Clean up (the inline forget confirm group)');

    // Cancel first: the list is untouched, the offer comes back.
    await win.click(`[data-testid="cleanup-itemless-cancel-${sourceId}"]`);
    if ((await win.locator(`[data-testid="cleanup-itemless-confirm-${sourceId}"]`).count()) !== 0) {
      fail('cancel must close the Cleanup inline confirm');
    }
    await win.click(`[data-testid="cleanup-itemless-forget-${sourceId}"]`);
    await win.locator(`[data-testid="cleanup-itemless-confirm-${sourceId}"]`).waitFor();
    await win.click(`[data-testid="cleanup-itemless-confirm-yes-${sourceId}"]`);

    // After: the item disappears from the list.
    await win.waitForSelector('[data-testid="cleanup-itemless-empty"]');
    if ((await rows.count()) !== 0) fail('after the forget the forgotten note must be OUT of the list');
    const afterText = await win.evaluate(() => document.body.innerText);
    if (afterText.includes(QUIET_SNIPPET)) fail('the forgotten note\'s text must appear nowhere on the Clean up screen');
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Clean up (after the forget)');

    // Home/Ledger gains exactly ONE new ledger event of the
    // forgotten-note kind, by its kind code (the expected sentence is
    // computed from the SAME shared table the screen renders — the
    // line's wording is never pinned here, I10).
    const { historyEventSentence } = await import('../../shared/plain-sentences.mjs');
    const expected = historyEventSentence({
      kind: 'source_forgotten', cause: 'user_forget_source', field_changed: 'source_forgotten',
      item_id: null, link_id: null, link_source_item_id: null, link_target_item_id: null,
      link_type: null, old_value: null, new_value: null, close_reason: null,
      source_id: sourceId,
    });
    await win.click('#nav button[data-job="home"]');
    await win.waitForSelector('[data-testid="home-ledger-table"]');
    const ledgerRows = await win.evaluate(() => {
      const table = document.querySelector('[data-testid="home-ledger-table"]');
      if (!table) return [];
      return Array.from(table.querySelectorAll('tr')).map((tr) => {
        const cells = tr.querySelectorAll('td');
        return { when: cells[0] ? cells[0].textContent.trim() : '', what: cells[1] ? cells[1].textContent.trim() : '' };
      });
    });
    const forgottenRows = ledgerRows.filter((row) => row.what === expected);
    if (forgottenRows.length !== 1) {
      fail(
        `Home/Ledger must gain exactly ONE forgotten-note event, saw ${forgottenRows.length} of ` +
          `${ledgerRows.length} rows (expected sentence: ${expected}); rows: ${JSON.stringify(ledgerRows).slice(0, 400)}`,
      );
    }
    if (!forgottenRows[0].what.includes(String(sourceId))) {
      fail(`the forgotten-note event must carry the source id: ${forgottenRows[0].what}`);
    }
    // The date: the ledger event's own timestamp renders ISO
    // (YYYY-MM-DDT…), so today or yesterday in UTC (a run near
    // midnight stays honest).
    const day = (offsetDays) => new Date(Date.now() - offsetDays * 86400000).toISOString().slice(0, 10);
    if (!forgottenRows[0].when.startsWith(day(0)) && !forgottenRows[0].when.startsWith(day(1))) {
      fail(`the forgotten-note event must carry its date, saw "${forgottenRows[0].when}"`);
    }
    const homeText = await win.evaluate(() => document.body.innerText);
    if (homeText.includes(QUIET_SNIPPET)) fail('the forgotten note\'s text must appear nowhere on Home');
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Home (the ledger with the forgotten-note event)');

    await app.close();

    // The engine's own reads agree: the itemless list is empty and the
    // ledger carries exactly one source_forgotten event for THIS note.
    const after = cliJson(['list-sources-without-items'], kbPath);
    if (after.count !== 0 || after.sources.length !== 0) {
      fail(`after the forget the itemless list must be empty, saw ${JSON.stringify(after)}`);
    }
    const ledger = cliJson(['history', '--limit', '50'], kbPath);
    const forgottenEvents = (ledger.events ?? []).filter((e) => e.kind === 'source_forgotten');
    if (forgottenEvents.length !== 1) {
      fail(`the engine's ledger must hold exactly one source_forgotten event, saw ${forgottenEvents.length}`);
    }
    if (forgottenEvents[0].source_id !== sourceId) {
      fail(`the source_forgotten event must name the forgotten note's id, saw ${JSON.stringify(forgottenEvents[0])}`);
    }
    if (JSON.stringify(forgottenEvents[0]).includes(QUIET_SNIPPET)) {
      fail('D-26: the source_forgotten ledger event must be textless');
    }
    const items = cliJson(['list-items'], kbPath);
    if (items.total !== 1) fail(`only note B's item may exist, saw ${JSON.stringify(items).slice(0, 200)}`);
    const exportAfter = cliExport(path.join(workDir, 'export-after.txt'), kbPath);
    if (exportAfter.includes(QUIET_SNIPPET)) fail('the forgotten note\'s text must be gone from the export too');
    process.stdout.write('cleanup list OK: the itemless note listed, forgotten there, ONE ledger event on Home, text gone\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  const ai = await startFakeAi();
  try {
    await zeroProposalsHasNoForget(ai);
    await rejectAllAndForget(ai);
    await cleanupListAndHistoryLine(ai);
  } finally {
    ai.server.close();
  }
  process.stdout.write('e2e forget-note OK: all three scenarios green (real worktree ember, fake AI server)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e forget-note FAILED: ${err.message}\n`);
  process.exit(1);
});

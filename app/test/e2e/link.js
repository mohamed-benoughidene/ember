'use strict';

/**
 * The step-06 E2E (dev-only, Linux; app step file §2): the Link items
 * screen over the REAL `ember relate --confirm json` CONTRACT shapes,
 * driven exactly like the step-05/07 precedent — with the embedder
 * faked at the only seam available across a process boundary (bridge
 * L2 §10 D2: sentence-transformers cannot run in this dev tree, so the
 * fake ember stub serves the PINNED relate blocks/prompts per the
 * contract table; app/test/fake-ember.js, App 06 block). The knowledge
 * base is a REAL temp file seeded by the Python test helpers, and the
 * pick list is built from the REAL `ember list-items` document of that
 * file — every part of this e2e is real except the embedder inside
 * relate. NOT VERIFIED here and owed once at the live E2E ticket T50:
 * Link items with the REAL model.
 *
 * Flows:
 *  1. MAIN FLOW on a real seeded KB: pick from the list (never a typed
 *     id); the proposal shows BOTH items and the relationship (43);
 *     Confirm/Skip/Reject + Stop with the pinned button order (44);
 *     the accepted link block lands in "Linked so far" after y; the
 *     gatekeeper rejection shown in plain words inline; the summary
 *     event as the final state with the engine's own counts (47); the
 *     not-undoable note; the exact y/s/n answer lines pinned; a11y
 *     scans on every state; keyboard-first.
 *  2. EMPTY POOL (46): `no unrelated items` -> the honest empty state.
 *  3. PREPARING + STOP (45): no event after the first second -> the
 *     calm preparing state with Stop; Stop ends the child cleanly
 *     (exit 2, no summary, nothing changed). Reduce Motion honoured.
 *  4. MISSING PACKAGE (RELATE-017 through the table, step file §1):
 *     plain words + what to install; the code only behind Details.
 *  5. NO KEY (48): the same "needs the connection" path as Add.
 */

const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { _electron } = require('playwright');
const { APP_ROOT, REPO_ROOT, FAKE_EMBER, PYTHON } = require('../util');
const { runAccessibilityScan } = require('../helpers/a11y-scan.mjs');

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');

/* ---------- real temp knowledge bases (the Python helpers) ---------- */

function py(code) {
  execFileSync(PYTHON, ['-c', code], { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] });
}

/** The main-flow KB: three Active items, no links between them yet. */
function seedMainKb(dbPath) {
  py(`from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_source
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
conn = open_maintain_database(${JSON.stringify(dbPath)})
sid = insert_source(conn, full_text='We decided to use SQLite. We assume the team ships weekly. The cache holds records.')
insert_item(conn, source_id=sid, item_id=1, item_type='Decision', statement='Use SQLite for local storage.')
insert_item(conn, source_id=sid, item_id=2, item_type='Decision', statement='Copy the database before every upgrade.')
insert_item(conn, source_id=sid, item_id=3, item_type='Assumption', statement='The team ships weekly.')
conn.commit(); conn.close()
`);
}

/** Story 46's KB: one item, nothing else — no candidates at all. */
function seedSingleItemKb(dbPath) {
  py(`from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_source
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
conn = open_maintain_database(${JSON.stringify(dbPath)})
sid = insert_source(conn, full_text='One quiet note.')
insert_item(conn, source_id=sid, item_id=1, item_type='Decision', statement='Use SQLite for local storage.')
conn.commit(); conn.close()
`);
}

/**
 * The stub's read fixture, dumped from the REAL engine's own
 * `list-items` document of the seeded KB (the app's pick list is real
 * data; only the relate session is stubbed).
 */
function buildFixture(dbPath, fixturePath) {
  const doc = JSON.parse(execFileSync(EMBER, ['list-items', '--db', dbPath], { encoding: 'utf8', cwd: REPO_ROOT }));
  fs.writeFileSync(fixturePath, JSON.stringify(doc));
  return doc;
}

/* ---------- the launcher ---------- */

async function launch({ workDir, dbPath, relateEnv = {}, withKey = true }) {
  const configDir = path.join(workDir, 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(
    path.join(userData, 'settings.json'),
    `${JSON.stringify(
      {
        schema: 1,
        textSize: 'default',
        colourTheme: 'system',
        quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' },
        menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
        menuHidden: [],
        lastPane: 'link',
        knowledgeBasePath: dbPath,
      },
      null,
      2,
    )}\n`,
  );
  const env = { ...process.env };
  // Determinism: stray fake-ember session variables and real keys must
  // never leak into these runs (the add e2e's rule).
  for (const k of [
    'FAKE_SESSION_SCRIPT',
    'FAKE_SESSION_DIE',
    'FAKE_SESSION_DIE_CODE',
    'FAKE_SESSION_IDLE',
    'FAKE_RELATE_SCRIPT',
    'FAKE_RELATE_EMPTY',
    'FAKE_RELATE_SLOW',
    'FAKE_RELATE_ERROR',
    'FAKE_RELATE_ERROR_CODE',
    'FAKE_RELATE_ERROR_DETAIL',
    'FAKE_RELATE_ANSWERS',
    'FAKE_FIXTURE',
    'EMBER_AI_API_KEY',
    'OPENROUTER_API_KEY',
  ]) {
    delete env[k];
  }
  env.XDG_CONFIG_HOME = configDir;
  env.EMBER_APP_COMMAND = `node ${FAKE_EMBER}`;
  env.FAKE_MODE = 'app';
  env.FAKE_FIXTURE = path.join(workDir, 'fixture.json');
  env.EMBER_APP_DB = dbPath;
  for (const [k, v] of Object.entries(relateEnv)) env[k] = v;
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  const win = await app.firstWindow();
  if (withKey) {
    const kept = await win.evaluate(() => window.ember.setSessionKey('sk-or-v1-ember-e2e-fake-key-0123456789'));
    if (!kept || !kept.ok) throw new Error('the session key could not be kept in the test app');
  }
  return { app, win };
}

/* ---------------- small helpers ---------------- */

function fail(what) {
  throw new Error(what);
}

async function assertCleanScan(win, label) {
  const { violations, checked } = await runAccessibilityScan(win, {
    // The Text Size Rule (DESIGN.md): measure at the Largest size with
    // the app's own :root.big adaptations in force.
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
  if (/[A-Z]+-\d{3}/.test(visible)) fail(`a bare error code reached the screen (story 102): ${visible.slice(-300)}`);
}

async function gotoLink(win) {
  await win.waitForSelector('#nav');
  await win.locator('#nav button[data-job="link"]').click();
  await win.waitForSelector('[data-testid="link-table"]');
}

async function pickItem(win, id) {
  await win.click(`[data-testid="link-row-${id}"]`);
  await win.waitForSelector('[data-testid="link-flow"]');
}

/** The keyboard's home row anchor: focus the pane like a keyboard user. */
async function focusPane(win) {
  await win.locator('#pane').focus();
}

/* ---------- the pinned relate rounds (contract shapes) ---------- */

const PREVIEW_1 = {
  event: 'block',
  kind: 'link-preview',
  fields: { index: 1, total: 3, source_item_id: 2, target_item_id: 1, link_type: 'supports', rationale: 'both say the storage choice drives the copy step' },
  text: 'Proposal 1/3: item 2 -> item 1 [supports]\n  rationale: both say the storage choice drives the copy step',
};
const PREVIEW_2 = {
  event: 'block',
  kind: 'link-preview',
  fields: { index: 2, total: 3, source_item_id: 2, target_item_id: 3, link_type: 'supports', rationale: null },
  text: 'Proposal 2/3: item 2 -> item 3 [supports]\n  rationale: -',
};
const PREVIEW_3 = {
  event: 'block',
  kind: 'link-preview',
  fields: { index: 3, total: 3, source_item_id: 2, target_item_id: 3, link_type: 'contradicts', rationale: 'weekly shipping conflicts with the offline assumption' },
  text: 'Proposal 3/3: item 2 -> item 3 [contradicts]\n  rationale: weekly shipping conflicts with the offline assumption',
};
const PROMPT = { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [s]kip / [q]uit', choices: ['y', 'n', 's', 'q'] };
const LINK_1 = {
  event: 'block',
  kind: 'link',
  fields: { link_id: 1, source_item_id: 2, target_item_id: 1, link_type: 'supports', status: 'Confirmed', rationale: 'both say the storage choice drives the copy step' },
  text: [
    '- link_id: 1',
    '  source_item_id: 2',
    '  target_item_id: 1',
    '  link_type: "supports"',
    '  status: "Confirmed"',
    '  rationale: "both say the storage choice drives the copy step"',
  ].join('\n'),
};
const GATEKEEPER = { event: 'message', text: 'relate rejected: RELATE-007 | item 3 is Closed' };
// rejected = the user's explicit `n` + the gatekeeper rejection (the
// engine's own arithmetic).
const SUMMARY_OK = { event: 'summary', accepted: 1, rejected: 2, skipped: 1, aborted: false };

/* ---------------- flow 1: the main flow ---------------- */

async function mainFlow() {
  process.stdout.write('--- link: main flow (pick, confirm, skip, reject, gatekeeper, summary) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-link-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  const fixture = buildFixture(dbPath, path.join(workDir, 'fixture.json'));
  if (fixture.items.length !== 3) fail(`the seeded KB must list 3 items, saw ${fixture.items.length}`);
  const answersFile = path.join(workDir, 'answers.jsonl');
  const { app, win } = await launch({
    workDir,
    dbPath,
    relateEnv: {
      FAKE_RELATE_SCRIPT: JSON.stringify([
        [PREVIEW_1, PROMPT],
        [LINK_1, PREVIEW_2, PROMPT],
        [PREVIEW_3, PROMPT],
        [GATEKEEPER, SUMMARY_OK],
      ]),
      FAKE_RELATE_EXIT: '0',
      FAKE_RELATE_ANSWERS: answersFile,
    },
  });
  try {
    await gotoLink(win);

    // The pick list: real engine data, one row per item, a11y-clean.
    const rows = await win.locator('[data-testid^="link-row-"]').count();
    if (rows !== 3) fail(`the pick list must hold 3 items, saw ${rows}`);
    const row2 = await win.textContent('[data-testid="link-row-2"]');
    if (!/Copy the database before every upgrade/.test(row2)) fail(`the row must carry the engine statement: ${row2}`);
    await assertCleanScan(win, 'Link items (pick list)');

    // Story 42/43: pick item 2 -> the proposal shows both items and
    // the relationship in one card, with the progress line.
    await pickItem(win, 2);
    await win.waitForSelector('[data-testid="link-proposal"]');
    const proposal = await win.textContent('[data-testid="link-proposal"]');
    if (!/Proposal 1 of 3/.test(proposal)) fail(`the progress line is missing: ${proposal}`);
    if (!/Copy the database before every upgrade/.test(proposal) || !/Use SQLite for local storage/.test(proposal)) {
      fail(`story 43: both items must be in one proposal: ${proposal}`);
    }
    if (!/supports/.test(proposal)) fail(`the relationship name must show: ${proposal}`);
    if (!/Ember's reason/.test(proposal)) fail(`the engine's rationale must show: ${proposal}`);
    // The pinned link button order: Stop, Skip, Reject, Confirm.
    const actions = await win
      .locator('[data-testid="link-choice"] [data-action]')
      .evaluateAll((els) => els.map((el) => el.dataset.action));
    assert.deepEqual(actions, ['proposal-stop', 'proposal-skip', 'proposal-reject', 'proposal-confirm'], 'the pinned button order');
    await assertCleanScan(win, 'Link items (proposal 1)');
    await assertNoBareCode(win);

    // Story 44, keyboard-first: Return confirms; the accepted link
    // block lands in Linked so far (the engine writes, then prints).
    await focusPane(win);
    await win.keyboard.press('Enter');
    await win.waitForSelector('[data-testid="linked-row"]');
    const linked = await win.textContent('[data-testid="link-linked"]');
    if (!/supports/.test(linked)) fail(`the accepted relationship must show: ${linked}`);
    if (!/Copy the database before every upgrade/.test(linked) || !/Use SQLite for local storage/.test(linked)) {
      fail(`story 43: the accepted link row must name both items: ${linked}`);
    }

    // Proposal 3 arrives (2 -> 3 contradicts); Reject it with 'n'.
    await win.waitForFunction(
      () => /The team ships weekly/.test((document.querySelector('[data-testid="link-proposal"]') ?? { textContent: '' }).textContent),
    );
    await assertCleanScan(win, 'Link items (proposal 2 + Linked so far)');
    await focusPane(win);
    await win.keyboard.press('s');

    // Proposal 3/3 arrives; Reject it with the keyboard (n).
    await win.waitForFunction(
      () => /contradicts/.test((document.querySelector('[data-testid="link-proposal"]') ?? { textContent: '' }).textContent),
    );
    await focusPane(win);
    await win.keyboard.press('n');

    // The gatekeeper rejection arrives as a message event (plain words
    // inline), then the summary event lands as the final state.
    await win.waitForSelector('[data-testid="link-summary-line"]');
    const summaryLine = await win.textContent('[data-testid="link-summary-line"]');
    if (!/1 link confirmed, 1 skipped, 2 rejected/.test(summaryLine)) fail(`story 47: the engine counts: ${summaryLine}`);
    const log = await win.textContent('[data-testid="link-log"]');
    if (!/rules rejected/.test(log)) fail(`the gatekeeper rejection must show in plain words: ${log}`);
    if (!/item 3 is Closed/.test(log)) fail(`the engine's own detail must show: ${log}`);
    if (/RELATE-007/.test(log)) fail('the rejection must be plain words, no bare code (story 102)');
    const note = await win.textContent('[data-testid="link-undo-note"]');
    if (!/not undone by the Undo button/.test(note) || !/Fix and close/.test(note)) {
      fail(`the not-undoable note must point at Fix and close: ${note}`);
    }
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Link items (summary)');
    await app.close();

    // The exact answer lines the app wrote for y / s / n (the contract:
    // one {"answer": "<text>"} line per prompt).
    const answers = fs.readFileSync(answersFile, 'utf8').trim().split('\n');
    const parsed = answers.map((a) => JSON.parse(a).answer);
    assert.deepEqual(parsed, ['y', 's', 'n'], 'the exact answer letters in order');
    process.stdout.write('main flow OK: stories 42-44, 47, 102, the not-undoable note, the exact answer lines\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 2: the empty pool (story 46) ---------------- */

async function emptyPoolFlow() {
  process.stdout.write('--- link: no unrelated items (story 46) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-linkempty-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedSingleItemKb(dbPath);
  buildFixture(dbPath, path.join(workDir, 'fixture.json'));
  const { app, win } = await launch({ workDir, dbPath, relateEnv: { FAKE_RELATE_EMPTY: '1' } });
  try {
    await gotoLink(win);
    await pickItem(win, 1);
    await win.waitForSelector('[data-testid="link-empty-line"]');
    const line = await win.textContent('[data-testid="link-empty-line"]');
    if (!/No unrelated items are left to link/.test(line)) fail(`story 46: the empty words: ${line}`);
    await assertCleanScan(win, 'Link items (empty pool)');
    // Back to the pick list.
    await win.click('[data-testid="link-again"]');
    await win.waitForSelector('[data-testid="link-table"]');
    process.stdout.write('empty pool OK (story 46)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 3: preparing + stop (story 45) + Reduce Motion ---------------- */

async function preparingAndStopFlow() {
  process.stdout.write('--- link: preparing state with Stop (story 45) + Reduce Motion ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-linkslow-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  buildFixture(dbPath, path.join(workDir, 'fixture.json'));
  const { app, win } = await launch({ workDir, dbPath, relateEnv: { FAKE_RELATE_SLOW: '1' } });
  try {
    await gotoLink(win);
    await pickItem(win, 2);
    // Nothing may sit in the FIRST second but the loading skeleton;
    // after it, the calm preparing state with its Stop button.
    await win.waitForSelector('[data-testid="link-preparing"]');
    const preparing = await win.textContent('[data-testid="link-preparing"]');
    if (!/take minutes/.test(preparing) || !/language model/.test(preparing)) {
      fail(`story 45: the preparing words: ${preparing}`);
    }
    await assertCleanScan(win, 'Link items (preparing)');

    // Reduce Motion (99/104): nothing animates even across a redraw.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('svg, .skel')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    await win.emulateMedia({ reducedMotion: 'no-preference' });

    // Stop ends the child cleanly: the quiet exit 2 with no summary is
    // the honest stopped state ("nothing was changed").
    await win.click('[data-testid="link-preparing-stop"]');
    await win.waitForSelector('[data-testid="link-stopped-line"]');
    const stopped = await win.textContent('[data-testid="link-stopped-line"]');
    if (!/stopped before Ember finished preparing/.test(stopped) || !/Nothing was changed/.test(stopped)) {
      fail(`the preparing-stop words: ${stopped}`);
    }
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Link items (stopped while preparing)');
    process.stdout.write('preparing + stop OK (story 45, Reduce Motion honoured)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 4: the missing optional package (RELATE-017) ---------------- */

async function missingPackageFlow() {
  process.stdout.write('--- link: missing optional package (RELATE-017 through the table) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-linkpkg-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  buildFixture(dbPath, path.join(workDir, 'fixture.json'));
  const { app, win } = await launch({
    workDir,
    dbPath,
    relateEnv: {
      FAKE_RELATE_ERROR: '1',
      FAKE_RELATE_ERROR_CODE: 'RELATE-017 EmbedderLoadFailed',
      FAKE_RELATE_ERROR_DETAIL: 'sentence_transformers is not installed; install the optional extra with: python -m pip install -e ".[relate]"',
    },
  });
  try {
    await gotoLink(win);
    await pickItem(win, 2);
    await win.waitForSelector('[data-testid="link-error"] [data-testid="state-error"]');
    const error = await win.textContent('[data-testid="link-error"]');
    if (!/not installed/i.test(error)) fail(`the missing-package words: ${error}`);
    if (!/pip install/.test(error) || !/\[relate\]/.test(error)) fail(`the what-to-do words: ${error}`);
    if (!/No link was added or changed/.test(error)) fail(`the nothing-changed fact: ${error}`);
    // This failure is not retryable in place (the package would fail
    // again): the way forward is back to the pick list.
    if (!(await win.locator('[data-action="link-again"]').isVisible())) fail('the way back to the pick list must be offered');
    await assertNoBareCode(win);
    await win.locator('[data-action="show-details"]').click();
    await win.waitForSelector('[data-testid="link-error"] [data-testid="error-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="link-error"] [data-testid="error-code"]');
    if (!/RELATE-017 EmbedderLoadFailed/.test(code)) fail(`Details must reveal the code, saw ${code}`);
    await assertCleanScan(win, 'Link items (missing package)');
    process.stdout.write('missing package OK: what to install, nothing changed, code behind Details\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 5: no key at all (story 48) ---------------- */

async function noKeyFlow() {
  process.stdout.write('--- link: no key, the same path as Add (story 48) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-linknokey-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  buildFixture(dbPath, path.join(workDir, 'fixture.json'));
  const { app, win } = await launch({ workDir, dbPath, withKey: false });
  try {
    await win.waitForSelector('#nav');
    await win.locator('#nav button[data-job="link"]').click();
    await win.waitForSelector('[data-testid="state-no-key"]');
    const block = await win.textContent('[data-testid="state-no-key"]');
    if (!/needs the AI connection/.test(block)) fail(`story 48: the no-key words: ${block}`);
    await assertCleanScan(win, 'Link items (no-key state)');
    await win.locator('[data-testid="state-no-key"] [data-action="link-open-setup"]').click();
    await win.waitForSelector('[data-testid="setup-key-input"]');
    const step = await win.textContent('.setup .sub');
    if (!/Step 2 of 3/.test(step)) fail(`the button must open the AI-connection setup step, saw: ${step}`);
    process.stdout.write('no-key OK (story 48, the Add path)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  await mainFlow();
  await emptyPoolFlow();
  await preparingAndStopFlow();
  await missingPackageFlow();
  await noKeyFlow();
  process.stdout.write('e2e link OK: all five flows green (real seeded KBs, the pinned stub shapes for relate; the real model is the T50 manual check)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e link FAILED: ${err.message}\n`);
  process.exit(1);
});

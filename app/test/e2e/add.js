'use strict';

// [shortcut graveyard fix] Boots here must not really register the global
// shortcut — every real bind left a stale KDE portal entry on the founder's
// machine. Nothing in this file asserts registration; the scenarios that do
// (popup.js, settings.js) opt out explicitly.
process.env.EMBER_APP_SHORTCUT_REFUSED ??= '1';

/**
 * The step-05 E2E (dev-only, Linux; app step file §2): the Add screen
 * over the REAL `ember capture --file <temp> --confirm json --db <kb>`
 * child, with the AI faked at the only seam across a process boundary:
 * a local HTTP server on EMBER_AI_BASE_URL (the in-process CliRunner
 * seam is not available to a child). The knowledge base is a real temp
 * file the Ember engine itself creates, writes and reads.
 *
 * Scenarios:
 *  1. the full confirm loop: add text, Confirm (Return) then Reject
 *     (n) with the keyboard, the Saved so far list (24), the summary
 *     with the Link items path (18, 20, 25, 26); DB state equals the
 *     terminal run on the same input (contract parity); a11y scans;
 *     Reduce Motion honoured (99/104).
 *  2. stop part-way with Esc (22, 23): one item saved, nothing
 *     half-written (real DB check).
 *  3. edit-then-confirm (21): the type/statement/metadata sub-prompts
 *     as a small form; the DB carries the edited item.
 *  4. zero proposals (28): the empty state; the text kept as a source.
 *  5. the message events inline (19): two dropped proposals (an
 *     unknown type, a quote not in the text) and a near-duplicate
 *     warning.
 *  6. AI unreachable (27): plain words, text kept, nothing created,
 *     Retry and Details; DB untouched (0 items, one source).
 *  7. a failed Add (Batch 3 F2): the error AND the draft form show
 *     together, the box still holding the text that was sent.
 *  8. the key refused at the first Add (the decision 5-A refusal of
 *     stories 5/8): plain "refused the key" words.
 *  9. no key at all (29): Add says it needs the connection and opens
 *     the AI-connection setup.
 * 10. a child that dies mid-session: the error state and the temp
 *     file cleaned (fake ember stub; a real ember child cannot be
 *     killed mid-session from here — deviation logged). BRIDGE-001
 *     never reaches the user in any scenario.
 * 11. a fake EMBER-000 engine death (Batch 2 Chunk 14, story 2/3):
 *     the plain crash sentence (Chunk 12), and under it the two
 *     buttons "Copy crash report" and "Show file"; clicking Copy
 *     shows the "Copied." feedback and the crash text, and the shown
 *     crash text is word for word the fake crash file's content. The
 *     REAL clipboard write is pinned by the injected-fake unit test
 *     in Chunk 13 (app/test/crash-ipc.test.js); this e2e asserts the
 *     visible feedback only.
 *
 * The step-03 accessibility helper runs on every screen and state this
 * e2e renders (stories 96-104).
 */

const { _electron } = require('playwright');
const http = require('node:http');
const net = require('node:net');
const { execFileSync, spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const assert = require('node:assert/strict');
const path = require('node:path');
const { APP_ROOT, REPO_ROOT, FAKE_EMBER, PYTHON } = require('../util');

// The shared venv's console script. Its editable install points at the
// MAIN checkout, so EVERY engine spawn below pins PYTHONPATH to
// REPO_ROOT (the forget-note/keep-safe convention): the path finder
// precedes the editable finder's appended hook, so `import ember`
// resolves to THIS repo's code — the repo the e2e run lives in.
const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');
const ENGINE_ENV = { ...process.env, PYTHONPATH: REPO_ROOT };
const KEY = 'sk-or-v1-ember-e2e-fake-key-0123456789';

/* Batch 2 Chunk 14: the sentinel crash id the fake EMBER-000 death
   names (a fake value only — a real report's id looks like
   `20261101T120000Z-a1b2c3`; the shape here matches it). */
const CRASH_ID = '20261101T120000Z-e2e14c';

const NOTE = 'We decided to use SQLite for local storage. We assume the team ships weekly.';

/* Batch 3 Chunk 2: a clearly different note the scenario types into the
   box after the failure, so the Retry request can be pinned to the
   EDITED text (not the original). No quote characters: the recorded
   request body is JSON-escaped and the assert is a plain substring check. */
const EDITED_NOTE = 'Edited after the failure: the retry must send exactly this edited note text.';

/* ---------- the fake AI (OpenAI /chat/completions shape) ---------- */

function startFakeAi() {
  let responder = () => ({ status: 200, content: '[]' });
  const bodies = []; // Batch 3 Chunk 1: every request body received (the fake-ai-server.js habit, body string only).
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

/** A free, then-closed port: the unreachable-AI base URL. */
function closedPortUrl() {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(`http://127.0.0.1:${port}/v1`));
    });
  });
}

/* ---------- the launcher (real ember + a real temp KB path) ---------- */

function settingsText(kbPath) {
  return `${JSON.stringify(
    {
      schema: 1,
      textSize: 'default',
      colourTheme: 'system',
      quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' },
      menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
      menuHidden: [],
      lastPane: 'add',
      knowledgeBasePath: kbPath,
    },
    null,
    2,
  )}\n`;
}

async function launchApp({ workDir, aiBaseUrl, withKey = true, childDies = false, crash = false }) {
  const configDir = path.join(workDir, 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  const kbPath = path.join(workDir, 'kb.db');
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
  // The crash-report state folder too (Batch 2 Chunk 14): crash files
  // land in the scenario's own folder, never in ~/.local/state.
  env.XDG_STATE_HOME = path.join(workDir, 'state');
  fs.mkdirSync(env.XDG_STATE_HOME, { recursive: true });
  env.EMBER_APP_DB = kbPath;
  // The REAL engine IS this repo's code (see EMBER above): the bridge
  // child inherits PYTHONPATH so `import ember` stays this checkout's.
  env.PYTHONPATH = REPO_ROOT;
  if (crash) {
    // A fake EMBER-000 engine death mid-session: the Chunks 2/14 shape.
    env.EMBER_APP_COMMAND = `node ${FAKE_EMBER}`;
    env.FAKE_MODE = 'crash';
    env.FAKE_CRASH_ID = CRASH_ID;
  } else if (childDies) {
    env.EMBER_APP_COMMAND = `node ${FAKE_EMBER}`;
    env.FAKE_MODE = 'session';
    // Mid-session death: one block + one prompt, then gone (no summary).
    env.FAKE_SESSION_SCRIPT = JSON.stringify([
      { event: 'block', kind: 'item', fields: { id: 1, type: 'Decision', statement: 'fake' }, text: '- id: 1' },
      { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [e]dit / [q]uit', choices: ['y', 'n', 'e', 'q'] },
    ]);
    env.FAKE_SESSION_DIE = '1';
    env.FAKE_SESSION_DIE_CODE = '1';
  } else {
    env.EMBER_APP_COMMAND = EMBER;
  }
  env.EMBER_AI_BASE_URL = aiBaseUrl;
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  const win = await app.firstWindow();
  if (withKey) {
    const kept = await win.evaluate((k) => window.ember.setSessionKey(k), KEY);
    if (!kept || !kept.ok) throw new Error('the session key could not be kept in the test app');
  }
  return { app, win, kbPath, userData, crashId: crash ? CRASH_ID : null };
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
  if (/[A-Z]+-\d{3}/.test(visible)) fail(`a bare error code reached the screen (story 102): ${visible.slice(-300)}`);
}

/** The keyboard's home row anchor: focus the pane like a keyboard user. */
async function focusPane(win) {
  await win.locator('#pane').focus();
}

async function goToAdd(win) {
  await win.waitForSelector('#nav');
  await win.locator('#nav button[data-job="add"]').click();
  await win.waitForSelector('[data-testid="add-text-input"]');
}

async function addText(win, text) {
  await win.fill('[data-testid="add-text-input"]', text);
  await win.click('[data-testid="add-start"]');
}

/* ---------- real-knowledge-base reads (the engine's own door) ---------- */

function dbItems(dbPath) {
  return JSON.parse(execFileSync(EMBER, ['list-items', '--db', dbPath], { encoding: 'utf8', cwd: REPO_ROOT, env: ENGINE_ENV }));
}

function dbCounts(dbPath) {
  return JSON.parse(
    execFileSync(
      PYTHON,
      [
        '-c',
        [
          'import json, sqlite3, sys',
          'conn = sqlite3.connect(sys.argv[1])',
          'def n(t):',
          '    try:',
          '        return conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]',
          '    except sqlite3.OperationalError:',
          '        return -1',
          'print(json.dumps({t: n(t) for t in ["items", "links", "sources", "change_log"]}))',
        ].join('\n'),
        dbPath,
      ],
      { encoding: 'utf8', cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] },
    ),
  );
}

function dbItemRow(dbPath) {
  return JSON.parse(
    execFileSync(
      PYTHON,
      [
        '-c',
        [
          'import json, sqlite3, sys',
          'conn = sqlite3.connect(sys.argv[1])',
          'rows = conn.execute("SELECT id, type, statement, metadata, status FROM items ORDER BY id").fetchall()',
          'print(json.dumps(rows))',
        ].join('\n'),
        dbPath,
      ],
      { encoding: 'utf8', cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] },
    ),
  );
}

function seedExistingItem(kbPath, statement) {
  execFileSync(
    PYTHON,
    [
      '-c',
      [
        'from pathlib import Path',
        'from ember.adapters.sqlite import open_database',
        'from tests.fakes import insert_source, insert_item',
        `Path(${JSON.stringify(kbPath)}).touch()`,
        `conn = open_database(${JSON.stringify(kbPath)})`,
        'source_id = insert_source(conn)',
        `insert_item(conn, source_id=source_id, item_id=1, item_type="Decision", statement=${JSON.stringify(statement)})`,
        'conn.commit()',
        'conn.close()',
      ].join('\n'),
    ],
    { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] },
  );
}

/* ---------------- scenario 1: the full confirm loop + parity ---------- */

async function fullLoopAndParity(ai) {
  process.stdout.write('--- add: full confirm loop, parity, motion ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-add-'));
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

    // Story 17: the notice before sending, on the input form.
    const notice = await win.textContent('[data-testid="add-notice"]');
    if (!/kept word for word/.test(notice) || !/sent to the AI service/.test(notice)) {
      fail(`story 17: the notice is missing its two facts: ${notice}`);
    }
    await assertCleanScan(win, 'Add (input form)');

    await addText(win, NOTE);
    await win.waitForSelector('[data-testid="proposal"]');
    const proposal1 = await win.textContent('[data-testid="proposal"]');
    if (!/Decision/.test(proposal1) || !/Use SQLite for local storage/.test(proposal1)) {
      fail(`proposal 1 must show the parsed block's type and statement: ${proposal1.slice(0, 200)}`);
    }
    if (!/use SQLite for local storage/.test(proposal1)) fail('the quote from the source must show (story 18)');
    // The pinned ProposalBlock order: Stop, Edit, Reject, Confirm.
    const actions = await win
      .locator('[data-testid="proposal"] [data-action]')
      .evaluateAll((els) => els.map((el) => el.dataset.action));
    assert.deepEqual(actions, ['proposal-stop', 'proposal-edit', 'proposal-reject', 'proposal-confirm'], 'the pinned button order');
    await assertCleanScan(win, 'Add (proposal 1)');
    await assertNoBareCode(win);

    // Story 23: Return confirms.
    await focusPane(win);
    await win.keyboard.press('Enter');
    await win.waitForSelector('[data-testid="saved-row"]');
    const saved = await win.textContent('[data-testid="saved-row"]');
    if (!/Use SQLite for local storage/.test(saved) || !/Active/.test(saved)) {
      fail(`story 24: the Saved so far row must carry the item and its heat word: ${saved}`);
    }
    await win.waitForFunction(() => /Assumption/.test((document.querySelector('[data-testid="proposal"]') ?? { textContent: '' }).textContent));
    // Reduce Motion honoured (99/104): nothing animates even while the
    // saved mark just changed.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('svg')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    await win.emulateMedia({ reducedMotion: 'no-preference' });
    await assertCleanScan(win, 'Add (proposal 2 + Saved so far)');

    // Story 23: n rejects.
    await focusPane(win);
    await win.keyboard.press('n');
    await win.waitForSelector('[data-testid="add-summary-line"]');
    const summaryLine = await win.textContent('[data-testid="add-summary-line"]');
    if (!/1 item confirmed, 1 rejected/.test(summaryLine)) fail(`story 25: the summary counts: ${summaryLine}`);
    if (!(await win.locator('[data-testid="add-to-link"]').isVisible())) fail('story 26: the one-click path to Link items');
    await assertCleanScan(win, 'Add (summary)');
    await assertNoBareCode(win);

    // Back to a fresh draft (the engine cleaned its own temp file).
    await win.click('[data-testid="add-reset"]');
    await win.waitForSelector('[data-testid="add-text-input"]');
    if ((await win.inputValue('[data-testid="add-text-input"]')) !== '') fail('the draft must be empty again');
    await app.close();

    // Contract parity: the terminal run on the SAME input with the SAME
    // fake AI must leave the SAME DB state (step file §2). Run it
    // ASYNC: the fake AI server lives in THIS process, and a blocking
    // spawn would starve its own event loop.
    const parityDir = path.join(workDir, 'parity');
    fs.mkdirSync(parityDir, { recursive: true });
    const noteFile = path.join(parityDir, 'note.txt');
    fs.writeFileSync(noteFile, NOTE);
    const parityEnv = { ...process.env, EMBER_AI_BASE_URL: ai.url, EMBER_AI_API_KEY: KEY, PYTHONPATH: REPO_ROOT };
    delete parityEnv.OPENROUTER_API_KEY;
    await new Promise((resolve, reject) => {
      const child = spawn(EMBER, ['capture', '--file', noteFile, '--db', path.join(parityDir, 'par.db')], {
        env: parityEnv,
        cwd: REPO_ROOT,
        stdio: ['pipe', 'ignore', 'inherit'],
      });
      child.stdin.end('y\nn\n');
      child.on('error', reject);
      child.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`the parity terminal run exited ${code}`))));
    });
    const appDb = { items: dbItems(kbPath), counts: dbCounts(kbPath) };
    const termDb = { items: dbItems(path.join(parityDir, 'par.db')), counts: dbCounts(path.join(parityDir, 'par.db')) };
    const rows = (db) =>
      db.items.items.map((it) => ({ id: it.id, type: it.type, statement: it.statement, status: it.status, metadata: it.metadata }));
    assert.deepEqual(rows(appDb), rows(termDb), 'the app add and the terminal capture leave the same items');
    assert.deepEqual(appDb.counts, termDb.counts, 'the same row counts everywhere');
    assert.equal(appDb.counts.items, 1, 'one confirmed item; a rejected proposal writes a ledger row, not an item row');
    assert.equal(appDb.counts.sources, 1);
    process.stdout.write('full loop OK: confirm+reject, saved list, summary, parity with the terminal run\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 2: stop part-way (Esc) ---------------- */

async function stopPartWay(ai) {
  process.stdout.write('--- add: stop part-way (Esc) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addstop-'));
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
    await addText(win, NOTE);
    await win.waitForSelector('[data-testid="proposal"]');
    await focusPane(win);
    await win.keyboard.press('Enter'); // confirm proposal 1
    await win.waitForSelector('[data-testid="saved-row"]');
    await win.keyboard.press('Escape'); // stop before proposal 2
    await win.waitForSelector('[data-testid="add-stopped-line"]');
    const stopped = await win.textContent('[data-testid="add-stopped-line"]');
    if (!/stopped early/.test(stopped) || !/1 item was saved/.test(stopped) || !/nothing is half-written/.test(stopped)) {
      fail(`story 22: the stopped summary must be honest: ${stopped}`);
    }
    await assertCleanScan(win, 'Add (stopped)');
    await app.close();
    // The real engine: the confirm went through, nothing else was written.
    const items = dbItems(kbPath);
    const counts = dbCounts(kbPath);
    if (items.total !== 1) fail(`exactly the confirmed item must exist, saw ${items.total}`);
    if (counts.sources !== 1) fail(`the source must be kept once, saw ${counts.sources}`);
    process.stdout.write('stop part-way OK: one item saved, nothing half-written (real DB check)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 3: edit-then-confirm ---------------- */

async function editThenConfirm(ai) {
  process.stdout.write('--- add: edit-then-confirm ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addedit-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Decision', statement: 'Use SQLite for local storage', source_quote: 'use SQLite for local storage', confidence: 0.9 },
      ]),
    }));
    await goToAdd(win);
    await addText(win, NOTE);
    await win.waitForSelector('[data-testid="proposal"]');

    await focusPane(win);
    await win.keyboard.press('e'); // story 23: e edits
    await win.waitForSelector('[data-testid="add-edit"]');
    // Step 1 of 3: the type. Decision is preselected; pick Finding.
    await win.check('input[name="add-edit-type"][value="Finding"]');
    await win.click('[data-testid="add-edit-submit"]');
    // Step 2 of 3: the statement, prefilled with the proposal's.
    await win.waitForSelector('[data-testid="add-edit-statement"]');
    const prefilled = await win.inputValue('[data-testid="add-edit-statement"]');
    if (!/Use SQLite for local storage/.test(prefilled)) fail(`the statement editor must open prefilled: ${prefilled}`);
    await assertCleanScan(win, 'Add (edit form, statement step)');
    await win.fill('[data-testid="add-edit-statement"]', 'The database engine is SQLite, decided today');
    await win.click('[data-testid="add-edit-submit"]');
    // Step 3 of 3: the project label.
    await win.waitForSelector('[data-testid="add-edit-metadata"]');
    await win.fill('[data-testid="add-edit-metadata"]', 'auth');
    await win.click('[data-testid="add-edit-submit"]');

    // The revalidated proposal comes back as a NEW block from the engine.
    await win.waitForFunction(
      () => /The database engine is SQLite, decided today/.test((document.querySelector('[data-testid="proposal"]') ?? { textContent: '' }).textContent),
    );
    const edited = await win.textContent('[data-testid="proposal"]');
    if (!/Finding/.test(edited)) fail(`the edited type must show: ${edited.slice(0, 200)}`);
    await focusPane(win);
    await win.keyboard.press('Enter');
    await win.waitForSelector('[data-testid="add-summary-line"]');
    const summaryLine = await win.textContent('[data-testid="add-summary-line"]');
    if (!/1 item confirmed, 0 rejected/.test(summaryLine)) fail(`the edited item must be confirmed: ${summaryLine}`);
    await app.close();
    const rows = dbItemRow(kbPath);
    // The engine gives a revalidated edit a NEW id (the original draft
    // is never written), so only the edited values are pinned here.
    assert.equal(rows.length, 1, 'exactly the edited item exists');
    assert.deepEqual(
      rows[0].slice(1),
      ['Finding', 'The database engine is SQLite, decided today', 'auth', 'Active'],
      'the DB must carry the edited type, statement and label (story 21)',
    );
    process.stdout.write('edit-then-confirm OK: type + statement + metadata, DB check\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 4: zero proposals (story 28) ---------------- */

async function zeroProposals(ai) {
  process.stdout.write('--- add: zero proposals ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addzero-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({ status: 200, content: '[]' }));
    await goToAdd(win);
    await addText(win, 'A quiet note with nothing to keep in it.');
    await win.waitForSelector('[data-testid="state-empty"]');
    const empty = await win.textContent('[data-testid="state-empty"]');
    if (!/nothing to propose/i.test(empty) || !/kept as a source/.test(empty)) {
      fail(`story 28: the empty state must say so: ${empty}`);
    }
    await assertCleanScan(win, 'Add (empty, zero proposals)');
    await win.click('[data-action="add-reset-empty"]');
    await win.waitForSelector('[data-testid="add-text-input"]');
    await app.close();
    const counts = dbCounts(kbPath);
    if (counts.items !== 0) fail(`nothing may be created, saw ${counts.items} items`);
    if (counts.sources !== 1) fail(`the text must be kept as a source, saw ${counts.sources}`);
    process.stdout.write('zero proposals OK: the empty state, the text kept as a source (DB check)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 5: the message events inline (story 19) ---------------- */

async function inlineMessages(ai) {
  process.stdout.write('--- add: dropped / gatekeeper / near-duplicate messages ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addmsg-'));
  const kbPath = path.join(workDir, 'kb.db');
  seedExistingItem(kbPath, 'Our database engine is SQLite');
  const { app, win } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Note', statement: 'A note of something', source_quote: 'something', confidence: 0.5 },
        { type: 'Decision', statement: 'Quantum flux capacitor charges', source_quote: 'quantum capacitor flux', confidence: 0.5 },
        { type: 'Decision', statement: 'Our database engine is SQLite for good', source_quote: 'database engine is SQLite', confidence: 0.9 },
      ]),
    }));
    await goToAdd(win);
    await addText(win, 'Our database engine is SQLite for good. Quantum flux capacitor charges.');
    await win.waitForSelector('[data-testid="proposal"]');
    await win.waitForFunction(
      () => /dropped proposal: type/.test((document.querySelector('[data-testid="add-log"]') ?? { textContent: '' }).textContent),
    );
    const log = await win.textContent('[data-testid="add-log"]');
    if (!/dropped proposal: quote/.test(log)) fail(`the engine's second drop line must show inline: ${log}`);
    if (!/warning: near-duplicate of item 1/.test(log)) fail(`the engine's warning line must show inline: ${log}`);
    const proposal = await win.textContent('[data-testid="proposal"]');
    if (!/similar to item 1/.test(proposal)) fail(`story 19: the proposal must warn on the near duplicate: ${proposal}`);
    await assertCleanScan(win, 'Add (messages + near-duplicate warning)');
    await focusPane(win);
    await win.keyboard.press('y'); // confirm the near-duplicate anyway
    await win.waitForSelector('[data-testid="add-summary-line"]');
    const summaryLine = await win.textContent('[data-testid="add-summary-line"]');
    if (!/1 item confirmed, 0 rejected/.test(summaryLine)) fail(`the near-dup confirm: ${summaryLine}`);
    await app.close();
    const rows = dbItemRow(kbPath);
    if (rows.length !== 2) fail(`the seeded item plus one confirmed item must exist, saw ${rows.length}`);
    if (rows[1][2] !== 'Our database engine is SQLite for good') fail(`the confirmed item's statement: ${JSON.stringify(rows[1])}`);
    process.stdout.write('inline messages OK: dropped + gatekeeper + warning lines visible inline\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 6: AI unreachable (story 27) ---------------- */

async function aiUnreachable(unreachableUrl) {
  process.stdout.write('--- add: AI unreachable ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addunreach-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: unreachableUrl });
  try {
    await goToAdd(win);
    await addText(win, NOTE);
    await win.waitForSelector('[data-testid="add-error"] [data-testid="state-error"]');
    const error = await win.textContent('[data-testid="add-error"]');
    if (!/could not answer/i.test(error)) fail(`story 27: the unreachable words: ${error}`);
    // Batch 6 (chunk 5): the two facts are the text kept as a source
    // and NO ITEMS made — the untrue "nothing was created" wording was
    // corrected (the note WAS created; only its items were not).
    if (!/kept word for word/.test(error) || !/no items were made/.test(error)) {
      fail(`the two facts must be on the error: ${error}`);
    }
    if (!(await win.locator('[data-testid="state-error"] [data-action="add-retry"]').isVisible())) {
      fail('story 27: the error must offer Retry');
    }
    await assertNoBareCode(win);
    await win.locator('[data-testid="state-error"] [data-action="show-details"]').click();
    await win.waitForSelector('[data-testid="add-error"] [data-testid="error-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="add-error"] [data-testid="error-code"]');
    if (!/CAPTURE-008/.test(code)) fail(`Details must reveal the engine code, saw ${code}`);
    await assertCleanScan(win, 'Add (unreachable error state)');
    await app.close();
    const counts = dbCounts(kbPath);
    if (counts.items !== 0) fail(`nothing may be created, saw ${counts.items} items`);
    if (counts.sources !== 1) fail(`the text must survive as a source, saw ${counts.sources}`);
    process.stdout.write('AI unreachable OK: plain words, text kept, nothing created, Retry (DB check)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 7: a failed Add keeps the form (Batch 3 F2) ---------------- */

async function failKeepsForm(ai) {
  process.stdout.write('--- add: the error and the form show together ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addfail-'));
  const { app, win } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({ status: 500, content: JSON.stringify({ error: { message: 'the AI service failed' } }) }));
    await goToAdd(win);
    await addText(win, NOTE);
    await win.waitForSelector('[data-testid="add-error"] [data-testid="state-error"]');
    const error = await win.textContent('[data-testid="add-error"]');
    if (!/could not answer/i.test(error)) fail(`the CAPTURE-008 words on a failed Add: ${error}`);
    // Batch 3 F2: the draft form must come back WITH the error, the
    // box still holding the text the user sent.
    await win.waitForSelector('[data-testid="add-text-input"]');
    if (!(await win.locator('[data-testid="add-text-input"]').isVisible())) {
      fail('the draft form must be visible next to the error');
    }
    const kept = await win.inputValue('[data-testid="add-text-input"]');
    if (kept !== NOTE) fail(`the box must still hold the sent text, saw: ${kept}`);
    // Batch 3 Chunk 2 (story 3): the user edits the kept text, the AI
    // comes back, Retry must send EXACTLY what is in the box now.
    const bodiesBefore = ai.bodies.length;
    await win.fill('[data-testid="add-text-input"]', EDITED_NOTE);
    ai.set(() => ({
      status: 200,
      content: JSON.stringify([
        { type: 'Decision', statement: 'The retry sent the edited text', source_quote: 'edited note text', confidence: 0.9 },
      ]),
    }));
    await win.locator('[data-testid="state-error"] [data-action="add-retry"]').click();
    await win.waitForSelector('[data-testid="proposal"]');
    const retries = ai.bodies.slice(bodiesBefore);
    if (retries.length !== 1) fail(`Retry must send exactly one request, saw ${retries.length}`);
    if (!retries[0].includes(EDITED_NOTE)) {
      fail(`the Retry request must contain the EDITED text, got: ${retries[0].slice(0, 400)}`);
    }
    if (retries[0].includes(NOTE)) fail(`the Retry request must NOT contain the original text, got: ${retries[0].slice(0, 400)}`);
    await assertNoBareCode(win);
    await app.close();
    process.stdout.write('form kept OK: the error and the form show together, text still in the box, Retry sent the edited text\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 8: the key refused at the first Add (5-A) ---------------- */

async function keyRefused(ai) {
  process.stdout.write('--- add: the key refused at the first Add ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addrefuse-'));
  const { app, win, kbPath } = await launchApp({ workDir, aiBaseUrl: ai.url });
  try {
    ai.set(() => ({
      status: 401,
      content: JSON.stringify({ error: { message: 'Invalid or revoked API key' } }),
    }));
    await goToAdd(win);
    await addText(win, NOTE);
    await win.waitForSelector('[data-testid="add-error"] [data-testid="state-error"]');
    await win.waitForFunction(
      () => /refused the key/.test((document.querySelector('[data-testid="add-error"]') ?? { textContent: '' }).textContent),
    );
    const error = await win.textContent('[data-testid="add-error"]');
    // Batch 6 (chunk 5): the true facts — text kept as a source, no items made.
    if (!/kept word for word/.test(error) || !/no items were made/.test(error)) fail(`the refusal facts: ${error}`);
    await assertNoBareCode(win);
    await win.locator('[data-testid="state-error"] [data-action="show-details"]').click();
    await win.waitForSelector('[data-testid="add-error"] [data-testid="error-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="add-error"] [data-testid="error-code"]');
    if (!/CAPTURE-008/.test(code)) fail(`the refusal's code behind Details, saw ${code}`);
    await assertCleanScan(win, 'Add (key refused)');
    await app.close();
    const counts = dbCounts(kbPath);
    if (counts.items !== 0 || counts.sources !== 1) fail(`the refusal must leave items 0 and the source 1, saw ${JSON.stringify(counts)}`);
    process.stdout.write('key refused OK: the decision 5-A plain refusal at the first Add\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 9: no key at all (story 29) ---------------- */

async function noKeyPath(ai) {
  process.stdout.write('--- add: no key, the path to the setting ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addnokey-'));
  const { app, win } = await launchApp({ workDir, aiBaseUrl: ai.url, withKey: false });
  try {
    await win.waitForSelector('#nav');
    await win.locator('#nav button[data-job="add"]').click();
    await win.waitForSelector('[data-testid="state-no-key"]');
    const block = await win.textContent('[data-testid="state-no-key"]');
    if (!/needs the AI connection/.test(block)) fail(`story 29: the no-key words: ${block}`);
    await assertCleanScan(win, 'Add (no-key state)');
    await win.locator('[data-testid="state-no-key"] [data-action="add-open-setup"]').click();
    await win.waitForSelector('[data-testid="setup-key-input"]');
    const step = await win.textContent('.setup .sub');
    if (!/Step 2 of 2/.test(step)) fail(`the button must open the AI-connection setup step, saw: ${step}`);
    process.stdout.write('no-key OK: Add waits and points at the AI connection (story 29)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 10: a child dies mid-session ---------------- */

async function childDiesMidSession(ai) {
  process.stdout.write('--- add: a child dies mid-session ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-adddie-'));
  const { app, win, userData } = await launchApp({ workDir, aiBaseUrl: ai.url, childDies: true });
  try {
    await goToAdd(win);
    await addText(win, NOTE);
    // The stub emits one block + one prompt, then dies before reading
    // stdin: the UI must show the error, never a dangling prompt.
    await win.waitForSelector('[data-testid="add-error"] [data-testid="state-error"]');
    const error = await win.textContent('[data-testid="add-error"]');
    if (!/ended early/.test(error) || !/nothing was half-written/.test(error)) {
      fail(`the dead child must be reported as an early end: ${error}`);
    }
    const leftovers = fs.readdirSync(userData).filter((n) => n.startsWith('add-text-') && n.endsWith('.txt'));
    if (leftovers.length !== 0) fail(`the pasted-text temp file must be cleaned after the crash, saw ${JSON.stringify(leftovers)}`);
    await assertNoBareCode(win);
    await assertCleanScan(win, 'Add (child died mid-session)');
    process.stdout.write('child death OK: the error state + the temp file cleaned (deviation: stub, not a killable real child)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 11: a fake EMBER-000 death (Chunk 14) ---------------- */

async function crashReportButtons(ai) {
  process.stdout.write('--- add: EMBER-000 death, the crash report buttons ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-addcrash-'));
  const crashFile = path.join(workDir, 'state', 'ember', 'crashes', `${CRASH_ID}.txt`);
  const { app, win } = await launchApp({ workDir, aiBaseUrl: ai.url, crash: true });
  try {
    await goToAdd(win);
    await addText(win, NOTE);
    // The stub dies at once: the app must show the error state with
    // the Chunk 12 EMBER-000 sentence, never a dangling prompt.
    await win.waitForSelector('[data-testid="add-error"] [data-testid="state-error"]');
    const error = await win.textContent('[data-testid="add-error"]');
    if (!/unexpected problem happened inside Ember/i.test(error)) {
      fail(`the Chunk 12 EMBER-000 sentence must show: ${error.slice(0, 200)}`);
    }
    if (!/report was saved/i.test(error)) fail(`the crash sentence's "report was saved" fact: ${error.slice(0, 200)}`);
    await assertNoBareCode(win);
    // The two crash buttons under the error block (visible without
    // opening Details — the plain words already invite the user to
    // "copy or open the crash report").
    const copyBtn = win.locator('[data-testid="state-error"] [data-action="copy-crash"]');
    const showBtn = win.locator('[data-testid="state-error"] [data-action="show-crash-file"]');
    if (!(await copyBtn.isVisible())) fail('the "Copy crash report" button must show under Details');
    if (!(await showBtn.isVisible())) fail('the "Show file" button must show under Details');
    const copyLabel = (await copyBtn.textContent()).trim();
    const showLabel = (await showBtn.textContent()).trim();
    if (copyLabel !== 'Copy crash report') fail(`the first button must be called "Copy crash report": ${copyLabel}`);
    if (showLabel !== 'Show file') fail(`the second button must be called "Show file": ${showLabel}`);
    // Details reveals the engine code and the crash id the app took
    // from the house line; the id must be the fake file's own name.
    await win.locator('[data-testid="state-error"] [data-action="show-details"]').click();
    await win.waitForSelector('[data-testid="add-error"] [data-testid="error-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="add-error"] [data-testid="error-code"]');
    if (!/EMBER-000/.test(code) || !/InternalError/.test(code)) fail(`Details must reveal EMBER-000 InternalError, saw ${code}`);
    if (!code.includes(`crash=${CRASH_ID}`)) fail(`the shown crash id must be the fake's (${CRASH_ID}), saw ${code}`);
    // The crash file the fake wrote sits in the scenario's own
    // XDG_STATE_HOME, and its content is the crash text the screen
    // must show after Copy — compared word for word below.
    if (!fs.existsSync(crashFile)) fail(`the fake crash file must exist at ${crashFile}`);
    const fileText = fs.readFileSync(crashFile, 'utf8');
    await assertCleanScan(win, 'Add (EMBER-000 crash state)');
    // Click Copy: the visible feedback ("Copied.") and the crash text
    // itself appear; the clipboard write itself is chunk 13's unit
    // pin, never asserted here (the honest split).
    await copyBtn.click();
    await win.waitForSelector('[data-testid="add-error"] [data-testid="crash-copied"]');
    const feedback = await win.textContent('[data-testid="add-error"] [data-testid="crash-copied"]');
    if (!/Copied\./.test(feedback)) fail(`copy must say "Copied.": ${feedback}`);
    const shown = await win.textContent('[data-testid="add-error"] [data-testid="crash-text"]');
    if (shown !== fileText) {
      fail(`the shown crash text must match the fake crash file word for word:\nshown:[${shown.slice(0, 160)}]\nfile:[${fileText.slice(0, 160)}]`);
    }
    process.stdout.write('crash report OK: the Chunk 12 sentence, both buttons, Copied. + the file\'s own text shown\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  const ai = await startFakeAi();
  const unreachable = await closedPortUrl();
  try {
    await fullLoopAndParity(ai);
    await stopPartWay(ai);
    await editThenConfirm(ai);
    await zeroProposals(ai);
    await inlineMessages(ai);
    await aiUnreachable(unreachable);
    await failKeepsForm(ai);
    await keyRefused(ai);
    await noKeyPath(ai);
    await childDiesMidSession(ai);
    await crashReportButtons(ai);
  } finally {
    ai.server.close();
  }
  process.stdout.write('e2e add OK: all eleven scenarios green (real ember child, fake AI server on EMBER_AI_BASE_URL)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e add FAILED: ${err.message}\n`);
  process.exit(1);
});

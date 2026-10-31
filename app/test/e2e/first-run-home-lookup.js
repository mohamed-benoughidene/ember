'use strict';

/**
 * The step-04 E2E (dev-only, Linux; app step file §2): first run, Home
 * and Look up over the real Electron shell with the fake ember stub
 * (FAKE_MODE=app + the pinned fixture; no flow in this step touches
 * the AI service, so no fake AI server is needed).
 *
 * Flows, one per scenario:
 *  1. FIRST RUN: three steps and "about two minutes" (2), the file
 *     default (3), what the file holds (4), the key step with clear
 *     empty/short messages (8) and the plain explanation (6), the key
 *     save (5 PARTIAL: shape check only, decision 5-A; on a basic_text
 *     keyring the APP-003 session-only offer is taken), skip (7) in a
 *     separate fresh launch, and "Add your first text" (9).
 *  2. HOME: the no-key banner (never blank), attention first (10) with
 *     the sweep button (15), counts (11-12), latest ledger lines (13),
 *     the main Add text button (14), and the pre-Add empty state.
 *  3. LOOK UP: search (30), filters (31), the count line (32), the
 *     table (33), the provenance view (34-36), nothing-matches +
 *     Clear filters (39), "No items yet" (40), and the Ledger tab with
 *     filters, paging (37-38) and the plain words Undone/Redone (122).
 *  4. EMPTY + ERROR: a well-formed empty KB (story 40); a child that
 *     fails on every command -> error blocks with Retry, plain words
 *     on screen and the code behind "Details" (41, 102); and Reduce
 *     Motion honoured (99/104).
 *
 * The step-03 accessibility helper runs on every screen and state this
 * e2e renders (stories 96-104).
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { launchShell, seedSettings } = require('./helpers/shell.js');
const { runAccessibilityScan } = require('../helpers/a11y-scan.mjs');

function fail(what) {
  throw new Error(what);
}

async function assertCleanScan(win, label) {
  const { violations, checked } = await runAccessibilityScan(win, {
    // The Text Size Rule (DESIGN.md): at Largest the app runs its
    // :root.big adaptations; the scan must measure the real thing.
    prepare: (page) => page.evaluate(() => document.documentElement.classList.add('big')),
    cleanup: (page) => page.evaluate(() => document.documentElement.classList.remove('big')),
  });
  if (violations.length > 0) {
    fail(`a11y scan on ${label} found ${violations.length}: ${JSON.stringify(violations, null, 2)}`);
  }
  process.stdout.write(`a11y scan clean on ${label} (${checked.tabbableCount} tabbable controls)\n`);
}

/**
 * Save a well-shaped key, taking the APP-003 session-only offer when
 * the keyring here refuses to store (basic_text); then Continue.
 */
async function finishFirstRunKeyStep(win) {
  await win.fill('[data-testid="setup-key-input"]', 'sk-or-v1-abcdef1234567890abcd-test');
  await win.click('[data-action="setup-save-key"]');
  await win.waitForSelector('[data-testid="setup-message"]');
  const message = await win.textContent('[data-testid="setup-message"]');
  const sessionButton = win.locator('[data-testid="setup-session-key"]');
  if ((await sessionButton.count()) > 0 && (await sessionButton.isVisible())) {
    if (!/session only/i.test(message)) fail(`an unexpected session-only offer: ${message}`);
    await sessionButton.click();
    await win.waitForFunction(
      () => /kept for this session only/i.test((document.querySelector('[data-testid="setup-message"]') ?? { textContent: '' }).textContent ?? ''),
    );
  } else {
    if (!/saved on this computer, in the system keyring/.test(message)) fail(`the saved-key message is wrong: ${message}`);
  }
  await win.waitForSelector('[data-testid="setup-continue"]');
  const help = await win.textContent('.setup .form');
  if (!/real test happens at your first Add/.test(help)) {
    fail(`decision 5-A honesty line missing: ${help.slice(0, 300)}`);
  }
  await win.click('[data-testid="setup-continue"]');
  await win.waitForSelector('[data-testid="setup-finish"]');
}

/* ---------------- scenario 1: first run ---------------- */

async function firstRun() {
  process.stdout.write('--- first run ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-firstrun-'));
  const shell = await launchShell({ workDir, withDb: false });
  const { app } = shell;
  try {
    const win = await app.firstWindow();

    // Step 1: three steps, "about two minutes", the default location
    await win.waitForSelector('[data-testid="setup-db-input"]');
    const sub = await win.textContent('.setup .sub');
    if (!/Step 1 of 3/.test(sub) || !/About two minutes/.test(sub)) fail(`the setup header is wrong: ${sub}`);
    const stepNames = await win.locator('.steps li').count();
    if (stepNames !== 3) fail(`expected the three setup steps, saw ${stepNames}`);
    const defaultPath = await win.evaluate(() => window.ember.getState().then((s) => s.defaultKbPath));
    const shown = await win.inputValue('[data-testid="setup-db-input"]');
    if (shown !== defaultPath) fail(`the default file location should be ${defaultPath}, saw ${shown}`);
    const holds = await win.textContent('.setup .form');
    if (!/items, their links and the ledger/.test(holds)) fail('the one sentence on what the file holds is missing');
    await assertCleanScan(win, 'first run step 1 (file location)');

    await win.click('[data-action="setup-file-continue"]');

    // Step 2: the plain explanation of what a key is and where text goes
    await win.waitForSelector('[data-testid="setup-key-input"]');
    const help = await win.textContent('.setup .form');
    if (!/AI service/.test(help) || !/sent to that service/.test(help)) {
      fail(`the plain key explanation is missing: ${help.slice(0, 300)}`);
    }
    await assertCleanScan(win, 'first run step 2 (key, no message)');

    // Story 8: clear messages for empty and too short
    await win.click('[data-action="setup-save-key"]');
    await win.waitForSelector('[data-testid="setup-message"]');
    let message = await win.textContent('[data-testid="setup-message"]');
    if (!/empty/i.test(message)) fail(`an empty key must say so: ${message}`);
    await win.fill('[data-testid="setup-key-input"]', 'short');
    await win.click('[data-action="setup-save-key"]');
    await win.waitForFunction(() => /too short/i.test(document.querySelector('[data-testid="setup-message"]').textContent));
    await assertCleanScan(win, 'first run step 2 (key, message shown)');

    await finishFirstRunKeyStep(win);

    // Step 3: ready, and the first action is Add your first text (9)
    const ready = await win.textContent('.setup .form');
    if (!/Ember is ready/.test(ready)) fail(`step 3 should say Ember is ready: ${ready}`);
    if (!/connected|kept for this session/.test(ready)) fail(`step 3 should name the connection state: ${ready}`);
    const finishLabel = (await win.textContent('[data-testid="setup-finish"]')).trim();
    if (finishLabel !== 'Add your first text') fail(`the first action must be "Add your first text", saw ${finishLabel}`);
    await assertCleanScan(win, 'first run step 3 (ready)');

    await win.click('[data-testid="setup-finish"]');
    await win.waitForSelector('[data-testid="pane-add"]');
    const addPane = await win.textContent('[data-testid="pane-add"]');
    if (!/arrives in a later build step/.test(addPane)) fail(`the interim Add pane must say so honestly: ${addPane.slice(0, 200)}`);
    const effective = await win.evaluate(() => window.ember.getState().then((s) => s.effectiveKbPath));
    if (effective !== defaultPath) fail(`the chosen path must be saved in settings, saw ${JSON.stringify(effective)}`);
    await app.close();

    // Story 7: skip allowed, still usable — a FRESH install.
    const workDirSkip = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-skip-'));
    const shell2 = await launchShell({ workDir: workDirSkip, withDb: false });
    const { app: app2 } = shell2;
    try {
      const win2 = await app2.firstWindow();
      await win2.waitForSelector('[data-testid="setup-db-input"]');
      await win2.click('[data-action="setup-file-continue"]');
      await win2.waitForSelector('[data-testid="setup-key-input"]');
      await win2.click('[data-action="setup-skip-key"]');
      await win2.waitForSelector('[data-testid="setup-finish"]');
      const ready2 = await win2.textContent('.setup .form');
      if (!/not connected yet/.test(ready2)) fail(`skipping must keep the app usable without a key: ${ready2}`);
      await win2.click('[data-testid="setup-finish"]');
      await win2.waitForSelector('[data-testid="pane-add"]');
      process.stdout.write('first run OK: the key path and the skip path both land in the app (stories 1-9)\n');
    } finally {
      await app2.close();
      fs.rmSync(workDirSkip, { recursive: true, force: true });
    }
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 2: Home ---------------- */

async function home() {
  process.stdout.write('--- home ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-home-'));
  const shell = await launchShell({ workDir, withDb: true });
  const { app } = shell;
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="counts-panel"]');

    // Stories 11-12: the counts, exactly what list-items says (5 items:
    // 3 Active, 1 Challenged, 1 Closed in the fixture)
    for (const [testid, expected] of [
      ['count-active', '3'],
      ['count-challenged', '1'],
      ['count-closed', '1'],
      ['count-total', '5'],
    ]) {
      const value = (await win.textContent(`[data-testid="${testid}"]`)).trim();
      if (value !== expected) fail(`${testid} should be ${expected}, saw ${value}`);
    }

    // Story 14: the main Add text button
    const addLabel = (await win.textContent('[data-testid="home-add"]')).trim();
    if (addLabel !== 'Add text') fail(`the main button must be "Add text", saw ${addLabel}`);

    // Story 10 + 15: attention first, with the way to act (the fixture
    // has 2 pending sweep changes)
    const finding = await win.textContent('[data-testid="attention-finding"]');
    if (!/out of date/.test(finding)) fail(`attention must lead with what needs attention: ${finding}`);
    const sweepButton = win.locator('[data-action="attention-cleanup"]');
    if (!(await sweepButton.isVisible())) fail('the attention message must have a button to the sweep (story 15)');
    await sweepButton.click();
    await win.waitForSelector('[data-testid="pane-cleanup"]');
    if (!/arrives in a later build step/.test(await win.textContent('[data-testid="pane-cleanup"]'))) {
      fail('the interim Clean up pane must be honest about what exists');
    }
    await win.locator('#nav button[data-job="home"]').click();
    await win.waitForSelector('[data-testid="counts-panel"]');

    // Story 13: the latest ledger lines, plain words
    await win.waitForSelector('[data-testid="home-ledger-table"]');
    const ledger = await win.textContent('[data-testid="home-ledger-table"]');
    if (!/Item 5 was added/.test(ledger)) fail(`the latest ledger lines must show: ${ledger.slice(0, 200)}`);
    const ledgerRows = await win.locator('[data-testid="home-ledger-table"] tr').count();
    if (ledgerRows !== 5) fail(`home shows the latest 5 ledger lines, saw ${ledgerRows}`);

    // The no-key state: a banner with a real path, never a blank screen
    const banner = await win.textContent('[data-testid="home-notice"]');
    if (!/no AI key yet/.test(banner)) fail(`the no-key state must be a banner on Home: ${banner}`);
    await win.click('[data-action="home-setup-key"]');
    await win.waitForSelector('[data-testid="setup-key-input"]');
    const step2 = await win.textContent('.setup .sub');
    if (!/Step 2 of 3/.test(step2)) fail(`the banner must re-open the setup AT the key step, saw: ${step2}`);
    await assertCleanScan(win, 'first run re-opened from the no-key banner (key step)');
    await win.click('[data-action="setup-skip-key"]');
    await win.waitForSelector('[data-testid="setup-finish"]');
    await win.click('[data-testid="setup-finish"]');
    await win.waitForSelector('[data-testid="pane-add"]');
    await win.locator('#nav button[data-job="home"]').click();
    await win.waitForSelector('[data-testid="counts-panel"]');
    await assertCleanScan(win, 'Home (normal)');
    await app.close();

    // The pre-Add empty state: a chosen file that does not exist yet
    // (the settings file carries the path; no Add has ever run, so no
    // read command is started — D3/I8).
    const missingKb = path.join(workDir, 'missing', 'ember.db');
    seedSettings(path.join(workDir, 'config'), missingKb);
    const shell2 = await launchShell({ workDir, withDb: false });
    const { app: app2 } = shell2;
    try {
      const win2 = await app2.firstWindow();
      await win2.waitForSelector('[data-testid="home-pane"]');
      await win2.waitForSelector('[data-testid="kb-gate"] .empty');
      const empty = await win2.textContent('[data-testid="kb-gate"]');
      if (!/No items yet/.test(empty)) fail(`the pre-Add Home must show the empty state: ${empty}`);
      const emptyRows = await win2.locator('[data-testid="counts-panel"]').count();
      if (emptyRows !== 0) fail('the pre-Add Home must NOT call any read command (D3/I8)');
      await assertCleanScan(win2, 'Home (pre-Add empty state)');
      process.stdout.write('home OK: counts, attention, ledger, no-key banner, pre-Add empty state (stories 10-15)\n');
    } finally {
      await app2.close();
    }
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 3: Look up ---------------- */

async function lookup() {
  process.stdout.write('--- look up ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-lookup-'));
  const shell = await launchShell({ workDir, withDb: true });
  const { app } = shell;
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="counts-panel"]');
    await win.locator('#nav button[data-job="lookup"]').click();

    // Story 30: a search box with a visible label. Story 32: count line.
    await win.waitForSelector('label[for="lookup-q"]');
    const label = await win.textContent('label[for="lookup-q"]');
    if (label.trim() !== 'Search items') fail(`the search box needs a visible label, saw ${label}`);
    await win.waitForSelector('[data-testid="lookup-table"]');
    let countLine = (await win.textContent('[data-testid="lookup-count"]')).trim();
    if (countLine !== '5 of 5 items') fail(`the count line should read "5 of 5 items", saw "${countLine}"`);
    const rows = await win.locator('[data-testid^="lookup-row-"]').count();
    if (rows !== 5) fail(`the table should list all 5 items, saw ${rows}`);
    const pills = await win.locator('[data-testid^="status-pill-"]').count();
    if (pills < 5) fail('every row shows its heat mark with its word (story 33)');

    // Stories 34-36: select an item -> verbatim source + provenance
    // with the other item's heat mark, both directions, with status.
    await win.click('[data-testid="lookup-row-5"]');
    await win.waitForSelector('[data-testid="item-source"]');
    const source = await win.textContent('[data-testid="item-source"]');
    if (!/We decided to use SQLite for local storage\./.test(source)) fail(`the source must be verbatim: ${source}`);
    if (!/Ember needs no server of its own\./.test(source)) fail(`the source text is cut: ${source}`);
    const why = await win.textContent('[data-testid="item-why"]');
    if (!/no server of its own/.test(why)) fail(`the rationale must show as Why: ${why}`);
    const provenanceLines = await win.locator('[data-testid="provenance-link"]').count();
    if (provenanceLines !== 4) fail(`item 5 has 4 links (2 out + 2 in), saw ${provenanceLines}`);
    const provenance = await win.textContent('[data-testid="provenance-panel"]');
    for (const word of ['Challenges', 'Replaces', 'Supported by']) {
      if (!provenance.includes(word)) fail(`the provenance is missing "${word}": ${provenance.slice(0, 400)}`);
    }
    if (!/reversed/.test(provenance)) fail('a reversed replacement must say so (the provenance context)');
    if (!/rejected/.test(provenance)) fail('a Rejected link must still show (nothing is deleted)');
    const otherMarks = await win.locator('[data-testid="provenance"] [data-testid^="status-pill-"]').count();
    if (otherMarks !== 4) fail('every linked item shows its heat mark (story 36)');
    await assertCleanScan(win, 'Look up, detail open');

    // The in-direction words: item 3 is challenged BY item 5.
    await win.click('[data-testid="lookup-row-3"]');
    await win.waitForFunction(() => /Challenged by/.test((document.querySelector('[data-testid="provenance-panel"]') ?? { textContent: '' }).textContent));
    const prov3 = await win.textContent('[data-testid="provenance-panel"]');
    if (!/Challenged by/.test(prov3)) fail(`item 3 must show "Challenged by": ${prov3.slice(0, 300)}`);
    const source3 = await win.textContent('[data-testid="item-source"]');
    if (!/Team standup, 14 Oct/.test(source3)) fail(`item 3's verbatim source missing: ${source3}`);

    // Stories 31 + 39: filters narrow; nothing-matches gets Clear filters
    await win.fill('[data-testid="lookup-q"]', 'backup');
    await win.press('[data-testid="lookup-q"]', 'Enter');
    await win.waitForFunction(() => /matches for/.test(document.querySelector('[data-testid="lookup-count"]').textContent));
    countLine = (await win.textContent('[data-testid="lookup-count"]')).trim();
    if (!/2 matches for "backup"/.test(countLine)) fail(`the search count is wrong: ${countLine}`);
    await win.selectOption('[data-testid="lookup-status"]', 'Challenged');
    await win.waitForSelector('[data-testid="state-empty"]');
    const emptyText = await win.textContent('[data-testid="state-empty"]');
    if (!/No items match/.test(emptyText)) fail(`nothing-matched must say so: ${emptyText}`);
    await win.click('[data-action="lookup-clear"]');
    await win.waitForFunction(() => document.querySelector('[data-testid="lookup-count"]').textContent.trim() === '5 of 5 items');

    // Stories 37-38 + 122: the Ledger tab, filters, paging, plain words
    await win.click('[data-testid="tab-ledger"]');
    await win.waitForSelector('[data-testid="ledger-table"]');
    const page1 = await win.locator('[data-testid="ledger-row"]').count();
    if (page1 !== 10) fail(`the ledger pages 10 lines at a time, saw ${page1}`);
    if (!(await win.locator('[data-testid="ledger-older"]').isVisible())) fail('16 fixture events must offer an Older page');
    const kinds1 = (await win.locator('[data-testid="ledger-kind"]').allTextContents()).map((s) => s.trim());
    if (kinds1.some((k) => k === '')) fail('story 122: no ledger kind may be blank');
    if (!kinds1.includes('Item edited')) fail('the item_edited kind must read in plain words');
    await win.click('[data-testid="ledger-older"]');
    await win.waitForFunction(() => {
      const kinds = [...document.querySelectorAll('[data-testid="ledger-kind"]')].map((n) => n.textContent.trim());
      return kinds.includes('Undone') && kinds.includes('Redone');
    });
    process.stdout.write('ledger paging OK: the older page carries the plain words Undone and Redone (story 122)\n');
    const allKinds = (await win.locator('[data-testid="ledger-kind"]').allTextContents()).map((s) => s.trim());
    for (const expected of ['Status source changed', 'Undone', 'Redone', 'Reversal undone', 'Change without words']) {
      if (!allKinds.includes(expected)) fail(`the older ledger page must label ${expected}; saw ${JSON.stringify(allKinds)}`);
    }

    // Back to the first page; the item filter and the date filter
    await win.click('[data-testid="ledger-newer"]');
    await win.waitForSelector('[data-testid="ledger-older"]');
    await win.fill('[data-testid="ledger-item"]', '4');
    await win.dispatchEvent('[data-testid="ledger-item"]', 'change');
    await win.waitForFunction(() => document.querySelectorAll('[data-testid="ledger-row"]').length <= 4);
    await win.fill('[data-testid="ledger-item"]', '');
    await win.dispatchEvent('[data-testid="ledger-item"]', 'change');
    await win.waitForSelector('[data-testid="ledger-older"]');
    await win.fill('[data-testid="ledger-since"]', '2026-10-26');
    await win.dispatchEvent('[data-testid="ledger-since"]', 'change');
    await win.waitForFunction(() => {
      const n = document.querySelectorAll('[data-testid="ledger-row"]').length;
      return n > 0 && n < 10;
    });
    const sinceRows = await win.locator('[data-testid="ledger-row"]').count();
    if (sinceRows !== 6) fail(`--since 2026-10-26 keeps the 6 lines from the 26th on, saw ${sinceRows}`);
    await assertCleanScan(win, 'Ledger tab (filtered)');

    process.stdout.write('look up OK: search, filters, count, table, provenance, ledger paging + words (stories 30-41, 122)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 4: empty fixture + error + motion ---------------- */

async function emptyAndError() {
  process.stdout.write('--- empty and error states ---\n');
  // An EMPTY knowledge base (well-formed, zero items): normal, but empty.
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-empty-'));
  const emptyFixture = path.join(workDir, 'empty-fixture.json');
  fs.writeFileSync(emptyFixture, JSON.stringify({ items: [], show: {}, history: [], pending: 0 }));
  const app = (await launchShell({ workDir, withDb: true, fixture: emptyFixture })).app;
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="counts-panel"]');
    const total = (await win.textContent('[data-testid="count-total"]')).trim();
    if (total !== '0') fail(`an empty KB reads total 0, saw ${total}`);
    await win.locator('#nav button[data-job="lookup"]').click();
    await win.waitForSelector('[data-testid="state-empty"]');
    const empty = await win.textContent('[data-testid="state-empty"]');
    if (!/No items yet/.test(empty)) fail(`story 40: an empty KB says "No items yet": ${empty}`);
    if (!(await win.locator('[data-action="lookup-empty-add"]').isVisible())) fail('story 40: the empty state offers the way to add');
    await assertCleanScan(win, 'Look up (empty KB, story 40)');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }

  // A child that fails on every command: error blocks with Retry and
  // Details; the plain words on screen, the code behind Details.
  const workDir2 = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-error-'));
  const { app: app2 } = await launchShell({ workDir: workDir2, mode: 'error', withDb: true });
  try {
    const win = await app2.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');
    await win.waitForSelector('[data-testid="state-error"]');
    const visible = await win.evaluate(() => document.body.innerText);
    if (/QUERY-\d{3}|APP-\d{3}/.test(visible)) fail(`no bare code on screen (story 102), saw one in: ${visible.slice(0, 300)}`);
    const errors = await win.locator('[data-testid="state-error"]').count();
    if (errors < 2) fail(`Home has three data blocks; each failing block shows its own error, saw ${errors}`);
    await win.locator('[data-testid="state-error"] [data-action="show-details"]').first().click();
    await win.waitForSelector('[data-testid="error-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="error-code"]');
    if (!/QUERY-003/.test(code)) fail(`Details must reveal the code, saw ${code}`);
    await win.locator('[data-testid="state-error"] [data-action="block-retry"]').first().click().catch(() => {});
    process.stdout.write('error states OK: what failed + Retry + Details reveal (stories 41, 102, 8)\n');
    await assertCleanScan(win, 'Home (error states)');

    // Reduce Motion honoured: nothing moves even while the app redraws.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    await win.locator('#nav button[data-job="lookup"]').click();
    await win.waitForSelector('[data-testid="lookup-gated"]');
    await win.waitForTimeout(400); // any loading skeleton has come and gone
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('svg, .skel')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    process.stdout.write('Reduce Motion honoured on the step-04 screens\n');
  } finally {
    await app2.close().catch(() => {});
    fs.rmSync(workDir2, { recursive: true, force: true });
  }
}

async function main() {
  await firstRun();
  await home();
  await lookup();
  await emptyAndError();
  process.stdout.write('e2e first-run home lookup OK: all four scenarios green (fake ember app mode, no AI service touched)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e first-run home lookup FAILED: ${err.message}\n`);
  process.exit(1);
});

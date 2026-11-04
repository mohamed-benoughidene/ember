'use strict';

// [shortcut graveyard fix] Boots here must not really register the global
// shortcut — every real bind left a stale KDE portal entry on the founder's
// machine. Nothing in this file asserts registration; the scenarios that do
// (popup.js, settings.js) opt out explicitly.
process.env.EMBER_APP_SHORTCUT_REFUSED ??= '1';

/**
 * The step-04 E2E (dev-only, Linux; app step file §2): first run, Home
 * and Look up over the real Electron shell with the fake ember stub
 * (FAKE_MODE=app + the pinned fixture; no flow in this step touches
 * the AI service, so no fake AI server is needed).
 *
 * Flows, one per scenario:
 *  1. FIRST RUN: two steps and "about two minutes" (2, Batch 6: the
 *     "Ready" step is gone — Skip and Continue go straight to finish),
 *     the file default (3), what the file holds (4), a refused file
 *     leaving the PREVIOUS path in the input (F7c: checked before it
 *     is saved), the key step with clear empty/short messages (8) and
 *     the plain explanation (6), the key save (5 PARTIAL: shape check
 *     only, decision 5-A; on a basic_text keyring the APP-003
 *     session-only offer is taken), skip (7) in a separate fresh
 *     launch, and the first action is the real Add pane (9).
 *  2. HOME: the no-key banner (never blank), attention first (10) with
 *     the sweep button (15), counts (11-12), latest ledger lines (13),
 *     the main Add text button (14), and the pre-Add empty state.
 *  3. LOOK UP: search (30), filters (31), the count line (32), the
 *     table (33), the provenance view (34-36), nothing-matches +
 *     Clear filters (39), "No items yet" (40), and the Ledger tab with
 *     filters, paging (37-38, newest first per Batch 6) and plain words
 *     on every page (122).
 *  3b. SEARCH PAGING (Batch 6 chunk 7): a 60-match base at 50 a page
 *     shows the page and total numbers in the search header and pages
 *     through the matches with the pager buttons (4.7 #5).
 *  4. EMPTY + ERROR: a well-formed empty KB (story 40); Home's grouped
 *     failure notices (Batch 3 F4, decision B3-1): one notice per error
 *     code replaces the per-block cards, the count as a bare number and
 *     the code on the notice (I7), the code behind Details (102), and
 *     Try again reloading every block; and Reduce Motion honoured
 *     (99/104).
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
  // Batch 6: two steps — "Continue" goes straight to finish (the app).
  await win.click('[data-testid="setup-continue"]');
}

/* ---------------- scenario 1: first run ---------------- */

async function firstRun() {
  process.stdout.write('--- first run ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-firstrun-'));
  const shell = await launchShell({ workDir, withDb: false });
  const { app } = shell;
  try {
    const win = await app.firstWindow();

    // Step 1: two steps, "about two minutes", the default location
    await win.waitForSelector('[data-testid="setup-db-input"]');
    const sub = await win.textContent('.setup .sub');
    if (!/Step 1 of 2/.test(sub) || !/About two minutes/.test(sub)) fail(`the setup header is wrong: ${sub}`);
    const stepNames = await win.locator('.steps li').count();
    if (stepNames !== 2) fail(`expected the two setup steps, saw ${stepNames}`);
    const defaultPath = await win.evaluate(() => window.ember.getState().then((s) => s.defaultKbPath));
    const shown = await win.inputValue('[data-testid="setup-db-input"]');
    if (shown !== defaultPath) fail(`the default file location should be ${defaultPath}, saw ${shown}`);
    const holds = await win.textContent('.setup .form');
    if (!/items, their links and the ledger/.test(holds)) fail('the one sentence on what the file holds is missing');
    await assertCleanScan(win, 'first run step 1 (file location)');

    // F7c: a refused file (an existing non-Ember file picked) shows the
    // refusal and leaves the PREVIOUS path in the input — and never
    // reaches the settings.
    const notEmber = path.join(workDir, 'not-ember.txt');
    fs.writeFileSync(notEmber, 'a plain text file that is no knowledge base', 'utf8');
    await win.fill('[data-testid="setup-db-input"]', notEmber);
    await win.click('[data-action="setup-file-continue"]');
    await win.waitForSelector('[data-testid="setup-message"]');
    const refused = await win.textContent('[data-testid="setup-message"]');
    if (!/not an Ember knowledge base/.test(refused)) fail(`a non-Ember file must be refused: ${refused}`);
    const kept = await win.inputValue('[data-testid="setup-db-input"]');
    if (kept !== defaultPath) fail(`a refused file must leave the previous path in the input, saw ${kept}`);
    await assertCleanScan(win, 'first run step 1 (refused file)');

    await win.click('[data-action="setup-file-continue"]');

    // Step 2: the plain explanation of what a key is and where text goes
    await win.waitForSelector('[data-testid="setup-key-input"]');
    const help = await win.textContent('.setup .form');
    if (!/AI service/.test(help) || !/sent to that service/.test(help)) {
      fail(`the plain key explanation is missing: ${help.slice(0, 300)}`);
    }
    await assertCleanScan(win, 'first run step 2 (key, no message)');

    // Batch 6 (D-14, F7d): exactly ONE key input per screen, the eye
    // toggle INSIDE the field (aria-label "Show key"/"Hide key"), and
    // NO separate Show/Hide button beside it.
    const keyInputs = await win.locator('[data-testid="setup-key-input"]').count();
    if (keyInputs !== 1) fail(`exactly one key input expected on first run, saw ${keyInputs}`);
    const eyeField = '.key-field:has([data-testid="setup-key-input"])';
    const eyeShow = win.locator(`${eyeField} button[aria-label="Show key"]`);
    if ((await eyeShow.count()) !== 1) {
      fail(`the key field needs exactly one eye toggle inside it (aria-label "Show key"), saw ${await eyeShow.count()}`);
    }
    await eyeShow.click();
    await win.waitForSelector(`${eyeField} button[aria-label="Hide key"]`);
    if ((await win.getAttribute('[data-testid="setup-key-input"]', 'type')) !== 'text') {
      fail('after the eye toggle the key input must be plain text');
    }
    await win.click(`${eyeField} button[aria-label="Hide key"]`);
    await win.waitForSelector(`${eyeField} button[aria-label="Show key"]`);
    if ((await win.getAttribute('[data-testid="setup-key-input"]', 'type')) !== 'password') {
      fail('after hiding, the key input must be masked again');
    }
    const setupButtons = (await win.locator('.setup button').allTextContents()).map((t) => t.trim());
    if (setupButtons.includes('Show') || setupButtons.includes('Hide')) {
      fail(`no separate Show/Hide button may sit beside the key field (F7d), saw: ${JSON.stringify(setupButtons)}`);
    }
    process.stdout.write('key field OK (first run): one box, the eye toggle inside with Show key/Hide key, no separate Show/Hide button\n');

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

    // Continue (or Skip) lands STRAIGHT in the app (Batch 6: no "Ready"
    // step). Story 9: the first action is the real Add pane.
    await win.waitForSelector('[data-testid="add-pane"]');
    await win.waitForSelector('[data-testid="add-text-input"]');
    const notice = await win.textContent('[data-testid="add-notice"]');
    if (!/kept word for word/.test(notice) || !/sent to the AI service/.test(notice)) {
      fail(`the real Add pane must open from first run with its notice: ${notice.slice(0, 200)}`);
    }
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
      // Batch 6: two steps — "Skip for now" goes straight to finish:
      // the app lands on the Add pane with its honest no-key state.
      await win2.click('[data-action="setup-skip-key"]');
      await win2.waitForSelector('[data-testid="add-pane"]'); /* App 05: real Add pane */
      await win2.waitForSelector('[data-testid="state-no-key"]');
      const noKey = await win2.textContent('[data-testid="state-no-key"]');
      if (!/needs the AI connection/.test(noKey)) fail(`skipping must keep the app usable without a key: ${noKey}`);
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
    // --- App 08 (Clean up, ticket A37): the real screen replaces the
    // interim pane this file pinned before; the assertion now pins the
    // real screen's honest idle state (story 65: Apply off until a
    // preview is shown, with the why on the control). ---
    if (!/Preview first, then apply/.test(await win.textContent('[data-testid="pane-cleanup"]'))) {
      fail('the real Clean up screen must open from the attention button');
    }
    const applyBtn = win.locator('[data-testid="cleanup-apply"]');
    if (!(await applyBtn.isDisabled())) fail('story 65: Apply must stay off before a preview');
    if (!/Preview the sweep first/.test((await applyBtn.getAttribute('title')) ?? '')) {
      fail('story 103: the disabled Apply must say why (its title)');
    }
    // --- App 08 assertion ends ---
    await win.locator('#nav button[data-job="home"]').click();
    await win.waitForSelector('[data-testid="counts-panel"]');

    // Story 13: the latest ledger lines, plain words. The engine renders
    // the ledger NEWEST first (Batch 6), so the latest 5 lines are the
    // most recent writes: the newest fixture line (the 10-30T08:40 event)
    // is on top and the OLDEST line (item 5's 10-01 creation) is NOT here.
    await win.waitForSelector('[data-testid="home-ledger-table"]');
    const ledger = await win.textContent('[data-testid="home-ledger-table"]');
    if (!/2026-10-30T08:40/.test(ledger)) fail(`the latest ledger lines must start at the newest write, saw: ${ledger.slice(0, 200)}`);
    if (/2026-10-01T10:02/.test(ledger)) fail(`the latest 5 lines must not reach back to the oldest write, saw: ${ledger.slice(0, 200)}`);
    const ledgerRows = await win.locator('[data-testid="home-ledger-table"] tr').count();
    if (ledgerRows !== 5) fail(`home shows the latest 5 ledger lines, saw ${ledgerRows}`);

    // The no-key state: a banner with a real path, never a blank screen
    const banner = await win.textContent('[data-testid="home-notice"]');
    if (!/no AI key yet/.test(banner)) fail(`the no-key state must be a banner on Home: ${banner}`);
    await win.click('[data-action="home-setup-key"]');
    await win.waitForSelector('[data-testid="setup-key-input"]');
    const step2 = await win.textContent('.setup .sub');
    if (!/Step 2 of 2/.test(step2)) fail(`the banner must re-open the setup AT the key step, saw: ${step2}`);
    await assertCleanScan(win, 'first run re-opened from the no-key banner (key step)');
    // Batch 6: two steps — "Skip for now" goes straight to finish.
    await win.click('[data-action="setup-skip-key"]');
    await win.waitForSelector('[data-testid="add-pane"]'); /* App 05: real Add pane */
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
    // Batch 6: the count line shows the page number beside the pre-page
    // total; both are 2 here.
    if (!/2 of 2 matches for "backup"/.test(countLine)) fail(`the search count is wrong: ${countLine}`);
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
    // The ledger renders NEWEST first (Batch 6): the first page holds the
    // most recent lines (the 10-30T08:40 "no words" event is page 1) and
    // the OLDEST lines (the two 10-01/10-03 "Added" events) are NOT here.
    if (!kinds1.includes('Change without words')) fail('the newest event (no-words edit) must be on the first page');
    if (kinds1.includes('Added')) fail('the oldest events must not be on the newest-first first page');
    await win.click('[data-testid="ledger-older"]');
    await win.waitForFunction(() => {
      const kinds = [...document.querySelectorAll('[data-testid="ledger-kind"]')].map((n) => n.textContent.trim());
      // Walking the offset forward walks BACK in time: the older page
      // carries the earliest lines, among them the two Added events and
      // the 10-20 item edit (story 122: plain words on every page).
      return kinds.includes('Added') && kinds.includes('Item edited');
    });
    process.stdout.write('ledger paging OK: the older page walks back in time (Added, Item edited) — story 122\n');
    const allKinds = (await win.locator('[data-testid="ledger-kind"]').allTextContents()).map((s) => s.trim());
    // The older page holds the OLDEST fixture lines: the two status moves,
    // the 10-20 item edit, the 10-14 link confirm and the two creations.
    for (const expected of ['Status changed', 'Item edited', 'Link confirmed', 'Added']) {
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

/* ---------------- scenario 3b: search paging (Batch 6, 4.7 #5) ---------------- */

async function searchPaging() {
  process.stdout.write('--- search paging: a 60-match base at 50 a page ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-searchpage-'));
  // 60 items whose statements share one word: the search total (60) is
  // bigger than one page (50), so the header must show both numbers and
  // the pager must reach the remaining 10.
  const items = Array.from({ length: 60 }, (_, i) => ({
    id: i + 1,
    type: 'Decision',
    statement: `Widget note ${i + 1} for the search page.`,
    status: 'Active',
    close_reason: null,
    rationale: null,
    source: null,
    validated: null,
    created_at: '2026-10-03T09:00:00+00:00',
  }));
  const fixture = path.join(workDir, 'sixty.json');
  fs.writeFileSync(fixture, JSON.stringify({ items, show: {}, history: [], pending: 0 }));
  const shell = await launchShell({ workDir, withDb: true, fixture });
  const { app } = shell;
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="counts-panel"]');
    await win.locator('#nav button[data-job="lookup"]').click();
    await win.waitForSelector('[data-testid="lookup-q"]');
    await win.fill('[data-testid="lookup-q"]', 'widget');
    await win.press('[data-testid="lookup-q"]', 'Enter');
    await win.waitForSelector('[data-testid="lookup-table"]');
    // Numbers and elements only, never the header wording (I10).
    const firstHeader = (await win.textContent('[data-testid="lookup-count"]')).trim();
    if (!/\b50\b/.test(firstHeader) || !/\b60\b/.test(firstHeader)) {
      fail(`the search header must show the page number 50 and the total 60, saw: ${firstHeader}`);
    }
    const firstRows = await win.locator('[data-testid^="lookup-row-"]').count();
    if (firstRows !== 50) fail(`the first search page holds 50 rows, saw ${firstRows}`);
    if (!(await win.locator('[data-testid="page-older"]').isVisible())) {
      fail('60 matches at 50 a page must offer the next page');
    }
    await win.click('[data-testid="page-older"]');
    await win.waitForFunction(() => {
      const rows = document.querySelectorAll('[data-testid^="lookup-row-"]').length;
      return rows === 10;
    });
    const secondHeader = (await win.textContent('[data-testid="lookup-count"]')).trim();
    if (!/\b60\b/.test(secondHeader)) fail(`the last search page must still show the total 60, saw: ${secondHeader}`);
    await assertCleanScan(win, 'Look up (search paging, 60 matches)');
    process.stdout.write('search paging OK: 50 of 60 on page one, 10 more on page two (Batch 6 chunk 7)\n');
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

  // ---- Batch 3 F4: ONE notice per error code on Home (B3-1) --------
  // Round (a): every engine-fed block fails with ONE code (mode
  // `error` -> QUERY-003 everywhere). Exactly ONE grouped notice, no
  // per-block error cards left, the count 3 as a bare number next to
  // the code (I7), the code behind Details, and Try again reloading
  // every block (the spawn log's new lines name the reads again).
  const workDir2 = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-error-'));
  const spawnLog = path.join(workDir2, 'spawn.log');
  const { app: app2 } = await launchShell({
    workDir: workDir2,
    mode: 'error',
    withDb: true,
    extraEnv: { FAKE_SPAWN_LOG: spawnLog },
  });
  /** The fake-ember spawn log: one JSON line (its argv) per spawn. */
  const spawnCommands = (fromLine) =>
    fs
      .readFileSync(spawnLog, 'utf8')
      .split('\n')
      .filter((line) => line.trim() !== '')
      .slice(fromLine)
      .map((line) => JSON.parse(line)[0]);
  try {
    const win = await app2.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');
    // All three block loaders have settled (their loading skeletons are
    // gone — failed, empty or served).
    await win.waitForFunction(
      () => {
        const hosts = ['attention', 'home-counts', 'home-ledger'].map((t) => document.querySelector(`[data-testid="${t}"]`));
        return hosts.length === 3 && hosts.every((h) => h && h.querySelectorAll('.skel').length === 0);
      },
      { timeout: 20000 },
    );

    // Exactly ONE notice, carrying the code and the count as a bare
    // number (decision I7: number + code only, never "N blocks" words).
    const seenNotices = await win.locator('[data-testid="home-failure-notice"]').count();
    if (seenNotices !== 1) fail(`one notice expected, saw ${seenNotices}`);
    const noticeText = await win.textContent('[data-testid="home-failure-notice"]');
    if (!/QUERY-003/.test(noticeText)) fail(`the notice must name QUERY-003, saw: ${noticeText}`);
    if (!/\b3\b/.test(noticeText)) fail(`the QUERY-003 notice must carry the count 3 as a number, saw: ${noticeText}`);

    // The notice replaces the cards: zero error cards inside the three
    // engine-fed block hosts (decision B3-1).
    const blockCards = await win.evaluate(() =>
      ['attention', 'home-counts', 'home-ledger'].map(
        (host) => document.querySelectorAll(`[data-testid="${host}"] [data-testid="state-error"]`).length,
      ),
    );
    if (blockCards.some((n) => n !== 0)) fail(`the grouped notice replaces the block cards (B3-1), still saw cards ${JSON.stringify(blockCards)}`);

    // No bare code on screen (story 102): the code lives behind Details.
    const visibleBeforeDetails = await win.evaluate(() => document.body.innerText);
    if (/QUERY-\d{3}|APP-\d{3}/.test(visibleBeforeDetails)) {
      fail(`no bare code on screen (story 102), saw one in: ${visibleBeforeDetails.slice(0, 300)}`);
    }

    // Details reveals the code.
    await win.locator('[data-testid="home-failure-notice"] [data-action="show-details"]').click();
    const roundADetail = await win.textContent('[data-testid="home-failure-notice"] [data-testid="error-code"]');
    if (!/QUERY-003/.test(roundADetail)) fail(`Details must reveal QUERY-003 on the notice, saw: ${roundADetail}`);
    await assertCleanScan(win, 'Home (one grouped failure notice)');

    // Try again reloads EVERY block, not one block (decision B3-1):
    // the spawn log's NEW lines must again name the reads the failing
    // Home load issues — `list-items` (attention AND counts) and
    // `history` (the ledger). NOTE: `current-state` and `maintain` can
    // never appear here: loadAttention stops at its FIRST failed call
    // (home.mjs loadAttention), so it never reaches them — true today
    // AND in the batch-3 notice design (verified against the real
    // spawn log; the plan's expected four commands do not occur).
    const linesBeforeRetry = spawnCommands(0).length;
    await win.locator('[data-testid="home-failure-notice"] [data-action="home-failures-retry"]').click();
    const retryDeadline = Date.now() + 15000;
    let newCommands = [];
    while (Date.now() < retryDeadline) {
      newCommands = spawnCommands(linesBeforeRetry);
      const names = new Set(newCommands);
      if (names.has('list-items') && names.has('history')) break;
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    for (const cmd of ['list-items', 'history']) {
      if (!newCommands.includes(cmd)) {
        fail(`Try again must reload every block (B3-1): the new spawn lines must include ${cmd}, saw ${JSON.stringify(newCommands)}`);
      }
    }
    process.stdout.write('home grouping OK (a): one notice, count 3, no cards, Try again reloads every block\n');

    // Round (b): TWO codes. FAKE_APP_FAIL makes `list-items` fail with
    // QUERY-003 (-> attention AND counts) and `history` fail with
    // QUERY-005 (-> the ledger). Exactly two notices — one per code —
    // with the counts 2 and 1 as bare numbers (I7), and Details revealing
    // each notice's own code.
    // Its OWN throwaway directory: the story-8 single-instance lock
    // ties one lock to one profile, so a third shell launched into
    // workDir2 while app2 still runs would exit at boot. launchShell
    // seeds everything it needs inside the directory, so a fresh one
    // is a fully independent shell (like every other scenario here).
    const workDir3 = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-error-b-'));
    const { app: app3 } = await launchShell({
      workDir: workDir3,
      mode: 'app',
      withDb: true,
      extraEnv: { FAKE_APP_FAIL: 'list-items:QUERY-003,history:QUERY-005' },
    });
    try {
      const win = await app3.firstWindow();
      await win.waitForSelector('[data-testid="home-pane"]');
      await win.waitForFunction(
        () => {
          const hosts = ['attention', 'home-counts', 'home-ledger'].map((t) => document.querySelector(`[data-testid="${t}"]`));
          return hosts.length === 3 && hosts.every((h) => h && h.querySelectorAll('.skel').length === 0);
        },
        { timeout: 20000 },
      );
      const roundBNotices = win.locator('[data-testid="home-failure-notice"]');
      const roundBCount = await roundBNotices.count();
      if (roundBCount !== 2) fail(`two notices expected, saw ${roundBCount}`);
      const roundBTexts = [await roundBNotices.nth(0).textContent(), await roundBNotices.nth(1).textContent()];
      const namingQ3 = roundBTexts.filter((text) => text.includes('QUERY-003'));
      const namingQ5 = roundBTexts.filter((text) => text.includes('QUERY-005'));
      if (namingQ3.length !== 1) fail(`exactly one notice must name QUERY-003, saw ${namingQ3.length} of: ${JSON.stringify(roundBTexts)}`);
      if (namingQ5.length !== 1) fail(`exactly one notice must name QUERY-005, saw ${namingQ5.length} of: ${JSON.stringify(roundBTexts)}`);
      if (namingQ3[0] === namingQ5[0]) fail(`the two codes need two separate notices (B3-1), one notice read: ${namingQ3[0]}`);
      if (!/\b2\b/.test(namingQ3[0])) fail(`the QUERY-003 notice must carry the count 2 as a number, saw: ${namingQ3[0]}`);
      if (!/\b1\b/.test(namingQ5[0])) fail(`the QUERY-005 notice must carry the count 1 as a number, saw: ${namingQ5[0]}`);
      const visibleBeforeDetailsB = await win.evaluate(() => document.body.innerText);
      if (/QUERY-\d{3}|APP-\d{3}/.test(visibleBeforeDetailsB)) {
        fail(`no bare code on screen (story 102), saw one in: ${visibleBeforeDetailsB.slice(0, 300)}`);
      }
      for (let i = 0; i < roundBCount; i += 1) {
        const notice = roundBNotices.nth(i);
        const text = await notice.textContent();
        const code = text.includes('QUERY-003') ? 'QUERY-003' : 'QUERY-005';
        await notice.locator('[data-action="show-details"]').click();
        const detail = await notice.locator('[data-testid="error-code"]').textContent();
        if (!detail.includes(code)) fail(`Details must reveal ${code} on its own notice, saw: ${detail}`);
      }
      await assertCleanScan(win, 'Home (two grouped failure notices)');
      process.stdout.write('home grouping OK (b): two notices, counts 2 and 1\n');

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
      await app3.close().catch(() => {});
      fs.rmSync(workDir3, { recursive: true, force: true });
    }
  } finally {
    await app2.close().catch(() => {});
    fs.rmSync(workDir2, { recursive: true, force: true });
  }
}

async function main() {
  await firstRun();
  await home();
  await lookup();
  await searchPaging();
  await emptyAndError();
  process.stdout.write('e2e first-run home lookup OK: all five scenarios green (fake ember app mode, no AI service touched)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e first-run home lookup FAILED: ${err.message}\n`);
  process.exit(1);
});

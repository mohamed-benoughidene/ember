'use strict';

/**
 * The step-07 E2E (dev-only, Linux; app step file §2): Fix and close
 * with Undo and Redo over the real Electron shell and a REAL temp
 * knowledge base seeded by the Python test harness. Nothing in this
 * step touches the AI service (every Fix and close command runs
 * without a key, docs/commands.md), so no fake AI server is needed.
 *
 * Flows:
 *  1. MAIN FLOW on one seeded KB: pick from the list (49); status
 *     buttons with their disabled reasons (50/103); verified on an
 *     Assumption and off elsewhere with the reason (52/53); edit the
 *     rationale with a preview (54/55); the close preview with the
 *     dependent count and list from the dry-run (56-58); the final
 *     confirmation naming the item, with a working Cancel (59); the
 *     plain confirming sentence after every change (62); Undo/Redo by
 *     button AND by Ctrl(+Shift)+Z, labelled from the dry-run plan
 *     (111-114); undoing the close restores the dependent too (115);
 *     remove a link -> Rejected, never deleted, then undo that (60,
 *     117); the story-119 note; the heat mark settles on change;
 *     Closed items show story 51's reason; the a11y helper scans.
 *  2. REVERSE A REPLACEMENT (61) on the superseded seed.
 *  3. REFUSAL PATH (118): a sweep changed the touched item since ->
 *     plain refusal words with Try again, the code behind Details.
 *  4. AN EMPTY KB: the empty state with a way to add; Reduce Motion.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { _electron } = require('playwright');
const { APP_ROOT, REPO_ROOT, PYTHON } = require('../util');
const { runAccessibilityScan } = require('../helpers/a11y-scan.mjs');

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');

function py(code) {
  execFileSync(PYTHON, ['-c', code], { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] });
}

function ember(args) {
  return execFileSync(EMBER, args, { encoding: 'utf8' });
}

function itemStatus(dbPath, id) {
  return JSON.parse(ember(['show-item', '--item', String(id), '--db', dbPath])).item.status;
}

/* ---------------- the knowledge bases ---------------- */

/** The main-flow KB: items 1-4, confirmed link 1: item 2 depends_on 1. */
function seedMainKb(dbPath) {
  py(`from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_source, insert_link_with_confirmation
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
conn = open_maintain_database(${JSON.stringify(dbPath)})
sid = insert_source(conn, full_text='We decided to use SQLite for local storage. Ember needs no server of its own.')
insert_item(conn, source_id=sid, item_id=1, item_type='Decision', statement='Use SQLite for local storage.', rationale='Ember needs no server of its own.')
insert_item(conn, source_id=sid, item_id=2, item_type='Decision', statement='Copy the database before every upgrade.')
insert_item(conn, source_id=sid, item_id=3, item_type='Assumption', statement='The team works offline most days.')
insert_item(conn, source_id=sid, item_id=4, item_type='Finding', statement='The report names page 3.', source='p. 3 of the report')
insert_link_with_confirmation(conn, 2, 1, 'depends_on')
conn.commit(); conn.close()
`);
}

/** Story 61's KB (the bridge harness seed): item 1 closed as superseded. */
function seedSupersededKb(dbPath) {
  py(`from tests.bridge import harness; harness.seed_superseded(${JSON.stringify(dbPath)})`);
}

/** Story 118's KB: item 5 Challenged, item 1 a Finding, no links yet. */
function seedRefusalKb(dbPath) {
  py(`from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_source
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
conn = open_maintain_database(${JSON.stringify(dbPath)})
sid = insert_source(conn)
insert_item(conn, source_id=sid, item_id=1, item_type='Finding', statement='Source finding.')
insert_item(conn, source_id=sid, item_id=5, item_type='Decision', statement='The contradicted call.', status='Challenged')
conn.commit(); conn.close()
`);
}

/** A well-formed but empty KB. */
function seedEmptyKb(dbPath) {
  py(`from ember.adapters.sqlite import open_maintain_database
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
open_maintain_database(${JSON.stringify(dbPath)}).close()
`);
}

/* ---------------- the launcher ---------------- */

async function launch({ workDir, dbPath, lastPane = 'fix' }) {
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
        lastPane,
        knowledgeBasePath: dbPath,
      },
      null,
      2,
    )}\n`,
  );
  const env = {
    ...process.env,
    XDG_CONFIG_HOME: configDir,
    EMBER_APP_COMMAND: EMBER,
    EMBER_APP_DB: dbPath,
  };
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  return { app };
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

async function gotoFix(win) {
  await win.locator('#nav button[data-job="fix"]').click();
  await win.waitForSelector('[data-testid="fix-pane"]');
  await win.waitForFunction(() => {
    const gated = document.querySelector('[data-testid="fix-gated"]');
    return gated !== null && gated.children.length > 0;
  });
}

async function selectItem(win, id) {
  await win.click(`[data-testid="fix-row-${id}"]`);
  await win.waitForFunction(
    (wanted) => ((document.querySelector('[data-testid="item-panel"] h2') ?? { textContent: '' }).textContent ?? '').includes(wanted),
    `Item ${id}`,
  );
}

/** One plain confirming sentence (story 62) is on screen, matching re. */
async function expectMessage(win, re) {
  try {
    await win.waitForFunction(
      (pattern) => new RegExp(pattern).test((document.querySelector('[data-testid="fix-message"]') ?? { textContent: '' }).textContent),
      re.source,
    );
  } catch (err) {
    const state = await win.evaluate(() => ({
      message: (document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: 'MISSING' }).textContent,
      error: (document.querySelector('[data-testid="fix-error"]') ?? { textContent: '' }).textContent,
    }));
    throw new Error(`expectMessage ${re} timed out; message region: ${JSON.stringify(state)}`);
  }
}

/** One refusal (plain words, story 118) is on screen, matching re. */
async function expectFixError(win, re) {
  await win.waitForFunction(
    (pattern) => new RegExp(pattern).test((document.querySelector('[data-testid="fix-error"]') ?? { textContent: '' }).textContent),
    re.source,
  );
}

/** Wait for the undo bar button of `side` to show a label with `text`. */
async function expectUndoBar(win, side, text) {
  try {
    await win.waitForFunction(
      ({ sel, wanted }) => new RegExp(wanted).test((document.querySelector(sel) ?? { textContent: '' }).textContent),
      { sel: `[data-testid="fix-${side}-btn"]`, wanted: text },
    );
  } catch (err) {
    const state = await win.evaluate(() => ({
      bar: (document.querySelector('[data-testid="undo-bar"]') ?? { textContent: 'MISSING' }).textContent,
    }));
    throw new Error(`undo bar did not show ${text}; bar: ${JSON.stringify(state)}`);
  }
}

/* ---------------- flow 1: the main flow ---------------- */

async function mainFlow() {
  process.stdout.write('--- fix and close main flow ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-fix-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    // The settle class is removed on animationend; pausing the ONE
    // motion makes the class readable deterministically (Reduce Motion
    // and the step-03 design e2e still prove the motion itself).
    await win.addStyleTag({ content: 'svg.heat, svg.heat * { animation-play-state: paused !important; }' });
    await gotoFix(win);

    // Story 49: the items come from a list, all of them, with marks.
    await win.waitForSelector('[data-testid="fix-table"]');
    const rows = await win.locator('[data-testid^="fix-row-"]').count();
    if (rows !== 4) fail(`the fix list should hold 4 items, saw ${rows}`);

    // The story-119 note is on the screen.
    const note = await win.textContent('[data-testid="undo-note"]');
    if (!/not undone by Undo/.test(note) || !/close the item/.test(note) || !/remove it below/.test(note)) {
      fail(`the story-119 note is missing or wrong: ${note}`);
    }

    // Stories 111/112/123: with no undo history yet, both buttons are
    // honestly OFF and say why (story 103).
    await win.waitForSelector('[data-testid="fix-undo-btn"][disabled]');
    await win.waitForSelector('[data-testid="fix-redo-btn"][disabled]');
    const undoReason = await win.textContent('[data-testid="undo-reason"]');
    if (!/Nothing to undo/.test(undoReason)) fail(`the disabled Undo must say why: ${undoReason}`);
    await assertCleanScan(win, 'Fix and close (list, nothing selected, undo off)');

    // Stories 50/103: the status buttons with their reasons.
    await selectItem(win, 1);
    await win.waitForSelector('[data-testid="mark-challenged"]:not([disabled])');
    if ((await win.locator('[data-testid="mark-active"][disabled]').count()) !== 1) {
      fail('Mark Active must be off while the item is already Active');
    }
    const whys = await win.textContent('[data-testid="fix-why"]');
    if (!/already Active/.test(whys) || !/assumptions only/.test(whys) || !/Source can be edited on a Finding/.test(whys)) {
      fail(`the disabled reasons (stories 51/53/55) must be visible: ${whys}`);
    }

    // Story 50 + 62 + 104: mark Challenged -> one plain confirming
    // sentence, the list re-read, and the heat mark settles on change.
    await win.click('[data-testid="mark-challenged"]');
    await expectMessage(win, /Item 1 is now Challenged\. Ember notes you set it/);
    await win.waitForFunction(
      () => document.querySelector('[data-testid="fix-row-1"] [data-testid="status-pill-challenged"]') !== null,
    );
    const settled = await win.evaluate(() => {
      const svg = document.querySelector('[data-testid="fix-row-1"] svg.heat');
      return svg ? svg.getAttribute('class') : '';
    });
    if (!/heat--settle/.test(settled)) fail(`the heat mark must settle on the change, saw class "${settled}"`);

    // Story 114 + 117: Ctrl+Z undoes the newest change, label from the plan.
    await expectUndoBar(win, 'undo', 'Undo Status change of item 1');
    await win.keyboard.press('Control+z');
    await expectMessage(win, /Undone Status change of item 1: nothing was erased/);
    await win.waitForFunction(
      () => document.querySelector('[data-testid="fix-row-1"] [data-testid="status-pill-active"]') !== null,
    );

    // ...and Shift+Ctrl+Z redoes it (story 112). Item 1 ends up
    // Challenged — the close below works from any open status.
    await expectUndoBar(win, 'redo', 'Redo Status change of item 1');
    await win.keyboard.press('Control+Shift+z');
    await expectMessage(win, /Redone Status change of item 1/);
    await win.waitForFunction(
      () => document.querySelector('[data-testid="fix-row-1"] [data-testid="status-pill-challenged"]') !== null,
    );

    // Story 52: verified on the Assumption, then cleared again. Its
    // panel also shows the rationale reason (story 55, Assumption).
    await selectItem(win, 3);
    await win.waitForSelector('[data-testid="toggle-verified"]:not([disabled])');
    await win.waitForFunction(() => /already Challenged|already Active/.test(document.querySelector('[data-testid="fix-why"]').textContent));
    const whys3 = await win.textContent('[data-testid="fix-why"]');
    if (!/Rationale can be edited on a Decision/.test(whys3) || !/Source can be edited on a Finding/.test(whys3)) {
      fail(`the edit reasons must show on the Assumption: ${whys3}`);
    }
    await win.click('[data-testid="toggle-verified"]');
    await expectMessage(win, /Item 3 is marked as verified\./);
    await win.waitForFunction(() => /\(verified\)/.test((document.querySelector('[data-testid="item-panel"]') ?? { textContent: '' }).textContent));
    await win.click('[data-testid="toggle-verified"]');
    await expectMessage(win, /verified mark on item 3 is cleared/);

    // Stories 54/55: edit the rationale of the Decision, preview first.
    await selectItem(win, 1);
    await win.waitForSelector('[data-testid="edit-rationale"]:not([disabled])');
    if ((await win.locator('[data-testid="edit-source"][disabled]').count()) !== 1) {
      fail('Edit source must be off on a Decision (story 55)');
    }
    await win.click('[data-testid="edit-rationale"]');
    await win.fill('[data-testid="edit-input"]', 'One file, no server, easy to back up.');
    await win.click('[data-testid="edit-preview-btn"]');
    await win.waitForSelector('[data-testid="edit-preview-line"]');
    const previewLine = await win.textContent('[data-testid="edit-preview-line"]');
    if (!/rationale of item 1/.test(previewLine) || !/Ember needs no server of its own\./.test(previewLine)
      || !/One file, no server/.test(previewLine) || !/Nothing has changed yet/.test(previewLine)) {
      fail(`the edit preview must show old -> new: ${previewLine}`);
    }
    await win.click('[data-testid="edit-apply"]');
    await expectMessage(win, /Saved\. The rationale of item 1 is changed; the old text stays in the ledger\./);

    // Stories 56-58: the close preview, straight from the dry-run document.
    await win.waitForSelector('[data-testid="close-reason"]');
    await win.selectOption('[data-testid="close-reason"]', 'invalidated');
    await win.click('[data-testid="close-preview-btn"]');
    await win.waitForSelector('[data-testid="close-preview"]');
    const closePreview = await win.textContent('[data-testid="close-preview"]');
    if (!/Item 1 would close as invalidated/.test(closePreview)) fail(`close preview words wrong: ${closePreview}`);
    if (!/1 item that depends on it would become Challenged: item 2\./.test(closePreview)) {
      fail(`the dependent count and list (story 57) missing: ${closePreview}`);
    }
    if (!/Nothing has changed yet/.test(closePreview)) fail('the preview must say nothing changed yet');

    // Story 59: the inline confirmation names the item, offers Cancel,
    // and Cancel really cancels.
    await win.click('[data-testid="close-ask"]');
    await win.waitForSelector('[data-testid="close-confirm"]');
    const confirm = await win.textContent('[data-testid="close-confirm"]');
    if (!/Close item 1, "Use SQLite for local storage\.\?"/.test(confirm)) fail(`the confirmation must name the item: ${confirm}`);
    if ((await win.locator('[data-testid="close-cancel"]').count()) !== 1) fail('the confirmation must offer Cancel');
    await win.click('[data-testid="close-cancel"]');
    try {
      await win.waitForFunction(() => document.querySelector('[data-testid="close-confirm"]') === null);
    } catch (err) {
      const state = await win.evaluate(() => ({
        confirm: Boolean(document.querySelector('[data-testid="close-confirm"]')),
        message: (document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent,
      }));
      throw new Error(`Cancel did not close the confirmation: ${JSON.stringify(state)}`);
    }
    if (itemStatus(dbPath, 1) !== 'Challenged') fail('Cancel must leave the item untouched');

    // Close for real: the sentence, the dependent challenged (56-59, 62).
    await win.click('[data-testid="close-ask"]');
    await win.waitForSelector('[data-testid="close-apply"]');
    await win.click('[data-testid="close-apply"]');
    await expectMessage(win, /Item 1 is closed \(invalidated\)\. Item 2 became Challenged because of it\./);
    await win.waitForFunction(
      () => document.querySelector('[data-testid="fix-row-1"] [data-testid="status-pill-closed"]') !== null,
    );

    // Story 51: the status buttons are off for the Closed item, reason shown.
    await selectItem(win, 1);
    await win.waitForFunction(() => /Already closed \(invalidated\)/.test((document.querySelector('[data-testid="item-panel"]') ?? { textContent: '' }).textContent));
    await win.waitForSelector('[data-testid="mark-active"][disabled]');
    const closedWhy = await win.textContent('[data-testid="fix-why"]');
    if (!/Closed item cannot change status/.test(closedWhy)) fail(`story 51: the Closed reason must show: ${closedWhy}`);

    // Stories 111/113/115: the button says what it will undo; undoing
    // the close restores the dependent item too (story 115); nothing
    // was erased (the ledger keeps both lines — checked on the file).
    await expectUndoBar(win, 'undo', 'Undo Close item 1');
    await win.click('[data-testid="fix-undo-btn"]');
    await expectMessage(win, /Undone Close item 1: nothing was erased/);
    try {
      // The close was made on a Challenged item, so undoing it restores
      // Challenged (the value recorded before the close), and item 2 —
      // the dependent — is Active again (story 115).
      await win.waitForFunction(
        () => document.querySelector('[data-testid="fix-row-1"] [data-testid="status-pill-challenged"]') !== null,
      );
    } catch (err) {
      const state = await win.evaluate(() => ({
        row1: (document.querySelector('[data-testid="fix-row-1"]') ?? { textContent: 'MISSING' }).textContent,
        message: (document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent,
      }));
      throw new Error(`after Undo Close item 1 the list still shows: ${JSON.stringify(state)}`);
    }
    if (itemStatus(dbPath, 2) !== 'Active') fail('undoing the close must restore the dependent item too (story 115)');
    const ledger = JSON.parse(ember(['history', '--db', dbPath]));
    const kinds = ledger.events.map((e) => e.kind);
    if (!kinds.includes('undone')) fail('the undo must be in the ledger (story 116)');

    // Story 60: remove a link — preview, confirm, Rejected not deleted.
    await selectItem(win, 2);
    await win.waitForSelector('[data-testid="unlink-1"]');
    await win.click('[data-testid="unlink-1"]');
    await win.waitForSelector('[data-testid="unlink-preview"]');
    const unlinkPreview = await win.textContent('[data-testid="unlink-preview"]');
    if (!/Link 1 would be marked Rejected/.test(unlinkPreview) || !/Nothing is deleted/.test(unlinkPreview)) {
      fail(`the removal preview must use the Reject words: ${unlinkPreview}`);
    }
    await win.waitForSelector('[data-testid="unlink-confirm"]');
    await win.click('[data-testid="unlink-apply"]');
    await expectMessage(win, /Link 1 is removed: marked Rejected, never deleted\./);
    try {
      await win.waitForFunction(() => /\(rejected\)/.test((document.querySelector('[data-testid="fix-links"]') ?? { textContent: '' }).textContent));
    } catch (err) {
      const state = await win.evaluate(() => ({
        panel: (document.querySelector('[data-testid="item-panel"]') ?? { textContent: 'MISSING' }).textContent.slice(0, 300),
        message: (document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent,
      }));
      throw new Error(`after remove-link the panel shows: ${JSON.stringify(state)}`);
    }
    // Undo the removal too (the undo covers remove-link), via the bar.
    await expectUndoBar(win, 'undo', 'Undo Removal of link 1');
    await win.click('[data-testid="fix-undo-btn"]');
    await expectMessage(win, /Undone Removal of link 1: nothing was erased/);
    try {
      await win.waitForFunction(() => /\(confirmed\)/.test((document.querySelector('[data-testid="fix-links"]') ?? { textContent: '' }).textContent));
    } catch (err) {
      const state = await win.evaluate(() => ({
        panel: (document.querySelector('[data-testid="item-panel"]') ?? { textContent: 'MISSING' }).textContent.slice(0, 300),
        message: (document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent,
      }));
      throw new Error(`after undoing the removal the panel shows: ${JSON.stringify(state)}`);
    }

    await assertCleanScan(win, 'Fix and close (item selected, after states exercised)');
    process.stdout.write('main flow OK: stories 49-62 and 111-119 exercised on a real KB\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 2: reverse a replacement (story 61) ---------------- */

async function reverseFlow() {
  process.stdout.write('--- reverse a replacement (story 61) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-reverse-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedSupersededKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    // Same deterministic settle read as the main flow.
    await win.addStyleTag({ content: 'svg.heat, svg.heat * { animation-play-state: paused !important; }' });
    await gotoFix(win);
    await selectItem(win, 2);
    await win.waitForSelector('[data-testid="reverse-1"]');
    await win.click('[data-testid="reverse-1"]');
    await expectMessage(win, /Replacement undone: item 1 is Active again\. Ember keeps the link on record\./);
    await win.waitForFunction(
      () => document.querySelector('[data-testid="fix-row-1"] [data-testid="status-pill-active"]') !== null,
    );
    // The heat mark settles on the reversal-driven status change too
    // (step file §1: the mark settles on every status change, undo included).
    const settled = await win.evaluate(() => {
      const svg = document.querySelector('[data-testid="fix-row-1"] svg.heat');
      return svg ? svg.getAttribute('class') : '';
    });
    if (!/heat--settle/.test(settled)) fail(`the reversal must settle the mark, saw "${settled}"`);
    process.stdout.write('reverse flow OK (story 61)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 3: the refusal path (story 118) ---------------- */

async function refusalFlow() {
  process.stdout.write('--- refusal after a sweep (story 118) ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-refusal-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedRefusalKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await gotoFix(win);

    // Through the app: set-status Challenged -> Active (the shield).
    await selectItem(win, 5);
    await win.click('[data-testid="mark-active"]');
    await expectMessage(win, /Item 5 is now Active\./);

    // A newer contradicts link + the sweep challenge the item again;
    // both done by the terminal here, exactly as a user mixing tools would.
    py(`from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_link_with_confirmation
conn = open_maintain_database(${JSON.stringify(dbPath)})
insert_link_with_confirmation(conn, 1, 5, 'contradicts', created_at='2999-01-01T00:00:00+00:00')
conn.commit(); conn.close()
`);
    ember(['maintain', '--db', dbPath]);
    if (itemStatus(dbPath, 5) !== 'Challenged') fail('the sweep must re-challenge the touched item');

    // Reopen the pane so the bar re-derives: the plan is refused now
    // (MAINTAIN-025), the button stays usable with its hint line.
    await win.locator('#nav button[data-job="home"]').click();
    await win.waitForSelector('[data-testid="home-pane"]');
    await gotoFix(win);
    await win.waitForSelector('[data-testid="undo-bar-hint"]');
    const hint = await win.textContent('[data-testid="undo-bar-hint"]');
    if (!/refused/.test(hint) || !/changed since/.test(hint)) fail(`the bar hint must say the undo is refused: ${hint}`);

    // The click shows the story-118 refusal: plain words, Try again,
    // the code only behind Details (no bare code on screen, story 102).
    await win.click('[data-testid="fix-undo-btn"]');
    await expectFixError(win, /At least one item or link this undo would restore has changed since/);
    const visible = await win.evaluate(() => document.body.innerText);
    if (/MAINTAIN-\d{3}/.test(visible)) fail(`no bare code on screen (story 102): ${visible.slice(0, 200)}`);
    await win.click('[data-testid="fix-error-details"]');
    await win.waitForSelector('[data-testid="error-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="error-code"]');
    if (!/MAINTAIN-025 UndoRefused/.test(code)) fail(`Details must reveal the code, saw ${code}`);
    await assertCleanScan(win, 'Fix and close (refusal state)');
    process.stdout.write('refusal flow OK (stories 118, 102)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- flow 4: empty KB + Reduce Motion ---------------- */

async function emptyAndMotion() {
  process.stdout.write('--- empty KB and Reduce Motion ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-fixempty-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedEmptyKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await gotoFix(win);
    await win.waitForSelector('[data-testid="state-empty"]');
    const empty = await win.textContent('[data-testid="state-empty"]');
    if (!/No items yet/.test(empty)) fail(`an empty KB says so with a way forward: ${empty}`);
    if (!(await win.locator('[data-action="fix-empty-add"]').isVisible())) fail('the empty state offers the way to add');
    await assertCleanScan(win, 'Fix and close (empty KB)');

    // Reduce Motion: nothing animates even while the app redraws.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    await win.locator('#nav button[data-job="lookup"]').click();
    await win.waitForSelector('[data-testid="lookup-gated"]');
    await gotoFix(win);
    await win.waitForTimeout(400); // any loading skeleton has come and gone
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('svg, .skel')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    process.stdout.write('empty + Reduce Motion OK\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  await mainFlow();
  await reverseFlow();
  await refusalFlow();
  await emptyAndMotion();
  process.stdout.write('e2e fix-close-undo OK: all flows green on real temp knowledge bases (no AI involved)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e fix-close-undo FAILED: ${err.message}\n`);
  process.exit(1);
});

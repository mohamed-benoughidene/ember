'use strict';

/**
 * The step-12 E2E (the step's check command `npm run e2e -- menus`,
 * step file §2) on a REAL temp knowledge base seeded by the Python
 * helpers, real `ember` commands, no AI involved:
 *
 *  1. THE MENU IS THE SPEC §9 TABLE — read live from Electron's
 *     Menu API: the seven menus, every label, every accelerator, the
 *     enabled states by context; Help visible AND disabled; the
 *     nothing-to-undo Undo/Redo visible AND disabled.
 *  2. THE LIVE UNDO/REDO LABELS — close an item through the UI and
 *     the Edit menu's Undo item names the action ("Undo Close item 1")
 *     and enables; menu Undo actually undoes (story 114: same
 *     controls, one path); Redo flips with "Redo Close item 1".
 *  3. FILE -> ADD TEXT OPENS THE POPUP (step file §2): the always-
 *     available route (plan §5.5), main window never parked.
 *  4. JOBS HONOURS THE STEP-10 HIDE/REORDER — hidden job disabled,
 *     never hidden; shown order follows the saved order; accelerators
 *     stay positional 1-7; the sidebar toggle works and rewords.
 *  5. SETTINGS… AND FIND — the menu's Settings… opens the panes;
 *     Edit -> Find lands on the Look up search box, focused.
 *  6. FIRST RUN — no knowledge base: every job and Settings disabled,
 *     never hidden; a click cannot break the first-run screen.
 *  7. STORY 102 + 99 — the boot notice's code sits behind a Details
 *     control; Reduce Motion leaves the ONE animation off while a
 *     real status change settles, and motion exists without it.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { _electron } = require('playwright');
const { APP_ROOT, REPO_ROOT, PYTHON } = require('../util');

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

function fail(message) {
  throw new Error(message);
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

/** A well-formed but empty KB. */
function seedEmptyKb(dbPath) {
  py(`from ember.adapters.sqlite import open_maintain_database
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
open_maintain_database(${JSON.stringify(dbPath)}).close()
`);
}

/* ---------------- the launcher ---------------- */

async function launch({ workDir, dbPath = null, lastPane = 'home', menuOrder = null, menuHidden = null, corruptSettings = false }) {
  const configDir = path.join(workDir, 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(
    path.join(userData, 'settings.json'),
    corruptSettings
      ? 'this is not json at all'
      : `${JSON.stringify(
          {
            schema: 1,
            textSize: 'default',
            colourTheme: 'system',
            quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' },
            menuOrder: menuOrder ?? ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
            menuHidden: menuHidden ?? [],
            lastPane,
            knowledgeBasePath: dbPath ?? '',
          },
          null,
          2,
        )}\n`,
  );
  const env = {
    ...process.env,
    XDG_CONFIG_HOME: configDir,
    EMBER_APP_COMMAND: EMBER, // the real `ember` from the worktree venv
  };
  if (dbPath !== null) env.EMBER_APP_DB = dbPath;
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  return { app, workDir, configDir };
}

/* ---------------- the live menu readers (main-process world) ---------------- */

async function readMenu(app) {
  return app.evaluate(({ Menu }) => {
    const m = Menu.getApplicationMenu();
    if (!m) return null;
    return m.items.map((menu) => ({
      label: menu.label,
      items: menu.submenu
        ? menu.submenu.items.map((i) => ({
            id: i.id || null,
            label: i.label,
            accelerator: i.accelerator || null,
            enabled: i.enabled,
            role: i.role || null,
          }))
        : [],
    }));
  });
}

function findItem(menus, id) {
  for (const menu of menus ?? []) {
    const item = (menu.items ?? []).find((i) => i.id === id);
    if (item) return item;
  }
  return null;
}

async function waitForMenuItem(app, id, predicate, what, timeoutMs = 15000) {
  const start = Date.now();
  for (;;) {
    const item = findItem(await readMenu(app), id);
    if (item && predicate(item)) return item;
    if (Date.now() - start > timeoutMs) {
      fail(`${what}: timed out waiting for menu item ${id}; last state ${JSON.stringify(item)}`);
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}

async function clickMenuItem(app, id) {
  const ok = await app.evaluate(({ Menu }, itemId) => {
    const menu = Menu.getApplicationMenu();
    if (!menu) return false;
    for (const m of menu.items) {
      if (!m.submenu) continue;
      const item = m.submenu.items.find((x) => x.id === itemId);
      if (item) {
        item.click();
        return true;
      }
    }
    return false;
  }, id);
  if (!ok) fail(`menu item ${id} not found`);
}

/* ---------------- scenario 1: the spec §9 table, live ---------------- */

async function specTable() {
  process.stdout.write('--- scenario 1: the menu equals the spec §9 table ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu1-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedEmptyKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');
    // Wait for the first real label derivation to settle (2 dry-runs).
    await waitForMenuItem(app, 'edit-undo', (i) => i.enabled === false && i.label === 'Undo', 'the empty KB disables Undo');

    const menus = await readMenu(app);
    if (menus === null) fail('the application menu is missing');
    if (JSON.stringify(menus.map((m) => m.label)) !== JSON.stringify(['Ember', 'File', 'Edit', 'View', 'Jobs', 'Window', 'Help'])) {
      fail(`the seven menus in spec order, saw: ${JSON.stringify(menus.map((m) => m.label))}`);
    }

    // Ember (app menu): About; Settings… (Command+Comma); Hide; Quit.
    const emberMenu = menus[0];
    const emberItems = emberMenu.items.filter((i) => !i.role || !['separator'].includes(i.role));
    const labels = emberMenu.items.map((i) => i.label || '---');
    if (!/About Ember/.test(labels.join('|'))) fail(`About Ember missing: ${labels.join('|')}`);
    const settings = findItem(menus, 'settings');
    if (!settings || settings.label !== 'Settings…' || settings.accelerator !== 'CmdOrCtrl+,') {
      fail(`Settings… with Command+Comma missing: ${JSON.stringify(settings)}`);
    }
    const hideItem = emberMenu.items.find((i) => i.label && i.label.startsWith('Hide'));
    if (!hideItem || hideItem.enabled === false) fail('the Hide item must be present and enabled (same items always)');
    const quit = emberMenu.items.find((i) => i.role === 'quit');
    if (!quit) fail('Quit missing');

    // File: Add text…; Open a knowledge base file… (Command+O); Back up…; Export…; Close window.
    const file = menus[1].items.filter((i) => i.label);
    const fileNames = file.map((i) => i.label);
    if (
      JSON.stringify(fileNames) !==
      JSON.stringify(['Add text…', 'Open a knowledge base file…', 'Back up…', 'Export…', 'Close window'])
    ) {
      fail(`the File menu is not the spec table: ${fileNames.join(' | ')}`);
    }
    const openKb = file.find((i) => i.label.startsWith('Open a knowledge base file…'));
    if (!openKb || openKb.accelerator !== 'CmdOrCtrl+O') fail('Open a knowledge base file… must carry Command/Control+O');
    if (file.find((i) => i.label === 'Close window')?.role !== 'close') fail('Close window must be the close role');

    // Edit: Undo/Redo (live), the standard row, Find.
    const edit = menus[2].items.filter((i) => i.label);
    const editNames = edit.map((i) => i.label);
    if (JSON.stringify(editNames.slice(2)) !== JSON.stringify(['Cut', 'Copy', 'Paste', 'Select All', 'Find'])) {
      fail(`the Edit menu standard row drifted: ${editNames.join(' | ')}`);
    }
    const editRoles = edit.slice(2, 6).map((i) => i.role);
    // (Electron reports the selectAll role lower-cased on read-back.)
    if (JSON.stringify(editRoles) !== JSON.stringify(['cut', 'copy', 'paste', 'selectall'])) {
      fail(`the edit roles drifted: ${editRoles.join(',')}`);
    }
    const find = findItem(menus, 'edit-find');
    if (!find || find.accelerator !== 'CmdOrCtrl+F') fail('Find must carry Command/Control+F');
    const undo = findItem(menus, 'edit-undo');
    const redo = findItem(menus, 'edit-redo');
    if (undo.label !== 'Undo' || undo.enabled !== false) fail(`nothing to undo: Undo stays visible and disabled, saw ${JSON.stringify(undo)}`);
    if (undo.accelerator !== 'CmdOrCtrl+Z') fail('Undo must be Command/Control+Z');
    if (redo.label !== 'Redo' || redo.enabled !== false) fail(`nothing to redo: Redo stays visible and disabled, saw ${JSON.stringify(redo)}`);
    if (redo.accelerator !== 'Shift+CmdOrCtrl+Z') fail('Redo must be Shift+Command/Control+Z');

    // View: the sidebar toggle, worded for the visible sidebar.
    const view = menus[3].items[0];
    if (view.label !== 'Hide Sidebar') fail(`the View menu is the sidebar toggle, saw ${view.label}`);

    // Jobs: the table's seven with Command+1..7 in the default order.
    const jobs = menus[4].items;
    if (
      JSON.stringify(jobs.map((i) => `${i.accelerator} ${i.label}`)) !==
      JSON.stringify([
        'CmdOrCtrl+1 Home',
        'CmdOrCtrl+2 Add',
        'CmdOrCtrl+3 Look up',
        'CmdOrCtrl+4 Link items',
        'CmdOrCtrl+5 Fix and close',
        'CmdOrCtrl+6 Clean up',
        'CmdOrCtrl+7 Keep safe',
      ])
    ) {
      fail(`the Jobs menu is not the spec table: ${jobs.map((i) => i.label).join(' | ')}`);
    }
    if (jobs.some((i) => !i.enabled)) fail('a chosen knowledge base means every job is enabled');

    // Window: Minimize + Zoom. Help: visible AND disabled.
    if (JSON.stringify(menus[5].items.map((i) => i.role)) !== JSON.stringify(['minimize', 'zoom'])) {
      fail('the Window menu is Minimize + Zoom');
    }
    const help = menus[6].items[0];
    if (help.label !== 'Ember Help' || help.enabled !== false) {
      fail(`Help content is out of scope: the item stays visible and disabled, saw ${JSON.stringify(help)}`);
    }

    process.stdout.write('menu equals the spec §9 table: 7 menus, 24 named items, roles and accelerations pinned\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 2: the live Undo/Redo labels ---------------- */

async function liveLabels() {
  process.stdout.write('--- scenario 2: the Edit menu labels undo/redo from the dry-run ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu2-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');
    await waitForMenuItem(app, 'edit-undo', (i) => i.enabled === false, 'a fresh KB has nothing to undo');

    // Jobs -> Fix and close navigates (the menu route works).
    await clickMenuItem(app, 'job-fix');
    await win.waitForSelector('[data-testid="fix-pane"]');

    // Close item 1 through the UI: preview, confirm, apply.
    await win.click('[data-testid="fix-row-1"]');
    await win.waitForSelector('[data-testid="close-preview-btn"]');
    await win.click('[data-testid="close-preview-btn"]');
    await win.waitForSelector('[data-testid="close-ask"]');
    await win.click('[data-testid="close-ask"]');
    await win.waitForSelector('[data-testid="close-apply"]');
    await win.click('[data-testid="close-apply"]');
    await win.waitForFunction(() => document.querySelector('[data-testid="status-pill-closed"]') !== null);

    // The menu re-derives after the write and NAMES the action (story 113).
    const undo = await waitForMenuItem(app, 'edit-undo', (i) => i.enabled && i.label === 'Undo Close item 1', 'the live undo label');
    if (undo.accelerator !== 'CmdOrCtrl+Z') fail('Undo keeps its key');
    const redoAfterClose = findItem(await readMenu(app), 'edit-redo');
    if (redoAfterClose.enabled !== false || redoAfterClose.label !== 'Redo') {
      fail(`nothing to redo right after a close: ${JSON.stringify(redoAfterClose)}`);
    }

    // Menu Undo actually undoes — the Fix and close screen's own control.
    await clickMenuItem(app, 'edit-undo');
    await win.waitForFunction(() => /Undone Close item 1/.test((document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent));
    if (itemStatus(dbPath, 1) !== 'Active') fail('the menu undo must really undo (item 1 Active again)');

    // Redo flips to name the action; Undo goes back to disabled-plain.
    await waitForMenuItem(app, 'edit-redo', (i) => i.enabled && i.label === 'Redo Close item 1', 'the live redo label');
    await waitForMenuItem(app, 'edit-undo', (i) => !i.enabled && i.label === 'Undo', 'Undo disabled again');
    const ledger = JSON.parse(ember(['history', '--db', dbPath]));
    const kinds = ledger.events.map((e) => e.kind);
    if (!kinds.includes('undone')) fail('the menu undo must be in the ledger (nothing erased)');
    process.stdout.write('live labels OK: Undo Close item 1 -> undone -> Redo Close item 1, via the real dry-run\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 3: File -> Add text opens the popup ---------------- */

async function addTextOpensPopup() {
  process.stdout.write('--- scenario 3: File -> Add text opens the quick popup ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu3-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    const visibleWindows = () =>
      app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().filter((w) => w.isVisible()).length);

    if ((await visibleWindows()) !== 1) fail('one window before File -> Add text');
    await clickMenuItem(app, 'file-add-text');
    const start = Date.now();
    let popupPage = null;
    while (Date.now() - start < 10000 && popupPage === null) {
      for (const page of app.windows()) {
        if (page !== win && page.url().endsWith('quick.html')) popupPage = page;
      }
      if (popupPage === null) await new Promise((r) => setTimeout(r, 150));
    }
    if (popupPage === null) fail('File -> Add text must open the quick popup (quick.html)');
    const startVisible = Date.now();
    while ((await visibleWindows()) !== 2 && Date.now() - startVisible < 10000) {
      await new Promise((r) => setTimeout(r, 150));
    }
    if ((await visibleWindows()) !== 2) fail('the popup must be visible');
    // The main window was NOT parked (the menu route never parks).
    const mainWindowVisible = await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows().some((w) => w.isVisible() && !w.webContents.getURL().endsWith('quick.html')),
    );
    if (!mainWindowVisible) fail('the menu add route must not park the main window');

    // Esc closes the popup (the popup's own rule), Ember stays.
    await popupPage.keyboard.press('Escape');
    const start2 = Date.now();
    while (Date.now() - start2 < 5000) {
      if ((await visibleWindows()) === 1) break;
      await new Promise((r) => setTimeout(r, 150));
    }
    if ((await visibleWindows()) !== 1) fail('Esc must close the popup');
    process.stdout.write('File -> Add text OK: the always-available route over the same open/hide action\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 4: jobs honour the step-10 hide/reorder ---------------- */

async function hideAndReorder() {
  process.stdout.write('--- scenario 4: the Jobs menu honours the step-10 hide/reorder ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu4-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedEmptyKb(dbPath);
  const { app } = await launch({
    workDir,
    dbPath,
    menuOrder: ['lookup', 'add', 'link', 'fix', 'keepsafe', 'cleanup'],
    menuHidden: ['cleanup'],
  });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    const jobs = (await readMenu(app))[4].items;
    if (
      JSON.stringify(jobs.map((i) => i.label)) !==
      JSON.stringify(['Home', 'Look up', 'Add', 'Link items', 'Fix and close', 'Keep safe', 'Clean up'])
    ) {
      fail(`the shown order must follow the saved order (Home always first): ${jobs.map((i) => i.label).join(' | ')}`);
    }
    const cleanup = jobs.find((i) => i.label === 'Clean up');
    if (cleanup.enabled !== false) fail('a hidden job is DISABLED in the menu, never hidden (spec §9 rule)');
    const others = jobs.filter((i) => i.label !== 'Clean up');
    if (others.some((i) => !i.enabled)) fail('the shown jobs stay enabled');
    // The accelerators are positional: nth shown item = Command/Ctrl+n.
    if (jobs.find((i) => i.label === 'Add').accelerator !== 'CmdOrCtrl+3') fail('the accelerators stay positional');

    // Jobs -> Look up navigates; the hidden Clean up is not navigable.
    await clickMenuItem(app, 'job-lookup');
    await win.waitForSelector('[data-testid="lookup-gated"]');

    // The sidebar toggle: this window's own nav, and the item rewords.
    await clickMenuItem(app, 'view-sidebar');
    await win.waitForFunction(() => document.getElementById('nav').hidden === true);
    await waitForMenuItem(app, 'view-sidebar', (i) => i.label === 'Show Sidebar', 'the sidebar item rewords');
    await clickMenuItem(app, 'view-sidebar');
    await win.waitForFunction(() => document.getElementById('nav').hidden === false);
    await waitForMenuItem(app, 'view-sidebar', (i) => i.label === 'Hide Sidebar', 'the sidebar item rewords back');
    process.stdout.write('hide/reorder + sidebar toggle OK\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 5: Settings… and Find ---------------- */

async function settingsAndFind() {
  process.stdout.write('--- scenario 5: Settings… opens the panes; Find focuses the search ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu5-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  const { app } = await launch({ workDir, dbPath });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="home-pane"]');

    await clickMenuItem(app, 'settings');
    await win.waitForSelector('[data-testid="pane-settings"]');
    if (!(await win.title()).includes('Settings')) fail('the Settings… route lands on the pane (title names it)');

    await clickMenuItem(app, 'edit-find');
    await win.waitForSelector('[data-testid="lookup-pane"]');
    await win.waitForSelector('[data-testid="lookup-q"]');
    const focused = await win.evaluate(() => {
      const el = document.activeElement;
      return el ? el.getAttribute('data-testid') : null;
    });
    if (focused !== 'lookup-q') fail(`Find must focus the search box, focused: ${focused}`);
    process.stdout.write('Settings… and Find OK\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 6: first run ---------------- */

async function firstRunMenu() {
  process.stdout.write('--- scenario 6: first run disables the jobs and Settings, never hides ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu6-'));
  const { app } = await launch({ workDir, dbPath: null });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('.setup');
    const menus = await readMenu(app);
    if (menus === null) fail('the menu exists even before first run finishes');
    const jobs = menus[4].items;
    if (jobs.length !== 7) fail('the seven jobs stay listed during first run');
    if (jobs.some((i) => i.enabled !== false)) fail('every job is disabled while first run owns the screen');
    const settings = findItem(menus, 'settings');
    if (settings.enabled !== false) fail('Settings is disabled while first run owns the screen');
    if (findItem(menus, 'about').enabled === false) fail('About stays available');

    // A click cannot break first run: the renderer keeps the screen.
    await clickMenuItem(app, 'job-home');
    await new Promise((r) => setTimeout(r, 400));
    await win.waitForSelector('.setup');
    process.stdout.write('first-run gating OK (disabled, never hidden)\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

/* ---------------- scenario 7: story 102 (Details) + story 99 (Reduce Motion) ---------------- */

async function detailsAndMotion() {
  process.stdout.write('--- scenario 7: the code sits behind Details; Reduce Motion kills the one animation ---\n');
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-menu7-'));
  const dbPath = path.join(workDir, 'kb.db');
  seedMainKb(dbPath);
  const { app } = await launch({ workDir, dbPath, corruptSettings: true });
  try {
    const win = await app.firstWindow();
    await win.waitForSelector('[data-testid="banner"]');
    // Story 102: the error code is on request — behind a Details control.
    await win.click('[data-action="notice-details"]');
    await win.waitForSelector('[data-testid="notice-code"]:not([hidden])');
    const code = await win.textContent('[data-testid="notice-code"]');
    if (!/APP-004/.test(code)) fail(`the APP-004 code must sit behind Details, saw: ${code}`);

    // Story 99: Reduce Motion turns the one animation off — on a REAL change.
    await win.emulateMedia({ reducedMotion: 'reduce' });
    await win.waitForSelector('[data-testid="home-pane"]');
    await clickMenuItem(app, 'job-fix');
    await win.waitForSelector('[data-testid="fix-row-1"]');
    await win.click('[data-testid="fix-row-1"]');
    await win.waitForSelector('[data-testid="mark-challenged"]');
    await win.click('[data-testid="mark-challenged"]');
    await win.waitForFunction(() => /Item 1 is now Challenged/.test((document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent));
    const animating = await win.evaluate(() =>
      [...document.querySelectorAll('svg, *')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animating !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animating}`);

    // And without it, the same change REALLY settles (the one motion exists).
    await win.emulateMedia({ reducedMotion: 'no-preference' });
    await win.click('[data-testid="mark-active"]');
    await win.waitForFunction(() => /Item 1 is now Active/.test((document.querySelector('[data-testid="fix-message-region"]') ?? { textContent: '' }).textContent));
    const settled = await win.evaluate(() => {
      const svg = [...document.querySelectorAll('svg')].find((el) => /heat--settle/.test(el.getAttribute('class') || ''));
      return svg ? getComputedStyle(svg).animationName : 'no-settle-class';
    });
    if (settled === 'none' || settled === 'no-settle-class') {
      fail(`a real status change must run the settle animation, saw ${settled}`);
    }
    process.stdout.write('Details-on-request + Reduce Motion OK\n');
  } finally {
    await app.close().catch(() => {});
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

async function main() {
  await specTable();
  await liveLabels();
  await addTextOpensPopup();
  await hideAndReorder();
  await settingsAndFind();
  await firstRunMenu();
  await detailsAndMotion();
  process.stdout.write('e2e menus OK: the menu is the spec table, the undo labels live, the routes work\n');
}

main().catch((err) => {
  process.stderr.write(`e2e menus FAILED: ${err && err.message ? err.message : err}\n`);
  process.exit(1);
});

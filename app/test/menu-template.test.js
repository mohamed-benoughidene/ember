'use strict';

/**
 * The menu builder's unit tests (app step 12, step file §2): the
 * builder's output equals the spec §9 table (labels, shortcuts,
 * enabled state by context), the Undo/Redo label states derive from
 * the dry-run results exactly as the Fix and close bar's words do
 * (shared/undo-labels.mjs is the source), the About credits carry the
 * font licence facts (story 108), and the manager attaches ONE
 * dispatch per actionable item on a fake Menu (T3 — the only Electron
 * touch).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ROOT } = require('./util');

const {
  buildMenuTemplate,
  deriveUndoMenuState,
  aboutCreditsText,
  MENU_TITLES,
  JOB_NAMES,
} = require('../shared/menu-template.mjs');
const { createAppMenuManager } = require('../main/app-menu.js');

const READY_UNDO = deriveUndoMenuState(
  { ok: true, data: { summary: { direction: 'undo', source_action: 'close-item', target_label: 'item 3' } } },
  'undo',
);

const BASE = { platform: 'other', kbChosen: true, sidebarVisible: true, undo: READY_UNDO, redo: { label: 'Redo', enabled: false, reason: null } };

function flat(template) {
  // A compact view: "Menu > item label [accelerator] (!enabled) (role) (#id)".
  return template
    .map((menu) => ({
      label: menu.label,
      items: menu.submenu.map((i) =>
        [
          i.type === 'separator' ? '---' : i.label,
          i.accelerator ? `[${i.accelerator}]` : '',
          i.enabled === false ? ' (disabled)' : '',
          i.role ? ` {role ${i.role}}` : '',
        ].join(''),
      ),
    }))
    .map((m) => `${m.label}: ${m.items.join(' | ')}`);
}

/* ---------------- the seven menus, from the spec §9 table ---------------- */

test('the menu is exactly the spec §9 table (File/Edit/View/Jobs/Window/Help)', () => {
  const t = buildMenuTemplate(BASE);
  assert.deepEqual(t.map((m) => m.label), ['Ember', 'File', 'Edit', 'View', 'Jobs', 'Window', 'Help']);

  // Ember (app menu): About; Settings… (Command+Comma); Hide; Quit.
  const ember = t[0].submenu.filter((i) => i.type !== 'separator').map((i) => i.label);
  assert.deepEqual(ember, ['About Ember', 'Settings…', 'Hide', 'Quit']);
  assert.equal(t[0].submenu.find((i) => i.label === 'Settings…').accelerator, 'CmdOrCtrl+,');

  // File: Add text…; Open a knowledge base file… (Command+O); Back up…; Export…; Close window.
  const file = t[1].submenu.filter((i) => i.type !== 'separator');
  assert.deepEqual(file.map((i) => i.label), ['Add text…', 'Open a knowledge base file…', 'Back up…', 'Export…', 'Close window']);
  assert.equal(file[0].id, 'file-add-text');
  assert.equal(file[1].accelerator, 'CmdOrCtrl+O');
  assert.equal(file[1].label, 'Open a knowledge base file…');
  assert.equal(file[4].role, 'close');
});

/* ---------------- Edit: undo labels, standard roles, Find ---------------- */

test('the Edit menu labels Undo/Redo with the action and disables when nothing to undo', () => {
  const t = buildMenuTemplate({
    ...BASE,
    undo: { label: 'Undo Close item 3', enabled: true },
    redo: { label: 'Redo', enabled: false },
  });
  const edit = t[2].submenu.filter((i) => i.type !== 'separator');
  assert.deepEqual(
    edit.map((i) => `${i.label}${i.enabled === false ? ' [off]' : ''}`),
    ['Undo Close item 3', 'Redo [off]', 'Cut', 'Copy', 'Paste', 'Select All', 'Find'],
  );
  const undo = edit[0];
  const redo = edit[1];
  assert.equal(undo.accelerator, 'CmdOrCtrl+Z');
  assert.equal(redo.accelerator, 'Shift+CmdOrCtrl+Z');
  assert.equal(edit[6].accelerator, 'CmdOrCtrl+F');
  assert.equal(edit[6].id, 'edit-find');
  // The standard row is roles (Apple-standard edit behaviour), no click of ours.
  assert.equal(edit[2].role, 'cut');
  assert.equal(edit[5].role, 'selectAll');
});

/* ---------------- View: Show/Hide Sidebar ---------------- */

test('the View menu is the sidebar toggle, worded by the current state', () => {
  assert.equal(buildMenuTemplate(BASE)[3].submenu[0].label, 'Hide Sidebar');
  assert.equal(buildMenuTemplate({ ...BASE, sidebarVisible: false })[3].submenu[0].label, 'Show Sidebar');
});

/* ---------------- Jobs: the step-10 hide/reorder honoured ---------------- */

test('the Jobs menu keeps every job visible, disables the hidden ones, numbers positionally', () => {
  const t = buildMenuTemplate({
    ...BASE,
    jobs: { order: ['lookup', 'add', 'link', 'fix', 'keepsafe', 'cleanup'], hidden: ['cleanup'] },
  });
  const jobs = t[4].submenu;
  assert.deepEqual(
    jobs.map((i) => `${i.accelerator} ${i.label}${i.enabled ? '' : ' [off]'}`),
    [
      'CmdOrCtrl+1 Home',
      'CmdOrCtrl+2 Look up',
      'CmdOrCtrl+3 Add',
      'CmdOrCtrl+4 Link items',
      'CmdOrCtrl+5 Fix and close',
      'CmdOrCtrl+6 Keep safe',
      'CmdOrCtrl+7 Clean up [off]',
    ],
  );
});

test('the Jobs menu at the default order is exactly the spec table with Command+1..7', () => {
  const t = buildMenuTemplate(BASE);
  assert.deepEqual(t[4].submenu.map((i) => i.label), ['Home', 'Add', 'Look up', 'Link items', 'Fix and close', 'Clean up', 'Keep safe']);
  assert.deepEqual(t[4].submenu.map((i) => i.accelerator), [...Array(7)].map((_, i) => `CmdOrCtrl+${i + 1}`));
});

test('first run (no knowledge base) disables the jobs and Settings, never hides them', () => {
  const t = buildMenuTemplate({ ...BASE, kbChosen: false });
  assert.equal(t[0].submenu.find((i) => i.id === 'settings').enabled, false);
  assert.ok(t[4].submenu.every((i) => i.enabled === false));
  // The always-there items stay.
  assert.equal(t[0].submenu.find((i) => i.id === 'about').enabled, undefined); // default enabled
  assert.equal(t[6].submenu[0].enabled, false);
});

/* ---------------- Window + Help ---------------- */

test('the Window menu is Minimize + Zoom; Help is visible and disabled', () => {
  assert.deepEqual(buildMenuTemplate(BASE)[5].submenu.map((i) => i.role), ['minimize', 'zoom']);
  const help = buildMenuTemplate(BASE)[6].submenu[0];
  assert.equal(help.label, 'Ember Help');
  assert.equal(help.enabled, false);
});

/* ---------------- Mac vs Linux ---------------- */

test('Command becomes Ctrl everywhere via CmdOrCtrl; the app menu holds the Mac Hide', () => {
  const mac = buildMenuTemplate({ ...BASE, platform: 'darwin' });
  const macHide = mac[0].submenu.find((i) => i.label !== undefined && i.label.startsWith('Hide'));
  assert.equal(macHide.role, 'hide');
  assert.equal(macHide.label, 'Hide Ember');
  // Linux: the same item exists (never hidden), Minimize in Hide's place.
  const linuxHide = buildMenuTemplate(BASE)[0].submenu.find((i) => i.label === 'Hide');
  assert.equal(linuxHide.role, 'minimize');
  // The other six menus are byte-identical between the platforms.
  const other = buildMenuTemplate(BASE);
  assert.deepEqual(other.slice(1), mac.slice(1));
});

/* ---------------- the Undo/Redo menu states ---------------- */

test('deriveUndoMenuState: the plan names the action; nothing-to-undo disables with the honest reason', () => {
  const plan = { ok: true, data: { summary: { direction: 'undo', source_action: 'close-item', target_label: 'item 3' } } };
  assert.deepEqual(deriveUndoMenuState(plan, 'undo'), { label: 'Undo Close item 3', enabled: true, reason: null });

  const nothing = {
    ok: false,
    error: { code: 'MAINTAIN-023', name: 'NothingToUndo', where: 'x', detail: 'no undo group available' },
  };
  const state = deriveUndoMenuState(nothing, 'undo');
  assert.equal(state.label, 'Undo');
  assert.equal(state.enabled, false);
  assert.match(state.reason, /Nothing to undo/);
});

test('deriveUndoMenuState: no answer yet is disabled-plain; a transport refusal stays enabled-plain', () => {
  assert.deepEqual(deriveUndoMenuState(null, 'redo'), { label: 'Redo', enabled: false, reason: null });
  const transport = { ok: false, error: { code: 'APP-008', name: 'BridgeTimeout', where: 'x', detail: 'timed out' } };
  assert.deepEqual(deriveUndoMenuState(transport, 'undo'), { label: 'Undo', enabled: true, reason: null });
});

test('deriveUndoMenuState: an unreadable summary never labels wrongly', () => {
  const drifted = { ok: true, data: { summary: { direction: 'undo', source_action: 'time-travel', target_label: 'item 3' } } };
  const state = deriveUndoMenuState(drifted, 'undo');
  assert.equal(state.enabled, false);
  assert.equal(state.label, 'Undo');
});

/* ---------------- the About credits (story 108) ---------------- */

test('the About credits name the typefaces, the OFL licence and where the texts sit', () => {
  const text = aboutCreditsText({ version: '0.2.0', fontsPath: '/app/assets/fonts' });
  assert.match(text, /Atkinson Hyperlegible Next/);
  assert.match(text, /Atkinson Hyperlegible Mono/);
  assert.match(text, /SIL Open Font Licence, version 1\.1/);
  assert.match(text, /-OFL\.txt/);
  assert.match(text, /\/app\/assets\/fonts/);
  assert.match(text, /0\.2\.0/);
});

/* ---------------- drift pins ---------------- */

test('the menu job names are the sidebar names (app.mjs) — no drift', () => {
  const source = fs.readFileSync(path.join(APP_ROOT, 'renderer', 'screens', 'app.mjs'), 'utf8');
  const jobs = [...source.matchAll(/id: '([a-z]+)', name: '([^']+)'/g)];
  assert.equal(jobs.length, 8); // 7 jobs + Settings
  for (const [, id, name] of jobs) {
    if (id === 'settings') continue; // Settings lives in the app menu, not Jobs
    assert.equal(JOB_NAMES[id], name, `the Jobs menu name for ${id} drifted from the sidebar`);
  }
});

test('the hidden movable jobs are exactly the six the settings Menu pane offers', () => {
  const source = fs.readFileSync(path.join(APP_ROOT, 'renderer', 'screens', 'settings.mjs'), 'utf8');
  const block = source.match(/export const MENU_JOBS = \[([\s\S]*?)\];/);
  assert.ok(block, 'settings.mjs MENU_JOBS moved');
  const ids = [...block[1].matchAll(/id: '([a-z]+)'/g)].map((m) => m[1]);
  assert.deepEqual(ids, ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe']);
});

/* ---------------- the manager (the one Electron touch) ---------------- */

function fakeMenuApi() {
  return {
    built: [],
    buildFromTemplate(t) {
      return { template: t };
    },
    setApplicationMenu(m) {
      this.built.push(m);
    },
  };
}

test('the manager attaches one dispatch per actionable item, none on roles or separators', () => {
  const api = fakeMenuApi();
  const clicks = [];
  const manager = createAppMenuManager({
    MenuApi: api,
    platform: 'other',
    context: () => ({ ...BASE, jobs: { order: [], hidden: [] } }),
    dispatch: (id) => clicks.push(id),
  });
  assert.equal(api.built.length, 0);
  manager.refresh();
  assert.equal(api.built.length, 1);
  const menu = api.built[0].template;
  assert.deepEqual(menu.map((m) => m.label), MENU_TITLES);

  const fire = (id) => {
    for (const m of menu) {
      const item = m.submenu.find((i) => i.id === id);
      if (item) return item.click();
    }
    throw new Error(`no item ${id}`);
  };
  // No accidental clicks before one is made.
  assert.deepEqual(clicks, []);
  fire('job-fix');
  fire('edit-find');
  assert.deepEqual(clicks, ['job-fix', 'edit-find']);
  // Role items and separators carry no click of ours; the one item with
  // no action at all (the disabled Ember Help) likewise.
  for (const m of menu) {
    for (const item of m.submenu) {
      if (item.type === 'separator') assert.equal(item.click, undefined);
      else if (item.role) assert.equal(item.click, undefined);
      else if (!item.id) assert.equal(item.click, undefined); // the disabled Help: no action exists
      else assert.equal(typeof item.click, 'function');
    }
  }
});

test('a second refresh replaces the menu with the CURRENT context', () => {
  const api = fakeMenuApi();
  let undo = { label: 'Undo', enabled: false, reason: null };
  const manager = createAppMenuManager({
    MenuApi: api,
    platform: 'other',
    context: () => ({ ...BASE, undo }),
    dispatch: () => {},
  });
  manager.refresh();
  assert.equal(api.built[0].template[2].submenu.find((i) => i.id === 'edit-undo').enabled, false);
  undo = { label: 'Undo Close item 1', enabled: true, reason: null };
  manager.refresh();
  assert.equal(api.built.length, 2);
  const item = api.built[1].template[2].submenu.find((i) => i.id === 'edit-undo');
  assert.equal(item.label, 'Undo Close item 1');
  assert.equal(item.enabled, true);
});

test('the manager refuses to build without its three pieces', () => {
  assert.throws(() => createAppMenuManager({ MenuApi: {}, platform: 'other', context: () => BASE, dispatch: () => {} }));
  assert.throws(() => createAppMenuManager({ MenuApi: fakeMenuApi(), platform: 'other', context: null, dispatch: () => {} }));
  assert.throws(() => createAppMenuManager({ MenuApi: fakeMenuApi(), platform: 'other', context: () => BASE, dispatch: null }));
});

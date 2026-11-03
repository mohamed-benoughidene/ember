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
  engineVersionFromStdout,
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

/* ---------------- story 13: a focused text field means text undo ---------------- */

test('a focused text field renders Edit Undo/Redo as Electron roles, never Ember job actions (story 13)', () => {
  const t = buildMenuTemplate({ ...BASE, textFieldFocused: true });
  const edit = t[2].submenu;
  const undo = edit[0];
  const redo = edit[1];
  // Roles, not action ids: the manager (main/app-menu.js wire) gives
  // role items NO click, so no Ember job action can fire while typing
  // — Ctrl+Z stays with the text box (finding 4.9 #14).
  assert.equal(undo.role, 'undo');
  assert.equal(redo.role, 'redo');
  assert.equal(undo.id, undefined);
  assert.equal(redo.id, undefined);
  // The standard words while editing text (Apple's rule — what a text
  // undo would undo is not known here), and the role implies enabled.
  assert.equal(undo.label, 'Undo');
  assert.equal(redo.label, 'Redo');
  // No accelerator of ours: the role carries the platform default.
  assert.equal(undo.accelerator, undefined);
  assert.equal(redo.accelerator, undefined);
  // The rest of the Edit menu is untouched.
  assert.deepEqual(
    edit.slice(2).map((i) => (i.type === 'separator' ? '---' : i.label)),
    ['---', 'Cut', 'Copy', 'Paste', 'Select All', '---', 'Find'],
  );
  // Without the knob (no field focused) the items stay Ember's own.
  const idle = buildMenuTemplate(BASE)[2].submenu;
  assert.equal(idle[0].id, 'edit-undo');
  assert.equal(idle[1].id, 'edit-redo');
});

test('the manager gives a focused-field role Undo/Redo no dispatch (they are not Ember actions)', () => {
  const api = fakeMenuApi();
  const clicks = [];
  const manager = createAppMenuManager({
    MenuApi: api,
    platform: 'other',
    context: () => ({ ...BASE, textFieldFocused: true }),
    dispatch: (id) => clicks.push(id),
  });
  manager.refresh();
  const edit = api.built[0].template[2].submenu;
  assert.equal(edit[0].role, 'undo');
  assert.equal(edit[0].click, undefined);
  assert.equal(edit[1].role, 'redo');
  assert.equal(edit[1].click, undefined);
  // The action ids are gone entirely: nothing can route an Ember undo
  // while a text field holds focus.
  assert.equal(edit.find((i) => i.id === 'edit-undo'), undefined);
  assert.equal(edit.find((i) => i.id === 'edit-redo'), undefined);
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

/* ---------------- the About credits (story 108, Batch 6 F7a) ---------------- */

test('the About credits name the typefaces, the OFL files and BOTH versions — never a path (F7a)', () => {
  const text = aboutCreditsText({ appVersion: '0.2.0', engineVersion: '0.4.0' });
  assert.match(text, /Atkinson Hyperlegible Next/);
  assert.match(text, /Atkinson Hyperlegible Mono/);
  assert.match(text, /SIL Open Font Licence, version 1\.1/);
  // The app version AND the engine's own version line (Batch 1's
  // `ember --version`), when the engine answered.
  assert.match(text, /Ember 0\.2\.0/);
  assert.match(text, /engine[^\n]*0\.4\.0/);
  // The full licence text is named by its REAL file (both bundled
  // faces carry one), not by a folder that may not exist.
  assert.match(text, /atkinson-hyperlegible-next-OFL\.txt/);
  assert.match(text, /atkinson-hyperlegible-mono-OFL\.txt/);
  // F7a: NO install path and NO fonts folder — the About box must not
  // reveal where (or whether) the app sits on disk.
  assert.ok(!text.includes('/'), `the About text shows a path-like string:\n${text}`);
  assert.ok(!/folder/i.test(text), `the About text still names a folder:\n${text}`);
});

test('when the engine does not answer, the About shows the app version only (F7a)', () => {
  for (const engineVersion of [null, undefined]) {
    const text = aboutCreditsText({ appVersion: '0.2.0', engineVersion });
    assert.match(text, /Ember 0\.2\.0/);
    // No engine claim at all: a silent engine must not produce a
    // half-honest line.
    assert.ok(!/engine/i.test(text), `the About text still claims an engine version:\n${text}`);
    assert.ok(!text.includes('/'), `the About text shows a path-like string:\n${text}`);
  }
});

test('the engine version line parses from `ember --version`; anything else is no answer', () => {
  // click's version_option with prog_name "ember" (ember/cli.py:379).
  assert.equal(engineVersionFromStdout('ember, version 0.1.0\n'), '0.1.0');
  // The packaging stub in tests/fixtures prints the same shape with a tag.
  assert.equal(engineVersionFromStdout('ember, version 0.1.0 (stub)\n'), '0.1.0');
  // Anything else — empty stdout, some other program's text — is null,
  // so the About box falls back to the app version only.
  assert.equal(engineVersionFromStdout(''), null);
  assert.equal(engineVersionFromStdout('\n'), null);
  assert.equal(engineVersionFromStdout('snake oil, version 9.9\n'), null);
  assert.equal(engineVersionFromStdout(undefined), null);
});

test('main.js passes BOTH versions to the About box, read once via `ember --version` (F7a wiring)', () => {
  const source = fs.readFileSync(path.join(APP_ROOT, 'main', 'main.js'), 'utf8');
  // The credits call carries the app version AND the engine version —
  // never a fonts path again.
  const call = source.match(/const credits = aboutCreditsText\(\{([\s\S]*?)\}\);/);
  assert.ok(call, 'the aboutCreditsText call moved in main.js');
  assert.match(call[1], /appVersion:/);
  assert.match(call[1], /engineVersion/);
  assert.ok(!call[1].includes('fontsPath'), 'the About call still passes a fonts path');
  // The engine version is read through the SAME resolved ember command
  // every other child uses (main/ember-command.js -> services.emberCommand):
  // one `--version` spawn in the main process, parsed by the shared
  // pure parser — no new IPC route, nothing crosses to the renderer.
  assert.ok(source.includes("'--version'"), 'main.js no longer asks the engine for its version');
  assert.match(source, /engineVersionFromStdout/, 'the engine answer is not parsed by the shared pure parser');
  // The fallback is real: the read never rejects and settles null when
  // the engine does not answer, so the builder above decides the words.
  assert.match(source, /function readEngineVersion/, 'the one-shot engine-version read moved');
  assert.ok(/catch/.test(source.match(/function readEngineVersion[\s\S]*?\n\}/)[0]), 'the engine-version read has no failure fallback');
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

test('every bridge READ command joins MENU_ACTIVITY_SKIPS: a read cannot change the ledger (issue #46)', () => {
  // The menu skips its undo-label re-derive after commands that cannot
  // write (main.js MENU_ACTIVITY_SKIPS). bridge-client.js owns the real
  // read/write split; this pin ties the two together so a Batch-7-style
  // new read cannot silently trigger the two dry-run child processes.
  const main = fs.readFileSync(path.join(APP_ROOT, 'main', 'main.js'), 'utf8');
  const skipBlock = main.match(/const MENU_ACTIVITY_SKIPS = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(skipBlock, 'main.js MENU_ACTIVITY_SKIPS moved');
  const skips = [...skipBlock[1].matchAll(/'([a-z-]+)'/g)].map((m) => m[1]);

  const client = fs.readFileSync(path.join(APP_ROOT, 'main', 'bridge-client.js'), 'utf8');
  const readBlock = client.match(/const READ_COMMANDS = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(readBlock, 'bridge-client.js READ_COMMANDS moved');
  const reads = [...readBlock[1].matchAll(/'([a-z-]+)'/g)].map((m) => m[1]);

  for (const read of reads) {
    assert.ok(
      skips.includes(read),
      `the read command '${read}' is missing from MENU_ACTIVITY_SKIPS (issue #46)`,
    );
  }
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

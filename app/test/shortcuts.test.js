'use strict';

/**
 * The shortcut + tray manager seams (plan §5.5, APP-005). Faked OS
 * objects everywhere (T3); the real registration is step 11's story.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { createShortcutManager, createTrayManager } = require('../main/shortcuts');

function fakeGlobalShortcut(result) {
  const calls = [];
  return {
    calls,
    register(accelerator, cb) {
      calls.push({ accelerator, cb });
      if (result instanceof Error) throw result;
      return result;
    },
    unregisterAll() {},
  };
}

test('a granted shortcut registers with the quick-add action and no failure', () => {
  const failures = [];
  let fired = false;
  const globalShortcut = fakeGlobalShortcut(true);
  const manager = createShortcutManager({
    globalShortcut,
    onFailure: (info) => failures.push(info),
    onQuickAdd: () => {
      fired = true;
    },
  });
  const result = manager.register('CommandOrControl+Alt+E');
  assert.deepEqual(result, { ok: true });
  assert.deepEqual(failures, []);
  assert.equal(globalShortcut.calls.length, 1);
  globalShortcut.calls[0].cb();
  assert.equal(fired, true, 'the callback was not wired to the shortcut');
});

test('a refused shortcut is APP-005 and the tray fallback is asked for', () => {
  const failures = [];
  const manager = createShortcutManager({
    globalShortcut: fakeGlobalShortcut(false),
    onFailure: (info) => failures.push(info),
    onQuickAdd: () => {},
  });
  const result = manager.register('CommandOrControl+Alt+E');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-005');
  assert.equal(result.error.name, 'ShortcutRegistrationFailed');
  assert.equal(failures.length, 1);
});

test('an OS-level throw is also APP-005, never a crash', () => {
  const failures = [];
  const manager = createShortcutManager({
    globalShortcut: fakeGlobalShortcut(new Error('no compositor')),
    onFailure: (info) => failures.push(info),
    onQuickAdd: () => {},
  });
  const result = manager.register('CommandOrControl+Alt+E');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-005');
  assert.equal(failures.length, 1);
  assert.ok(result.error.detail.includes('no compositor'));
});

test('an empty accelerator is APP-005 (nothing is registered "somehow")', () => {
  const failures = [];
  const globalShortcut = fakeGlobalShortcut(true);
  const manager = createShortcutManager({
    globalShortcut,
    onFailure: (info) => failures.push(info),
    onQuickAdd: () => {},
  });
  assert.equal(manager.register('').ok, false);
  assert.equal(globalShortcut.calls.length, 0, 'nothing was registered');
});

test('the tray fallback builds the pinned three-item menu', () => {
  const templates = [];
  const TrayCtor = class FakeTray {
    constructor(icon) {
      this.icon = icon;
    }
    setToolTip(t) {
      this.tooltip = t;
    }
    setContextMenu(menu) {
      this.menu = menu;
    }
    destroy() {}
  };
  const MenuBuilder = { buildFromTemplate: (t) => (templates.push(t), { t }) };
  const tray = createTrayManager({ TrayCtor, MenuBuilder, iconPath: null });
  let quickAdd = false;
  const result = tray.show({
    onQuickAdd: () => {
      quickAdd = true;
    },
    onOpenEmber: () => {},
    onQuit: () => {},
  });
  assert.deepEqual(result, { ok: true });
  assert.equal(tray.builtCount, 1);
  const template = templates[0];
  assert.deepEqual(
    template.filter((entry) => entry.label).map((entry) => entry.label),
    ['Quick add', 'Open Ember', 'Quit'],
  );
  template[0].click();
  assert.equal(quickAdd, true);
});

test('a tray failure reports honestly (the File -> Add text route remains)', () => {
  const BrokenTray = class {
    constructor() {
      throw new Error('StatusNotifierWatcher missing');
    }
  };
  const tray = createTrayManager({ TrayCtor: BrokenTray, MenuBuilder: { buildFromTemplate: () => ({}) } });
  const result = tray.show({ onQuickAdd: () => {}, onOpenEmber: () => {}, onQuit: () => {} });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-005');
  assert.ok(result.error.detail.includes('File -> Add text'), result.error.detail);
});

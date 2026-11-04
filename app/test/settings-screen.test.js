'use strict';

/**
 * The Settings screen's pure pieces (app step 10), unit-tested without
 * a DOM: the menu pane's order/hide math, the captured-key accelerator
 * build, the masked key hint (main/key-hint.js), and the Settings
 * shortcut re-registration seam.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ROOT } = require('./util');
const { maskKey } = require('../main/key-hint');
const { registerSettingsShortcut } = require('../main/shortcuts');

let screenMod; // the Settings screen module (ESM), imported in the tests
const screen = async () => {
  screenMod ??= await import('../renderer/screens/settings.mjs');
  return screenMod;
};

function order(ids, MENU_JOBS) {
  return MENU_JOBS.filter((j) => ids.includes(j.id));
}

test('the panes are the four decision-8 settings plus the knowledge-base file', async () => {
  const { SETTING_PANES } = await screen();
  assert.deepEqual(SETTING_PANES.map((p) => p.id), ['appearance', 'popup', 'menu', 'ai', 'kbfile']);
  assert.deepEqual(
    SETTING_PANES.slice(0, 4).map((p) => p.name),
    ['Appearance', 'Quick popup', 'Menu', 'AI connection'],
    'the four spec panes sit first, in the approved wording',
  );
});

test('menu order: a foreign or truncated order still shows every job exactly once', async () => {
  const { MENU_JOBS, menuOrderForDisplay } = await screen();
  assert.deepEqual(
    menuOrderForDisplay(['lookup', 'ghost', 'add', 'lookup', 'cleanup']).map((j) => j.id),
    ['lookup', 'add', 'cleanup', 'link', 'fix', 'keepsafe'],
  );
  assert.equal(menuOrderForDisplay([]).length, MENU_JOBS.length);
  assert.equal(menuOrderForDisplay(undefined).length, MENU_JOBS.length);
});

test('Home and Settings are never in the movable list (story 88)', async () => {
  const { MENU_JOBS } = await screen();
  assert.equal(MENU_JOBS.some((j) => j.id === 'home'), false);
  assert.equal(MENU_JOBS.some((j) => j.id === 'settings'), false);
});

test('moving a job clamps at the ends and keeps the others', async () => {
  const { MENU_JOBS, menuOrderForDisplay, moveJob } = await screen();
  const list = menuOrderForDisplay(['add', 'lookup', 'link']);
  assert.deepEqual(moveJob(list, 'add', 'up'), list, 'up at the top changes nothing');
  assert.deepEqual(moveJob(list, 'keepsafe', 'down'), list, 'down at the bottom changes nothing');
  assert.deepEqual(
    moveJob(list, 'add', 'down').map((j) => j.id),
    ['lookup', 'add', 'link', 'fix', 'cleanup', 'keepsafe'],
  );
  assert.deepEqual(
    moveJob(list, 'link', 'up').map((j) => j.id),
    ['add', 'link', 'lookup', 'fix', 'cleanup', 'keepsafe'],
  );
  void order;
  void MENU_JOBS;
});

test('hiding keeps nothing deleted: toggle twice restores the exact list', async () => {
  const { toggleJobHidden } = await screen();
  const hidden = toggleJobHidden(['keepsafe'], 'add');
  assert.deepEqual(hidden, ['keepsafe', 'add']);
  assert.deepEqual(toggleJobHidden(hidden, 'add'), ['keepsafe']);
});

test('capture: lone modifiers wait, letters build an accelerator with Apple-ordered mods', async () => {
  const { eventKey, acceleratorFromEvent } = await screen();
  assert.equal(eventKey({ key: 'Control' }), null);
  assert.equal(eventKey({ key: 'Meta' }), null);
  assert.equal(eventKey({ key: 'e' }), 'e');
  assert.equal(eventKey({ key: 'Enter' }), 'Enter');
  // On Linux Ctrl+Alt+E saves CommandOrControl, so the choice is portable:
  assert.equal(
    acceleratorFromEvent({ ctrlKey: true, altKey: true, shiftKey: false, metaKey: false }, 'e', false),
    'CommandOrControl+Alt+E',
  );
  // On a Mac a pressed Control stays Control, so the pane can warn (86):
  assert.equal(
    acceleratorFromEvent({ ctrlKey: true, altKey: true, shiftKey: false, metaKey: false }, 'e', true),
    'Control+Alt+E',
  );
  assert.equal(
    acceleratorFromEvent({ ctrlKey: false, altKey: false, shiftKey: false, metaKey: true }, 'q', true),
    'Command+Q',
  );
});

test('the masked key hint is the last four characters, never the key (89)', () => {
  assert.equal(maskKey('sk-or-v1-abcdef1234567890abcd'), 'abcd');
  assert.equal(maskKey('1234'), '1234');
  assert.equal(maskKey('123'), null);
  assert.equal(maskKey(null), null);
  assert.equal(maskKey(undefined), null);
  // The hint can never contain the whole key when the key is long.
  const key = 'sk-or-v1-averylongkeyvalue0123456789';
  assert.ok(!maskKey(key).includes(key));
});

test('the Settings shortcut re-registration forgets the old keys first, then tries the new ones', () => {
  const calls = [];
  const manager = {
    register: (accelerator) => {
      calls.push(`register:${accelerator}`);
      return { ok: true };
    },
    unregisterAll: () => {
      calls.push('unregisterAll');
    },
    current: () => null, // this fake models "nothing yet registered"
  };
  const first = registerSettingsShortcut({ manager, accelerator: 'CommandOrControl+Alt+E' });
  const second = registerSettingsShortcut({ manager, accelerator: 'CommandOrControl+Alt+K' });
  assert.deepEqual(first, { ok: true });
  assert.deepEqual(second, { ok: true });
  assert.deepEqual(calls, ['unregisterAll', 'register:CommandOrControl+Alt+E', 'unregisterAll', 'register:CommandOrControl+Alt+K']);
});

test('a refused shortcut comes back failed after the manager told the shell', () => {
  let onFailureArgs = null;
  const manager = {
    register: () => {
      // The real manager calls onFailure itself before returning false;
      // onFailure is where main.js builds the tray fallback.
      onFailureArgs = 'called';
      return { ok: false };
    },
    unregisterAll: () => {},
    current: () => null,
  };
  const result = registerSettingsShortcut({ manager, accelerator: 'CommandOrControl+Alt+K' });
  assert.equal(result.ok, false);
  assert.equal(onFailureArgs, 'called', 'the shell was notified for the tray fallback');
});

/* ---------- fix #42: the persistent shortcut status line ---------- */

const POPUP_STATE = {
  settings: { quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' } },
  candidate: null,
  capturing: false,
};

test('the shortcut status line says so when the system accepted the keys', async () => {
  const { popupHtml } = await screen();
  const html = popupHtml({ ...POPUP_STATE, shortcutStatus: { configured: 'CommandOrControl+Alt+E', live: 'CommandOrControl+Alt+E', active: true } });
  assert.ok(html.includes('data-testid="popup-shortcut-status"'), 'the status line is rendered with its test id');
  assert.ok(html.includes('accepted'), 'the active words name the acceptance');
  assert.ok(!html.includes('Not working right now'), 'no contradiction with the active state');
});

test('the shortcut status line marks refused keys as not working when you come back (fix #42)', async () => {
  const { popupHtml } = await screen();
  const html = popupHtml({ ...POPUP_STATE, shortcutStatus: { configured: 'CommandOrControl+Alt+E', live: null, active: false } });
  assert.ok(html.includes('data-testid="popup-shortcut-status"'), 'the status line is rendered with its test id');
  assert.ok(html.includes('Not working right now'), 'the honest not-active marker is on the pane');
  assert.ok(html.includes('tried again next time Ember starts'), 'the saved-and-retried promise stays');
});

test('the status line is absent when no shortcut is configured at all', async () => {
  const { popupHtml } = await screen();
  const html = popupHtml({
    settings: { quickPopup: { shortcut: '', position: 'bottom-right' } },
    candidate: null,
    capturing: false,
    shortcutStatus: { configured: null, live: null, active: false },
  });
  assert.ok(!html.includes('data-testid="popup-shortcut-status"'), 'nothing configured: no line, no noise');
});

test('every preloaded name the Settings screen calls exists in preload and ipc', () => {
  const preload = fs.readFileSync(path.join(APP_ROOT, 'preload', 'preload.js'), 'utf8');
  const ipc = fs.readFileSync(path.join(APP_ROOT, 'main', 'ipc.js'), 'utf8');
  for (const channel of ['registerShortcut', 'shortcutStatus', 'keyHint', 'saveSettings', 'keyStatus', 'setKey', 'setSessionKey', 'removeKey', 'kbStatus', 'pickKnowledgeBaseFile']) {
    assert.ok(preload.includes(channel), `${channel} is preloaded`);
    assert.ok(ipc.includes(`ember:${channel}'`), `${channel} is registered`);
  }
});

test('both layers share the ONE keyShapeWords function (fix C5 drift pin)', async () => {
  const shared = await import('../shared/key-shape.mjs');
  const { keyShapeWords: screenWords } = await import('../renderer/screens/settings.mjs');
  const { keyShapeWords: mainWords } = require('../main/ipc');
  // Identity, not equality: a layer that grows its own copy fails this.
  assert.equal(screenWords, shared.keyShapeWords, 'the settings screen must re-export the shared words');
  assert.equal(mainWords, shared.keyShapeWords, 'the main-process backstop must re-export the shared words');
  assert.match(shared.keyShapeWords('empty'), /Paste your key/);
});

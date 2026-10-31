'use strict';

/**
 * The app's own T9 equivalent — the preload allowlist test (step file
 * §1: "A node test asserts the renderer cannot reach fs,
 * child_process").
 *
 * Three pins:
 * 1. the preload file exposes EXACTLY the named list (15 after step
 *    04), over contextBridge, requiring only `electron`;
 * 2. every renderer file (any subfolder, .js and .mjs) contains no
 *    Node access at all (no require, no process, no Electron import);
 * 3. the window is built with contextIsolation on, nodeIntegration
 *    off, sandbox on; and every channel the preload calls is really
 *    registered in main/ipc.js (no silent dead calls, no hidden ones).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ROOT } = require('./util');

const PRELOAD = fs.readFileSync(path.join(APP_ROOT, 'preload', 'preload.js'), 'utf8');
const IPC = fs.readFileSync(path.join(APP_ROOT, 'main', 'ipc.js'), 'utf8');
const MAIN = fs.readFileSync(path.join(APP_ROOT, 'main', 'main.js'), 'utf8');

const EXPECTED_CHANNELS = [
  'ember:ping',
  'ember:getState',
  'ember:saveSettings',
  'ember:kbStatus',
  'ember:pickKnowledgeBaseFile',
  'ember:listItems',
  'ember:topicSearch',
  'ember:showItem',
  'ember:history',
  'ember:currentState',
  'ember:maintainDryRun',
  'ember:keyStatus',
  'ember:setKey',
  'ember:setSessionKey',
  'ember:removeKey',
];
/* App 05 (ticket A34): the Add confirm-session channels =====
   The three invoke channels are registered by wireAddChannels
   (main/add-session.js) at the end of the ipc list, not in the
   handlers table; the two push channels go main -> renderer. */
const ADD_SESSION_CHANNELS = ['ember:addStart', 'ember:addAnswer', 'ember:addStop', 'ember:addAttach'];
/* App step 09 (Keep safe) — the five invoke channels, merged after
   the Add block (the merged file's order: base, Add, Keep safe). */
const KEEP_SAFE_CHANNELS = [
  'ember:pickSaveFile',
  'ember:backupTo',
  'ember:exportTo',
  'ember:dbCheck',
  'ember:switchKnowledgeBase',
];
/* App step 07 (Fix and close) — the two channels, merged after the
   Keep safe block (the merged file's order: base, Add, Keep safe,
   Fix and close). */
const FIX_CLOSE_CHANNELS = ['ember:fixAction', 'ember:undoPlan'];
/* App 10 (ticket A39): the Settings channels, merged after the
   Fix and close block (merged file order: base, Add, Keep safe,
   Fix and close, Settings). */
const SETTINGS_CHANNELS = ['ember:registerShortcut', 'ember:keyHint'];
/* App 08 (ticket A37): the Clean up screen's four invoke channels,
   merged after the Settings block (merged file order: base, Add,
   Keep safe, Fix and close, Settings, Clean up). */
const MAINTAIN_CHANNELS = [
  'ember:maintainPreview',
  'ember:maintainApply',
  'ember:maintainAnswer',
  'ember:maintainStop',
];
/* App 11 (ticket A40): the quick popup's two invoke channels, merged
   after the Clean up block (merged file order: base, Add, Keep safe,
   Fix and close, Settings, Clean up, Quick popup). The `ember:openRequest`
   push channel goes main -> main-window renderer (not an invoke). */
const QUICK_POPUP_CHANNELS = ['ember:openQuickPopup', 'ember:quickOpenMain'];
const ADD_PUSH_CHANNELS = ['ember:addEvent', 'ember:addExit'];
const ADD_SESSION_MODULE = fs.readFileSync(path.join(APP_ROOT, 'main', 'add-session.js'), 'utf8');
/* ==== end App 05 block ==== */

function readRendererSources() {
  const dir = path.join(APP_ROOT, 'renderer');
  const files = [];
  (function walk(d) {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(path.join(d, entry.name));
      else if (entry.name.endsWith('.js') || entry.name.endsWith('.mjs')) {
        files.push({ file: path.relative(dir, path.join(d, entry.name)), source: fs.readFileSync(path.join(d, entry.name), 'utf8') });
      }
    }
  })(dir);
  return files;
}

test('the preload exposes exactly the pinned list over contextBridge', () => {
  const declared = PRELOAD.match(/EMBER_PRELOAD_API = Object\.freeze\(\[([^\]]*)\]/);
  assert.ok(declared, 'the allowlist constant was renamed or removed');
  const names = declared[1]
    .split(',')
    .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
    .filter(Boolean);
  /* App 05 (ticket A34) + App step 09: the freeze list = the 15
     handler channels, then the four Add invoke channels, then the
     five Keep safe channels, then the two Fix and close channels,
     the two Settings channels, the four Clean up channels, and the
     two Quick popup channels (app 11). */
  assert.deepEqual(names, [...EXPECTED_CHANNELS, ...ADD_SESSION_CHANNELS, ...KEEP_SAFE_CHANNELS, ...FIX_CLOSE_CHANNELS, ...SETTINGS_CHANNELS, ...MAINTAIN_CHANNELS, ...QUICK_POPUP_CHANNELS]);
  assert.equal((PRELOAD.match(/contextBridge\.exposeInMainWorld/g) ?? []).length, 1, 'exactly one expose');
});

test('the preload requires ONLY electron (never fs, child_process, or node:*)', () => {
  const requires = [...PRELOAD.matchAll(/require\(\s*['"]([^'"]+)['"]\s*\)/g)].map((m) => m[1]);
  assert.deepEqual(requires, ['electron']);
});

test('the preload never hands out raw ipcRenderer or process to the renderer world', () => {
  assert.ok(!/exposeInMainWorld\(\s*['"][^'"]*['"]\s*,\s*ipcRenderer\b/.test(PRELOAD), 'raw ipcRenderer must never be exposed');
  assert.ok(!/exposeInMainWorld\(\s*['"][^'"]*['"]\s*,\s*process\b/.test(PRELOAD), 'process must never be exposed');
});

test('the renderer files import no Node and no Electron (T9)', () => {
  for (const { file, source } of readRendererSources()) {
    assert.ok(!/\brequire\s*\(/.test(source), `${file} uses require`);
    assert.ok(!/\bprocess\b/.test(source), `${file} touches process`);
    assert.ok(!/\b__dirname\b/.test(source), `${file} touches __dirname`);
    assert.ok(!/from\s+['"]electron['"]/.test(source), `${file} imports electron`);
    assert.ok(!/globalThis\.nodeRequire|window\.require/.test(source), `${file} reaches for a Node escape hatch`);
  }
});

test('the window is built with the isolation switches ON', () => {
  assert.match(MAIN, /contextIsolation:\s*true/);
  assert.match(MAIN, /nodeIntegration:\s*false/);
  assert.match(MAIN, /sandbox:\s*true/);
});

test('every preloaded call has a registered handler in main/ipc.js (no dead, no hidden)', () => {
  const registered = [...IPC.matchAll(/'(ember:[a-zA-Z]+)':/g)].map((m) => m[1]);
  for (const channel of EXPECTED_CHANNELS) {
    assert.ok(registered.includes(channel), `${channel} is preloaded but never handled`);
  }
  assert.deepEqual(
    registered.sort(),
    [...EXPECTED_CHANNELS, ...KEEP_SAFE_CHANNELS, ...FIX_CLOSE_CHANNELS, ...SETTINGS_CHANNELS, ...MAINTAIN_CHANNELS, ...QUICK_POPUP_CHANNELS].sort(),
    'ipc.js registered a channel outside the allowlist',
  );
});

/* ==== App 11 (ticket A40): the quick popup's push channel rides
   main/main.js (the ONE main-to-window push this step adds), pinned
   like the Add push channels so it cannot go dead or hidden. ==== */
test('the quick-open push channel exists in preload and main', () => {
  assert.ok(PRELOAD.includes("'ember:openRequest'"), 'ember:openRequest missing from the preload subscriptions');
  assert.ok(MAIN.includes("'ember:openRequest'"), 'main.js never pushes ember:openRequest');
});
/* ==== end App 11 block ==== */

/* ==== App 05 (ticket A34): the Add session channels are registered by
   wireAddChannels inside ipc.js's App 05 block, and the two push
   channels are subscribed in the preload — all pinned here so none can
   go dead or hidden. ==== */
test('the add-session channels are preloaded, registered and pushed by name', () => {
  assert.ok(IPC.includes('wireAddChannels'), 'ipc.js never wires the Add session channels');
  for (const channel of ADD_SESSION_CHANNELS) {
    assert.ok(PRELOAD.includes(`'${channel}'`), `${channel} missing from the preload allowlist`);
    assert.ok(
      ADD_SESSION_MODULE.includes(`ipcMain.handle('${channel}'`),
      `${channel} not registered by wireAddChannels`,
    );
  }
  for (const channel of ADD_PUSH_CHANNELS) {
    assert.ok(PRELOAD.includes(`'${channel}'`), `${channel} missing from the preload subscriptions`);
    assert.ok(ADD_SESSION_MODULE.includes(`'${channel}'`), `${channel} missing from the main-process pushes`);
  }
});
/* ==== end App 05 block ==== */

'use strict';

/**
 * The app's own T9 equivalent — the preload allowlist test (step file
 * §1: "A node test asserts the renderer cannot reach fs,
 * child_process").
 *
 * Three pins:
 * 1. the preload file exposes EXACTLY the named list (15 after step
 *    04; 42 with the Batch 2 Chunk 13 crash channels; 43 with story
 *    13's `ember:textFocusChanged` push; 45 with Batch 6 Chunk 13's
 *    two forget-note channels), over
 *    contextBridge, requiring only `electron`;
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
const SETTINGS_CHANNELS = ['ember:registerShortcut', 'ember:keyHint', 'ember:shortcutStatus'];
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
/* Batch 2 Chunk 13: the EMBER-000 crash report's two invoke channels,
   appended after the Quick popup block (merged file order: base, Add,
   Keep safe, Fix and close, Settings, Clean up, Link items, Quick
   popup, Crash report). Both are plain invokes over a crash id. */
const CRASH_CHANNELS = ['ember:crashReport', 'ember:crashReportFolder'];
/* App 12 (ticket A41): the application menu's ONE push channel
   (main -> main-window renderer). Not an invoke: subscribed via
   onMenuRequest in the preload, pinned below like the other pushes. */
const MENU_PUSH_CHANNELS = ['ember:menuRequest'];
const ADD_PUSH_CHANNELS = ['ember:addEvent', 'ember:addExit'];
/* Story 13 (finding 4.9 #14): the text-field focus push — ONE invoke
   channel, renderer -> main, a single boolean payload (true while a
   text field holds the keys, false the moment none does). Not a push
   subscription: only main ever acts on it (the Edit menu's role
   flip); the renderer gets a plain {ok} back. */
const TEXT_FOCUS_CHANNELS = ['ember:textFocusChanged'];
/* Batch 6 Chunk 13 (D-07/D-09/D-10): the "Forget this note" channels,
   merged after the text-focus entry (merged file order: base, Add,
   Keep safe, Fix and close, Settings, Clean up, Link items, Quick
   popup, Crash report, text focus, Forget note). Two plain invokes:
   the PERMANENT write (forget-source) and the read
   (list-sources-without-items). */
const FORGET_CHANNELS = ['ember:forgetSource', 'ember:listSourcesWithoutItems'];
/* App 06 (ticket A35): the Link items session channels, merged after
   the Fix and close block (the merged file's order: base, Add,
   Keep safe, Fix and close, Link items). */
const LINK_CHANNELS = [
  'ember:relateStart',
  'ember:relateAnswer',
  'ember:relateStop',
  'ember:relateAttach',
  'ember:relateEvent',
  'ember:relateExit',
];
const RELATE_SESSION_MODULE = fs.readFileSync(path.join(APP_ROOT, 'main', 'relate-session.js'), 'utf8');
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
  /* App 05 (ticket A34) + steps 09/07/06 + Chunk 13: the freeze list =
     the 15 handler channels, then the four Add invoke channels, then
     the five Keep safe channels, then the two Fix and close channels,
     the two Settings channels (app 10), the four Clean up channels
     (App 08), then the six Link items channels (App 06), then the two
     Quick popup channels (app 11), then the two Crash report channels
     (Batch 2 Chunk 13), then the one text-focus channel (story 13),
     then the two Forget-note channels (Batch 6 Chunk 13). */
  assert.deepEqual(names, [...EXPECTED_CHANNELS, ...ADD_SESSION_CHANNELS, ...KEEP_SAFE_CHANNELS, ...FIX_CLOSE_CHANNELS, ...SETTINGS_CHANNELS, ...MAINTAIN_CHANNELS, ...LINK_CHANNELS, ...QUICK_POPUP_CHANNELS, ...CRASH_CHANNELS, ...TEXT_FOCUS_CHANNELS, ...FORGET_CHANNELS]);
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
  assert.deepEqual(registered.sort(), [...EXPECTED_CHANNELS, ...KEEP_SAFE_CHANNELS, ...FIX_CLOSE_CHANNELS, ...SETTINGS_CHANNELS, ...MAINTAIN_CHANNELS, ...QUICK_POPUP_CHANNELS, ...CRASH_CHANNELS, ...TEXT_FOCUS_CHANNELS, ...FORGET_CHANNELS].sort(), 'ipc.js registered a channel outside the allowlist');
});

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

/* ==== App 06 (ticket A35): the Link items session channels are
   registered by wireRelateChannels inside ipc.js's App 06 block, and
   the two push channels are subscribed in the preload — the same pin
   as the Add block, so none can go dead or hidden. ==== */
test('the relate-session channels are preloaded, registered and pushed by name', () => {
  assert.ok(IPC.includes('wireRelateChannels'), 'ipc.js never wires the Link items session channels');
  for (const channel of ['ember:relateStart', 'ember:relateAnswer', 'ember:relateStop', 'ember:relateAttach']) {
    assert.ok(PRELOAD.includes(`'${channel}'`), `${channel} missing from the preload allowlist`);
    assert.ok(
      RELATE_SESSION_MODULE.includes(`ipcMain.handle('${channel}'`),
      `${channel} not registered by wireRelateChannels`,
    );
  }
  for (const channel of LINK_CHANNELS.slice(4)) {
    assert.ok(PRELOAD.includes(`'${channel}'`), `${channel} missing from the preload subscriptions`);
    assert.ok(RELATE_SESSION_MODULE.includes(`'${channel}'`), `${channel} missing from the main-process pushes`);
  }
});
/* ==== end App 06 block ==== */

/* ==== Batch 5 (story 24 / D-24's safety half): the window is a closed
   box — navigation and new windows are denied in main.js, pinned here
   statically next to the isolation switches so neither can regress. ==== */
test('the main window denies navigation and new windows (story 24)', () => {
  assert.match(MAIN, /webContents\.on\('will-navigate'/, 'main.js never registers will-navigate');
  const navigate = MAIN.match(/webContents\.on\('will-navigate'[\s\S]{0,200}/);
  assert.ok(navigate && navigate[0].includes('preventDefault()'), 'will-navigate must be denied with event.preventDefault()');
  assert.match(MAIN, /setWindowOpenHandler\(\s*\(\)\s*=>\s*\(\{\s*action:\s*'deny'\s*\}\)\s*\)/, 'setWindowOpenHandler must deny new windows');
});
/* ==== end Batch 5 story 24 block ==== */

/* ==== App 12 (ticket A41): the application menu's push channel is
   subscribed by the preload, sent by main by name, and never an
   invoke — pinned here so it cannot go dead or hidden. ==== */
test('the menu push channel is preloaded, sent by name, and reachable', () => {
  for (const channel of MENU_PUSH_CHANNELS) {
    assert.ok(PRELOAD.includes(`'${channel}'`), `${channel} missing from the preload subscriptions`);
    assert.ok(MAIN.includes(`'${channel}'`), `${channel} is never sent from main`);
    assert.ok(PRELOAD.includes('onMenuRequest'), 'onMenuRequest missing from the preload');
  }
  // The push adds no invoke channel: ipc.js did not grow a handler for it.
  const registered = [...IPC.matchAll(/'(ember:[a-zA-Z]+)':/g)].map((m) => m[1]);
  assert.ok(!registered.includes('ember:menuRequest'), 'the push channel must not be an invoke handler');
});
/* ==== end App 12 block ==== */

/* ==== Story 13 (finding 4.9 #14): the text-field focus push — the
   ONE boolean the renderer may hand main, so the Edit menu flips to
   Electron's text Undo/Redo roles while a field holds the keys (and
   back to the Ember derivation the moment none does). Pinned here so
   the route can neither go dead, grow, nor lose its wiring: invoke
   by name with a boolean, validated once in ipc.js, and main.js
   reading the value into the menu context and rebuilding on the
   flip. (The template half — context {textFieldFocused:true} ->
   roles with no dispatch — is menu-template.test.js's own pin.) ==== */
test('the text-focus channel is invoke-only by name, boolean-validated, and wired into the menu context (story 13)', () => {
  // Preload: one allowlist entry + one invoke; never a push subscription.
  assert.ok(PRELOAD.includes("'ember:textFocusChanged'"), 'ember:textFocusChanged missing from the preload allowlist');
  assert.match(PRELOAD, /textFocusChanged: \(focused\) => ipcRenderer\.invoke\('ember:textFocusChanged', focused\)/, 'the preload must expose exactly one invoke under this name');
  assert.equal((PRELOAD.match(/ember:textFocusChanged/g) ?? []).length, 2, 'the channel must appear only in the allowlist and the invoke (no subscription)');
  // ipc.js registers it and validates the payload ONCE at the edge.
  assert.match(IPC, /'ember:textFocusChanged':/, 'the text-focus channel is not registered in ipc.js');
  assert.match(IPC, /typeof payload !== 'boolean'/, 'the text-focus handler must validate the boolean itself');
  // main.js carries the value through: the hook reaches registerIpcHandlers,
  // the menu context reads the stored value, and the flip stores it.
  assert.match(MAIN, /onTextFocusChanged/, 'main.js never hands the focus change to ipc.js');
  assert.match(MAIN, /textFieldFocused: menuState\.textFieldFocused/, "the menu context does not carry the focus value");
  assert.match(MAIN, /menuState\.textFieldFocused = focused/, 'main.js never stores the pushed focus value');
});
/* ==== end story 13 block ==== */

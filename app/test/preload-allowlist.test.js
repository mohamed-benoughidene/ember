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
  // [app 10] the Settings panes
  'ember:registerShortcut',
  'ember:keyHint',
];

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
  assert.deepEqual(names, EXPECTED_CHANNELS);
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
  assert.deepEqual(registered.sort(), [...EXPECTED_CHANNELS].sort(), 'ipc.js registered a channel outside the allowlist');
});

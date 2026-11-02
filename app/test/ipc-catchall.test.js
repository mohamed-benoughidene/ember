'use strict';

/**
 * The IPC catch-all (Batch 5 chunk 18, story 25, finding 4.9 #19):
 * when a handler throws, the renderer gets a named APP- error with a
 * GENERIC sentence — never the raw error text, which can carry paths
 * and values. The raw error goes to the app's own stderr log (one
 * house line with the code, I20), never across the IPC edge.
 *
 * Fakes only (the keep-safe-ipc pattern): no Electron, no real
 * knowledge base. The handler is made to throw through the
 * settings-store seam; the throw propagates to the catch-all wrap.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { registerIpcHandlers } = require('../main/ipc');
const { errorPatternFixture } = require('./util');

function harness({ settingsLoad } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-catchall-'));
  const fakeIpcMain = {
    handlers: {},
    // ipcMain.handle wraps as (event, payload); adapt so tests call
    // with the payload only (the keep-safe-ipc pattern).
    handle(name, fn) {
      this.handlers[name] = async (payload) => fn(undefined, payload);
    },
  };
  registerIpcHandlers({
    ipcMain: fakeIpcMain,
    settingsStore: {
      load: settingsLoad ?? (() => ({ settings: { knowledgeBasePath: '' }, notice: null })),
      save: () => ({ ok: true }),
    },
    keyStore: {
      status: () => ({ stored: false, sessionOnly: false, backend: 'none' }),
      get: () => null,
      set: () => ({ ok: true }),
      setSessionOnly: () => ({ ok: true }),
      remove: () => ({ ok: true }),
    },
    apiKeyProvider: () => null,
    errorPattern: errorPatternFixture(),
    emberCommand: ['node', '-e', ''],
    appVersion: '0.0.0',
    userDataPath: dir,
  });
  return {
    call: (name, payload) => fakeIpcMain.handlers[name](payload),
    cleanup: () => fs.rmSync(dir, { recursive: true, force: true }),
  };
}

test('a throwing IPC answer carries the code and a generic sentence, never the raw error', async () => {
  const h = harness({
    // The thrown message names a private path; NO part of it may ever
    // reach the renderer (story 25, 4.9 #19).
    settingsLoad: () => {
      throw new Error('failed to read /home secrets/ember.db');
    },
  });
  const logged = [];
  const originalWrite = process.stderr.write.bind(process.stderr);
  process.stderr.write = (chunk) => {
    logged.push(String(chunk));
    return true;
  };
  try {
    const result = await h.call('ember:getState');
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-002');
    assert.match(result.error.detail, /the call failed unexpectedly/i, 'a generic sentence, not the raw text');
    assert.doesNotMatch(
      result.error.detail,
      /home secrets|failed to read/,
      'no part of the thrown message crosses the IPC edge',
    );
    // The raw error stays in the app's own log: one house line, with
    // the code on it.
    const houseLines = logged.join('').split('\n').filter((line) => line.includes('APP-002'));
    assert.equal(houseLines.length, 1, 'exactly one house line logged');
    assert.match(houseLines[0], /^error: APP-002 /);
    assert.match(houseLines.join(''), /home secrets/, 'the raw text stays in the app log');
  } finally {
    process.stderr.write = originalWrite;
    h.cleanup();
  }
});

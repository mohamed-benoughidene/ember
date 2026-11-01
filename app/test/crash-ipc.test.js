'use strict';

/**
 * The crash-report IPC channels (Batch 2, Chunk 13): Copy crash report
 * (`ember:crashReport`) and Show file (`ember:crashReportFolder`).
 *
 * Injected fakes only (the repo's T3 pattern, as in shortcuts.test.js):
 * a fake clipboard, a fake shell, and a fake file reader. The real
 * ~/.local/state is NEVER touched — XDG_STATE_HOME points at a scratch
 * folder under /tmp/opencode/batch2/chunk13, and the fake reader never
 * reads the disk at all. The file LOCATION comes from
 * main/crash-file.js's crashPath (the merged N4 rule).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { registerIpcHandlers } = require('../main/ipc');
const { crashPath } = require('../main/crash-file');

const SCRATCH = '/tmp/opencode/batch2/chunk13';
process.env.XDG_STATE_HOME = path.join(SCRATCH, 'state');

const CRASH_ID = '20261101T120000Z-a1b2c3';
const CRASH_TEXT =
  'error: EMBER-000 InternalError | ember.cli.storage | crash=' + CRASH_ID + '\n' +
  'Traceback (most recent call last):\n' +
  '  RuntimeError: boom\n';

/**
 * Register the handlers on a fake ipcMain and return the fake table.
 * The other options are dummies: this test only invokes the two crash
 * channels, and these defaults resemble what main.js passes.
 */
function crashIpc() {
  const fake = {
    handlers: {},
    readCalls: [],
    clipboard: {
      writes: [],
      writeText(text) {
        this.writes.push(text);
      },
    },
    shell: {
      shown: [],
      showItemInFolder(p) {
        this.shown.push(p);
      },
    },
    // The injected reader: no disk access, canned text, records calls.
    // fake.missing stands in for "the file is not there" (a throw the
    // way ENOENT happens, still no disk access).
    readTextFile(p) {
      fake.readCalls.push(p);
      if (fake.missing) {
        const err = new Error(`ENOENT: no such file or directory, open '${p}'`);
        err.code = 'ENOENT';
        throw err;
      }
      return CRASH_TEXT;
    },
  };
  const ipcMain = {
    handle(name, fn) {
      fake.handlers[name] = fn;
    },
  };
  registerIpcHandlers({
    ipcMain,
    settingsStore: { load: () => ({ settings: {}, notice: null }), save: () => ({ ok: true }) },
    keyStore: {
      status: () => ({}),
      get: () => ({ state: 'none' }),
      set: () => ({}),
      setSessionOnly: () => ({}),
      remove: () => ({}),
    },
    apiKeyProvider: () => null,
    errorPattern: null,
    emberCommand: ['ember'],
    appVersion: '0.0.0-test',
    userDataPath: path.join(SCRATCH, 'user-data'),
    clipboard: fake.clipboard,
    shell: fake.shell,
    readTextFile: fake.readTextFile,
  });
  return fake;
}

test('the crash copy and show-file channels work on injected fakes', async () => {
  const fake = crashIpc();

  // --- Copy crash report: the whole text goes to the clipboard. ---
  const copy = fake.handlers['ember:crashReport'];
  assert.equal(typeof copy, 'function', 'ember:crashReport is not registered in main/ipc.js');
  const copyResult = await copy(null, { crashId: CRASH_ID });
  // The file is found through crashPath, not hand-built.
  assert.deepEqual(fake.readCalls, [crashPath(CRASH_ID)], 'the file was not read at its crashPath location');
  // The WHOLE text is copied — the proof: the handler must hand the
  // reader's full return value to the clipboard.
  assert.deepEqual(fake.clipboard.writes, [CRASH_TEXT], 'the clipboard did not receive the whole file text');
  assert.deepEqual(copyResult, { ok: true, text: CRASH_TEXT }, 'the handler did not return the crash text');

  // --- Show file: the injected shell reveals the crash FILE itself. ---
  const folder = fake.handlers['ember:crashReportFolder'];
  assert.equal(typeof folder, 'function', 'ember:crashReportFolder is not registered in main/ipc.js');
  const folderResult = await folder(null, { crashId: CRASH_ID });
  assert.deepEqual(fake.shell.shown, [crashPath(CRASH_ID)], 'the shell was not pointed at the crash FILE');
  assert.deepEqual(folderResult, { ok: true, path: crashPath(CRASH_ID) });

  // --- A missing crash file: a plain APP-002 refusal, never a crash. ---
  fake.missing = true;
  const missingResult = await copy(null, { crashId: CRASH_ID });
  assert.equal(missingResult.ok, false, 'a missing file must not answer ok');
  assert.equal(missingResult.error.code, 'APP-002', 'the refusal is not APP-002-shaped');
  assert.equal(typeof missingResult.error.name, 'string');
  assert.equal(typeof missingResult.error.where, 'string');
  assert.equal(typeof missingResult.error.detail, 'string');
  // No clipboard write happened for a file that is not there.
  assert.deepEqual(fake.clipboard.writes, [CRASH_TEXT], 'the clipboard was touched for a missing file');});

'use strict';

/**
 * The step-09 IPC handlers (ticket A38), against fakes for everything
 * Electron: the save-dialog adapter, the shape backstop before any
 * child starts (I9), the summary mapping for backup, and the story-76
 * order in switchKnowledgeBase — file check, then db-check, and only
 * then the settings change.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { registerIpcHandlers } = require('../main/ipc');
const { errorPatternFixture } = require('./util');

const FAKE_EMBER = `
'use strict';
const argv = process.argv.slice(2); // ['backup'|'export'|'db-check', '--db', db, ...]
const command = argv[0];
if (command === 'db-check') {
  const result = process.env.FAKE_DBCHECK_RESULT === 'UNREADABLE' ? 'UNREADABLE' : 'OK';
  process.stdout.write(JSON.stringify({
    changes: [], command: 'db-check', dry_run: false,
    summary: { result,
      detail: result === 'UNREADABLE' ? 'db file missing' : null,
      lines: ['version: 13', 'result: ' + result] },
  }));
  process.exit(result === 'OK' ? 0 : 1);
}
if (command === 'backup') {
  const target = argv[3]; // backup --db <db> <TARGET> --format json
  process.stdout.write(JSON.stringify({
    changes: [], command: 'backup', dry_run: false,
    summary: { path: target, schema_version: 13, item_count: 2, rotated: null },
  }));
  process.exit(0);
}
if (command === 'export') {
  process.stdout.write('exported 2 items -> ' + (argv[3] === '--out' ? argv[4] : 'stdout'));
  process.exit(0);
}
process.stderr.write('error: QUERY-003 KnowledgeBaseMissing | x | nope\\n');
process.exit(1);
`;

function harness({ settings } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-ksipc-'));
  const fakeFile = path.join(dir, 'fake-ember.js');
  fs.writeFileSync(fakeFile, FAKE_EMBER);
  const savedPatches = [];
  const commands = [];
  const fakeIpcMain = {
    handlers: {},
    // ipcMain.handle wraps as (event, payload); adapt so tests call with payload only.
    handle(name, fn) {
      this.handlers[name] = async (payload) => fn(undefined, payload);
    },
  };
  const kbFile = path.join(dir, 'kb.db');
  fs.writeFileSync(kbFile, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(2000, 0)]));
  registerIpcHandlers({
    ipcMain: fakeIpcMain,
    settingsStore: {
      load: () => ({ settings: { knowledgeBasePath: settings?.knowledgeBasePath ?? kbFile }, notice: null }),
      save: (patch) => {
        savedPatches.push(patch);
        return { ok: true };
      },
    },
    keyStore: { status: () => ({ stored: false, sessionOnly: false, backend: 'none' }), get: () => null, set: () => ({ ok: true }), setSessionOnly: () => ({ ok: true }), remove: () => ({ ok: true }) },
    apiKeyProvider: () => null,
    errorPattern: errorPatternFixture(),
    emberCommand: ['node', fakeFile],
    appVersion: '0.0.0',
    userDataPath: dir,
    saveChooser: ({ kind, defaultName }) => ({ kind, defaultName, path: path.join(dir, defaultName || 'chosen.db') }),
    onCommand: (name, args) => commands.push([name, args]),
  });
  return {
    call: (name, payload) => fakeIpcMain.handlers[name](payload),
    commands,
    savedPatches,
    kbFile,
    dir,
    cleanup: () => fs.rmSync(dir, { recursive: true, force: true }),
  };
}

test('pickSaveFile passes the ask to the dialog adapter; a cancel changes nothing', async () => {
  const h = harness();
  try {
    const ok = await h.call('ember:pickSaveFile', { kind: 'backup', defaultName: '/tmp/x/ember-backup.db' });
    assert.equal(ok.ok, true);
    assert.match(ok.path, /ember-backup\.db$/);
    assert.match(ok.path, /\/tmp\/x\/ember-backup\.db$/, 'the adapter receives the ask (kind + default name)');
    // No payload at all is a shape refusal at the edge (I9), not a dialog.
    const noAsk = await h.call('ember:pickSaveFile', null);
    assert.equal(noAsk.ok, false);
    assert.equal(noAsk.error.code, 'APP-002');
    const bad = await h.call('ember:pickSaveFile', { kind: 'rmrf' });
    assert.equal(bad.ok, false);
    assert.equal(bad.error.code, 'APP-002');
  } finally {
    h.cleanup();
  }
});

test('backupTo refuses an unusable path BEFORE any child starts, then maps the engine summary', async () => {
  const h = harness();
  try {
    const bad = await h.call('ember:backupTo', { targetPath: '' });
    assert.equal(bad.ok, false);
    assert.equal(bad.error.code, 'APP-002');
    const relative = await h.call('ember:backupTo', { targetPath: 'just-a-name.db' });
    assert.equal(relative.ok, false);
    assert.equal(relative.error.code, 'APP-002');
    assert.deepEqual(h.commands, [], 'no command may start for a path of the wrong shape (I9)');

    const target = path.join(h.dir, 'backup.db');
    const ok = await h.call('ember:backupTo', { targetPath: target });
    assert.equal(ok.ok, true);
    assert.deepEqual(ok.data, { path: target, schemaVersion: 13, itemCount: 2, rotated: null });
    assert.deepEqual(h.commands, [['backup', [target]]]);
  } finally {
    h.cleanup();
  }
});

test('exportTo is exit-code-driven and returns no document content', async () => {
  const h = harness();
  try {
    const target = path.join(h.dir, 'export.txt');
    const ok = await h.call('ember:exportTo', { outPath: target });
    assert.equal(ok.ok, true);
    assert.deepEqual(ok.data, { outPath: target });
    assert.deepEqual(h.commands, [['export', ['--out', target]]]);
    const bad = await h.call('ember:exportTo', { outPath: 'nope.txt' });
    assert.equal(bad.ok, false);
  } finally {
    h.cleanup();
  }
});
test('dbCheck runs against the chosen path when one is given, else the current one', async () => {
  const h = harness();
  try {
    const own = await h.call('ember:dbCheck', null);
    assert.equal(own.ok, true);
    assert.equal(own.data.result, 'OK');
    // An explicit path rides --db (the story-76 pre-check needs it).
    process.env.FAKE_DBCHECK_RESULT = 'UNREADABLE';
    const other = path.join(h.dir, 'other.db');
    fs.writeFileSync(other, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(10, 0)]));
    const report = await h.call('ember:dbCheck', { dbPath: other });
    assert.equal(report.ok, true, 'UNREADABLE is a report, not an error');
    assert.equal(report.data.result, 'UNREADABLE');
    delete process.env.FAKE_DBCHECK_RESULT;
  } finally {
    h.cleanup();
  }
});

test('switchKnowledgeBase: file check, then db-check, then the setting changes (story 76)', async () => {
  const h = harness();
  try {
    const oldPath = h.kbFile;

    // not an Ember file -> APP-006 before anything runs
    const garbage = path.join(h.dir, 'garbage.db');
    fs.writeFileSync(garbage, 'hello');
    const refused = await h.call('ember:switchKnowledgeBase', { path: garbage });
    assert.equal(refused.ok, false);
    assert.equal(refused.error.code, 'APP-006');
    assert.deepEqual(h.savedPatches, [], 'the setting must not change');
    assert.deepEqual(h.commands, [], 'and no command may start');

    // UNREADABLE per db-check -> APP-006, setting unchanged
    process.env.FAKE_DBCHECK_RESULT = 'UNREADABLE';
    const unreadable = path.join(h.dir, 'unreadable.db');
    fs.writeFileSync(unreadable, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(10, 0)]));
    const blocked = await h.call('ember:switchKnowledgeBase', { path: unreadable });
    assert.equal(blocked.ok, false);
    assert.equal(blocked.error.code, 'APP-006');
    assert.deepEqual(h.savedPatches, [], 'UNREADABLE must stop the setting change');
    delete process.env.FAKE_DBCHECK_RESULT;

    // a readable Ember file passes (a v12 file would too: no floor) ->
    // the setting changes exactly once, to the chosen path
    const chosen = path.join(h.dir, 'chosen.db');
    fs.writeFileSync(chosen, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(10, 0)]));
    const ok = await h.call('ember:switchKnowledgeBase', { path: chosen });
    assert.equal(ok.ok, true);
    assert.equal(ok.data.path, chosen);
    assert.deepEqual(h.savedPatches, [{ knowledgeBasePath: chosen }]);
    assert.equal(oldPath === chosen, false);
  } finally {
    delete process.env.FAKE_DBCHECK_RESULT;
    h.cleanup();
  }
});

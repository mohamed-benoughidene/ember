'use strict';

/**
 * The settings store tests (step file §2): schema validation, atomic
 * write, corrupt file -> defaults + APP-004, never a crash.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { normalizeSettings, DEFAULTS, SCHEMA_NUMBER } = require('../shared/settings-schema');
const { createSettingsStore } = require('../main/settings-store');

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ember-settings-'));
}

// --- the pure schema ----------------------------------------------------------

test('defaults carry exactly the four spec settings plus lastPane and the knowledge-base path', () => {
  assert.deepEqual(Object.keys(DEFAULTS).sort(), [
    'colourTheme',
    'knowledgeBasePath',
    'lastPane',
    'menuHidden',
    'menuOrder',
    'quickPopup',
    'schema',
    'textSize',
  ]);
  assert.equal(DEFAULTS.schema, SCHEMA_NUMBER);
});

test('nothing at all normalizes to clean defaults', () => {
  const { settings, schemaChanged } = normalizeSettings(undefined);
  assert.deepEqual(settings, DEFAULTS);
  assert.equal(schemaChanged, true);
});

test('a foreign or missing schema number costs the full defaults (D5)', () => {
  for (const raw of [{}, { schema: 99 }, { schema: '1' }]) {
    const { settings, schemaChanged } = normalizeSettings(raw);
    assert.equal(schemaChanged, true, JSON.stringify(raw));
    assert.deepEqual(settings, DEFAULTS, JSON.stringify(raw));
  }
});

test('a valid file keeps its values and repairs only the broken fields', () => {
  const { settings, schemaChanged } = normalizeSettings({
    schema: 1,
    textSize: 'large',
    colourTheme: 'dark',
    quickPopup: { shortcut: 'CommandOrControl+Shift+E', position: 'top-left' },
    menuOrder: ['lookup', 'add'],
    menuHidden: ['keepsafe'],
    lastPane: 'add',
    knowledgeBasePath: '/home/mo/kb.db',
  });
  assert.equal(schemaChanged, false);
  assert.equal(settings.textSize, 'large');
  assert.equal(settings.colourTheme, 'dark');
  assert.deepEqual(settings.quickPopup, { shortcut: 'CommandOrControl+Shift+E', position: 'top-left' });
  assert.deepEqual(settings.menuOrder, ['lookup', 'add']);
  assert.deepEqual(settings.menuHidden, ['keepsafe']);
  assert.equal(settings.lastPane, 'add');
  assert.equal(settings.knowledgeBasePath, '/home/mo/kb.db');
});

test('wrong per-field values fall back field by field, never crash', () => {
  const { settings, schemaChanged } = normalizeSettings({
    schema: 1,
    textSize: 42,
    colourTheme: 'sepia',
    quickPopup: 'nope',
    menuOrder: 'wrong',
    menuHidden: [1, 2],
    lastPane: 0,
    knowledgeBasePath: 7,
  });
  assert.equal(schemaChanged, false);
  assert.equal(settings.textSize, 'default');
  assert.equal(settings.colourTheme, 'system');
  assert.deepEqual(settings.quickPopup, DEFAULTS.quickPopup);
  assert.deepEqual(settings.menuOrder, DEFAULTS.menuOrder);
  assert.deepEqual(settings.menuHidden, []);
  assert.equal(settings.lastPane, 'home');
  assert.equal(settings.knowledgeBasePath, '');
});

test('unknown keys are dropped, not kept (D6: the schema is exact)', () => {
  const { settings } = normalizeSettings({ schema: 1, hackerField: 'x' });
  assert.equal('hackerField' in settings, false);
});

// --- the store (file effects) ---------------------------------------------------

test('a missing file is the clean first run: defaults, no notice', () => {
  const store = createSettingsStore({ file: path.join(tempDir(), 'settings.json') });
  const { settings, notice } = store.load();
  assert.deepEqual(settings, DEFAULTS);
  assert.equal(notice, null);
});

test('a corrupt file gives defaults and an APP-004 notice, never a crash', () => {
  const dir = tempDir();
  const file = path.join(dir, 'settings.json');
  fs.writeFileSync(file, '{"schema": 1, "textSize": "large", TRUNCATED');
  const { settings, notice } = createSettingsStore({ file }).load();
  assert.deepEqual(settings, DEFAULTS);
  assert.equal(notice.code, 'APP-004');
  assert.equal(notice.name, 'SettingsUnreadable');
});

test('an unreadable file (wrong permissions shape) gives APP-004, not a crash', () => {
  const dir = tempDir();
  const file = path.join(dir, 'settings.json');
  fs.writeFileSync(file, '{}');
  fs.chmodSync(file, 0o000);
  try {
    const { notice, settings } = createSettingsStore({ file }).load();
    if (process.getuid && process.getuid() !== 0) {
      assert.equal(notice.code, 'APP-004');
      assert.deepEqual(settings, DEFAULTS);
    }
  } finally {
    fs.chmodSync(file, 0o600);
  }
});

test('save round-trips: patch -> file -> load back identical, then a notice-free load', () => {
  const dir = tempDir();
  const file = path.join(dir, 'settings.json');
  const store = createSettingsStore({ file });
  const first = store.save({ textSize: 'largest', knowledgeBasePath: '/home/mo/kb.db', lastPane: 'lookup' });
  assert.equal(first.ok, true);
  assert.equal(first.settings.textSize, 'largest');
  const second = createSettingsStore({ file }).load();
  assert.equal(second.notice, null);
  assert.equal(second.settings.textSize, 'largest');
  assert.equal(second.settings.knowledgeBasePath, '/home/mo/kb.db');
  // SchemaPersisted: the saved document is versioned (D5).
  const onDisk = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.equal(onDisk.schema, SCHEMA_NUMBER);
});

test('save is atomic: no temp file left behind, content complete', () => {
  const dir = tempDir();
  const file = path.join(dir, 'settings.json');
  const store = createSettingsStore({ file });
  store.save({ textSize: 'small' });
  const entries = fs.readdirSync(dir);
  assert.deepEqual(entries, ['settings.json'], `leftovers: ${entries.join(', ')}`);
  JSON.parse(fs.readFileSync(file, 'utf8')); // would throw on a partial write
});

test('save repairs a corrupt file on the next save (the APP-004 promise)', () => {
  const dir = tempDir();
  const file = path.join(dir, 'settings.json');
  fs.writeFileSync(file, 'garbage{');
  const store = createSettingsStore({ file });
  assert.equal(store.load().notice.code, 'APP-004');
  const saved = store.save({ colourTheme: 'light' });
  assert.equal(saved.ok, true);
  assert.equal(saved.settings.colourTheme, 'light');
  assert.equal(store.load().notice, null);
});

test('a failed save reports APP-004 and leaves no partial file', () => {
  const dir = tempDir();
  const file = path.join(dir, 'no-such-subdir', 'settings.json');
  const store = createSettingsStore({
    file,
    // A fake fsImpl whose mkdirSync refuses, simulating an immutable dir.
    fsImpl: {
      ...fs,
      mkdirSync: () => {
        throw new Error('read-only file system');
      },
    },
  });
  const result = store.save({ textSize: 'small' });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-004');
  assert.equal(fs.existsSync(file), false);
});

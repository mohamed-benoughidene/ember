'use strict';

/** APP-006 and APP-007: the knowledge-base and runtime guards. */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { resolveEmberCommand, checkEmberCommand, validateKnowledgeBasePath } = require('../main/ember-command');

test('the ember command comes from the env override or falls back to PATH', () => {
  assert.deepEqual(resolveEmberCommand({ EMBER_APP_COMMAND: '' }), ['ember']);
  assert.deepEqual(resolveEmberCommand({ EMBER_APP_COMMAND: 'node /x/fake-ember.js' }), [
    'node',
    '/x/fake-ember.js',
  ]);
  assert.deepEqual(resolveEmberCommand({}), ['ember']);
});

test('APP-007: a path-shaped ember command that does not exist is refused at boot', () => {
  const result = checkEmberCommand(['/nowhere/no-ember']);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-007');
  assert.equal(result.error.name, 'RuntimeMissing');
  assert.deepEqual(checkEmberCommand(['ember']), { ok: true }, 'a bare PATH name cannot be pre-checked');
  assert.deepEqual(checkEmberCommand([process.execPath, '/dev/null']), { ok: true });
});

test('APP-006: an empty choice is reported, not swallowed', () => {
  const result = validateKnowledgeBasePath('');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-006');
  assert.equal(result.error.name, 'KnowledgeBaseMissing');
});

test('APP-006: a missing file, a directory and a non-SQLite file are all refused', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-kb-'));
  const results = [
    validateKnowledgeBasePath(path.join(dir, 'missing.db')),
    validateKnowledgeBasePath(dir),
    validateKnowledgeBasePath(path.join(dir, 'garbage.db')),
  ];
  const notSqlite = (() => {
    fs.writeFileSync(path.join(dir, 'garbage.db'), 'just some text, not a database');
    return validateKnowledgeBasePath(path.join(dir, 'garbage.db'));
  })();
  for (const result of [...results, notSqlite]) {
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-006');
  }
});

test('a file that carries the SQLite header passes the cheap check', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-kb-'));
  const file = path.join(dir, 'kb.db');
  const buf = Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(96, 0)]);
  fs.writeFileSync(file, buf);
  assert.deepEqual(validateKnowledgeBasePath(file), { ok: true });
});

test('a REAL knowledge base (made by the project venv) passes the check', () => {
  const python = path.join(__dirname, '..', '..', '.venv', 'bin', 'python');
  assert.ok(fs.existsSync(python), `the project venv python is missing at ${python}`);
  const { execFileSync } = require('node:child_process');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-kb-'));
  const file = path.join(dir, 'kb.db');
  execFileSync(python, ['-c', `from tests.bridge import harness; harness.seed_pair(${JSON.stringify(file)})`], {
    cwd: path.join(__dirname, '..', '..'),
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  assert.deepEqual(validateKnowledgeBasePath(file), { ok: true });
});

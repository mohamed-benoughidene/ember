'use strict';

/**
 * The undo-label gate's unit tests (app step 12's rule; A43 fix; the
 * G2 decision, 2026-11-01): the probe is now the ENGINE's read-only
 * `ember db-check` — the app never opens the knowledge base file
 * itself (rule B2). A real v13 file passes, a real v12 file refuses
 * (the whole file must stay BYTE-IDENTICAL with no `.bak-v12`, the
 * never-migrate proof), a non-database file and a missing path fail
 * closed, and an engine that cannot answer refuses too.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const { schemaVersionIsAtLeast } = require('../main/kb-schema-version');
const { PYTHON, REPO_ROOT, errorPatternFixture } = require('./util');

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ember-kbschema-'));
}

function seed(dbPath, statementTemplate) {
  execFileSync(PYTHON, ['-c', statementTemplate.replace('__DB__', JSON.stringify(dbPath))], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
}

const seedV12 = 'from tests.test_v12_read_never_migrates import _build_v12_db as f; f(__DB__)';

test('a real v13 knowledge base passes the undo-label gate (engine db-check)', async () => {
  assert.ok(fs.existsSync(EMBER), `the ember CLI is missing at ${EMBER}`);
  const dir = tempDir();
  const dbPath = path.join(dir, 'kb.db');
  seed(dbPath, 'from tests.bridge import harness as h; h.seed_pair(__DB__)');
  const ok = await schemaVersionIsAtLeast(dbPath, 13, {
    emberCommand: [EMBER],
    errorPattern: errorPatternFixture(),
  });
  assert.equal(ok, true);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a real v12 file refuses, stays BYTE-IDENTICAL, and no .bak-v12 appears', async () => {
  const dir = tempDir();
  const dbPath = path.join(dir, 'kb.db');
  seed(dbPath, seedV12);
  const before = fs.readFileSync(dbPath);
  const ok = await schemaVersionIsAtLeast(dbPath, 13, {
    emberCommand: [EMBER],
    errorPattern: errorPatternFixture(),
  });
  assert.equal(ok, false, 'a v12 file must refuse the undo-label derivation');
  assert.deepEqual(fs.readFileSync(dbPath), before, 'the probe must never rewrite the file');
  assert.equal(fs.existsSync(`${dbPath}.bak-v12`), false, 'the probe must never back up (that would mean a migration)');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a file that is not a database fails closed', async () => {
  const dir = tempDir();
  const dbPath = path.join(dir, 'kb.db');
  fs.writeFileSync(dbPath, 'definitely not sqlite');
  const ok = await schemaVersionIsAtLeast(dbPath, 13, {
    emberCommand: [EMBER],
    errorPattern: errorPatternFixture(),
  });
  assert.equal(ok, false);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a missing path fails closed', async () => {
  const dir = tempDir();
  const dbPath = path.join(dir, 'not-there.db');
  const ok = await schemaVersionIsAtLeast(dbPath, 13, {
    emberCommand: [EMBER],
    errorPattern: errorPatternFixture(),
  });
  assert.equal(ok, false);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('an engine that cannot answer fails closed (the injected seam)', async () => {
  const dbPath = path.join(tempDir(), 'kb.db');
  fs.writeFileSync(dbPath, 'SQLite format 3\x00placeholder');
  const ok = await schemaVersionIsAtLeast(
    dbPath,
    13,
    { emberCommand: ['this-binary-does-not-exist'], errorPattern: errorPatternFixture() },
    async () => ({ ok: false, error: { code: 'APP-001', name: 'BridgeSpawnFailed', where: 'test', detail: 'spawn failed' } }),
  );
  assert.equal(ok, false);
  fs.rmSync(path.dirname(dbPath), { recursive: true, force: true });
});

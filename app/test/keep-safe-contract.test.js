'use strict';

/**
 * The step-09 contract tests (app step file §2; ticket A38): on a REAL
 * temp knowledge base seeded by the Python test helpers, the Keep safe
 * commands through the app's own code paths must equal what the same
 * `ember` command prints directly (spec "one test seam"), the forbidden
 * actions stay forbidden, and the live file is byte-identical after
 * everything (the hash proof; D7: read-only means read-only).
 *
 * App side = the step-02 bridge client (runCommand) exactly as ipc.js
 * calls it, plus the step-09 db-check runner. The seeders and the
 * direct runs are the Python venv (run from the WORKTREE root, so the
 * worktree's own ember/ and tests/ code is what runs).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync, spawnSync } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createBridgeClient } = require('../main/bridge-client');
const { runDbCheck } = require('../main/db-check-runner');
const { REPO_ROOT, errorPatternFixture } = require('./util');

// The worktree has no .venv of its own; the interpreter lives in the
// main checkout (setup instruction) while the CODE comes from the
// worktree via the working directory.
const PYTHON = fs.existsSync(path.join(REPO_ROOT, '.venv', 'bin', 'python'))
  ? path.join(REPO_ROOT, '.venv', 'bin', 'python')
  : '/home/mo/lab/ember/.venv/bin/python';
const EMBER_ARGV = [PYTHON, '-m', 'ember'];

// `python -m ember` resolves the package from the working directory:
// pin it to the worktree root for every child, whatever dir npm ran in.
if (!process.cwd().startsWith(REPO_ROOT)) process.chdir(REPO_ROOT);

function seed(kind) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `ember-kscontract-${kind}-`));
  const dbPath = path.join(dir, 'kb.db');
  execFileSync(PYTHON, ['-c', `from tests.bridge import harness; harness.${kind}(${JSON.stringify(dbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  return { dir, dbPath };
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function clientFor(dbPath) {
  return createBridgeClient({ emberCommand: EMBER_ARGV, dbPath, errorPattern: errorPatternFixture(), timeoutReadMs: 30000 });
}

/** The direct CLI result of a one-shot command that prints a document. */
function directDoc(db, args) {
  const out = spawnSync(PYTHON, ['-m', 'ember', ...args, '--db', db], { encoding: 'utf8' });
  return { text: out.stdout, status: out.status, stderr: out.stderr };
}

test('backup through the app equals ember backup: same report, and the copy reads back', async () => {
  const { dir, dbPath } = seed('seed_pair');
  const direct = directDoc(dbPath, ['backup', path.join(dir, 'direct.db'), '--format', 'json']);
  assert.equal(direct.status, 0, direct.stderr);
  const appResult = await clientFor(dbPath).runCommand('backup', [path.join(dir, 'app.db')]);
  assert.equal(appResult.ok, true, JSON.stringify(appResult.error ?? {}));
  const directSummary = JSON.parse(direct.text).summary;
  // The pinned summary keys, exactly: path, schema_version, item_count, rotated.
  assert.deepEqual(Object.keys(directSummary).sort(), ['item_count', 'path', 'rotated', 'schema_version']);
  // runCommand returns the whole document; the ipc layer reads .summary.
  const appSummary = appResult.data.summary;
  assert.equal(appSummary.schema_version, directSummary.schema_version);
  assert.equal(appSummary.item_count, directSummary.item_count);
  assert.equal(appSummary.rotated, null);
  assert.deepEqual(Object.keys(appSummary).sort(), ['item_count', 'path', 'rotated', 'schema_version'], 'the app-side summary carries the pinned keys');
  // The file reads back: checking the copy with db-check reports OK.
  const copyCheck = await runDbCheck({ emberCommand: EMBER_ARGV, errorPattern: errorPatternFixture(), dbPath: appSummary.path });
  assert.equal(copyCheck.ok, true);
  assert.equal(copyCheck.data.result, 'OK');
  assert.equal(copyCheck.data.lines[0], `version: ${directSummary.schema_version}`);
}, 60000);

test('export through the app writes the same BYTES as ember export --out (the app reads no export JSON)', async () => {
  const { dir, dbPath } = seed('seed_pair');
  const cli = spawnSync(PYTHON, ['-m', 'ember', 'export', '--out', path.join(dir, 'direct.txt'), '--db', dbPath], { encoding: 'utf8' });
  assert.equal(cli.status, 0, cli.stderr);
  const appResult = await clientFor(dbPath).runCommand('export', ['--out', path.join(dir, 'app.txt')]);
  assert.equal(appResult.ok, true, JSON.stringify(appResult.error ?? {}));
  assert.equal(appResult.data, null, 'the app reads no export JSON: data comes back null');
  assert.equal(sha256(path.join(dir, 'app.txt')), sha256(path.join(dir, 'direct.txt')), 'export bytes must be identical');
}, 60000);

test('db-check through the app equals the engine report, line for line', async () => {
  const { dbPath } = seed('seed_pair');
  const direct = directDoc(dbPath, ['db-check', '--format', 'json']);
  assert.equal(direct.status, 0);
  const directSummary = JSON.parse(direct.text).summary;
  const appResult = await runDbCheck({ emberCommand: EMBER_ARGV, errorPattern: errorPatternFixture(), dbPath });
  assert.equal(appResult.ok, true);
  assert.deepEqual(appResult.data.lines, directSummary.lines);
  assert.equal(appResult.data.result, directSummary.result);
  assert.equal(appResult.data.result, 'OK');
}, 60000);

test('the FORBIDDEN actions stay forbidden through the app: backup onto the file, export onto the file', async () => {
  const { dbPath } = seed('seed_pair');
  const hashBefore = sha256(dbPath);

  const backup = await clientFor(dbPath).runCommand('backup', [dbPath]);
  assert.equal(backup.ok, false, 'backing up ONTO the knowledge base must be refused (story 72)');
  assert.equal(backup.error.code, 'BACKUP-003', 'the engine owns the refusal');

  const exp = await clientFor(dbPath).runCommand('export', ['--out', dbPath]);
  assert.equal(exp.ok, false, 'exporting OVER the knowledge base must be refused');
  assert.equal(exp.error.code, 'EXPORT-002');

  assert.equal(sha256(dbPath), hashBefore, 'the knowledge base file is byte-identical after both refusals');
}, 60000);

test('rotation: backing up twice to one name keeps the older copy as .old-1 and says so', async () => {
  const { dir, dbPath } = seed('seed_pair');
  const client = clientFor(dbPath);
  const target = path.join(dir, 'rotation.db');
  const first = await client.runCommand('backup', [target]);
  assert.equal(first.ok, true);
  assert.equal(first.data.summary.rotated, null);
  const second = await client.runCommand('backup', [target]);
  assert.equal(second.ok, true);
  assert.equal(second.data.summary.rotated, `${target}.old-1`);
  assert.ok(fs.existsSync(`${target}.old-1`), 'the older copy exists');
}, 60000);

test('UNREADABLE and DRIFT come back as REPORTS; the hash proof holds across every read', async () => {
  const { dir, dbPath } = seed('seed_pair');
  const client = clientFor(dbPath);

  // UNREADABLE: a file full of garbage is a report, not a crash.
  const garbage = path.join(dir, 'garbage.db');
  fs.writeFileSync(garbage, 'not a database at all');
  const unreadable = await runDbCheck({ emberCommand: EMBER_ARGV, errorPattern: errorPatternFixture(), dbPath: garbage });
  assert.equal(unreadable.ok, true, 'UNREADABLE is data for the screen');
  assert.equal(unreadable.data.result, 'UNREADABLE');

  // DRIFT: a real knowledge base with one enforcement trigger dropped.
  const drifted = path.join(dir, 'drift.db');
  fs.copyFileSync(dbPath, drifted);
  execFileSync(
    PYTHON,
    ['-c', `import sqlite3; c = sqlite3.connect(${JSON.stringify(drifted)}); c.execute("DROP TRIGGER items_closed_reason_insert"); c.commit()`],
    { cwd: REPO_ROOT },
  );
  const drift = await runDbCheck({ emberCommand: EMBER_ARGV, errorPattern: errorPatternFixture(), dbPath: drifted });
  assert.equal(drift.ok, true, 'DRIFT is data for the screen');
  assert.equal(drift.data.result, 'DRIFT');
  assert.ok(drift.data.lines.some((l) => l.startsWith('triggers: missing')));

  // Hash proof: live KB byte-identical after backup, export, db-check (D7).
  const hashBefore = sha256(dbPath);
  assert.equal((await client.runCommand('backup', [path.join(dir, 'h.db')])).ok, true);
  assert.equal((await client.runCommand('export', ['--out', path.join(dir, 'h.txt')])).ok, true);
  const afterCheck = await runDbCheck({ emberCommand: EMBER_ARGV, errorPattern: errorPatternFixture(), dbPath });
  assert.equal(afterCheck.data.result, 'OK');
  assert.equal(sha256(dbPath), hashBefore, 'backup + export + db-check must not touch one live byte');
}, 60000);

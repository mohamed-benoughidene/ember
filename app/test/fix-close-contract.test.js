'use strict';

/**
 * The step-07 contract tests (app step file §2), on REAL temp
 * knowledge bases seeded by the Python test harness — the same
 * one-test-seam rule as the step-04 suite: what the app's calls do
 * must equal what the matching `ember` command does, and a forbidden
 * action stays forbidden through the app.
 *
 * - close-item: the app's `--dry-run --format json` preview equals the
 *   CLI's byte for byte; the applied write equals the CLI write on a
 *   byte-identical twin file (the dependent becomes Challenged).
 * - undo/redo: the dry-run summary carries the pinned keys
 *   (direction, source_group_id, source_action, target_label) and
 *   equals the CLI's; applying through the app lands the same state as
 *   the CLI, twice in a row (story 117: undo steps back newest first).
 * - Forbidden stays forbidden: `set-status` on a Closed item exits 1
 *   with the engine's own code (MAINTAIN-006, story 51), the
 *   validated mark refuses non-Assumptions (CAPTURE-016, story 53),
 *   and a deliberately wrong argv never leaves the app (the builder
 *   throws — covered in fix-close-args.test.js).
 * - Story 118 through the app: undo is refused after a sweep changed
 *   the touched item (MAINTAIN-025), and writes nothing.
 * - Story 120 (the shield): a set-status CHALLENGED->Active made
 *   through the app shields the item; a control file where the SAME
 *   change was made by the CLI behaves identically under the sweep.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createBridgeClient } = require('../main/bridge-client');
const { PYTHON, REPO_ROOT, errorPatternFixture } = require('./util');

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');
const PY = (code) => execFileSync(PYTHON, ['-c', code], { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] });

function seed(kind, dir) {
  const dbPath = path.join(dir, 'kb.db');
  PY(`from tests.bridge import harness; harness.${kind}(${JSON.stringify(dbPath)})`);
  return dbPath;
}

function clientFor(dbPath) {
  return createBridgeClient({
    emberCommand: [EMBER],
    dbPath,
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 30000,
  });
}

function cli(args) {
  return JSON.parse(execFileSync(EMBER, args, { encoding: 'utf8' }));
}

function itemStatus(dbPath, itemId) {
  const out = cli(['show-item', '--item', String(itemId), '--db', dbPath]);
  return [out.item.status, out.item.close_reason];
}

function freshDir(name) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `ember-fix-${name}-`));
}

test('the close preview and write equal the CLI on twin files (stories 56-59)', async () => {
  const dir = freshDir('close');
  const dbApp = seed('seed_pair', dir);
  const dbCli = path.join(dir, 'twin.db');
  fs.copyFileSync(dbApp, dbCli);
  const client = clientFor(dbApp);

  // The preview: the app's dry-run document equals the CLI's, byte for
  // byte (the dependent count story 57 rides on `changes`).
  const preview = await client.runCommand('close-item', ['--item', '1', '--reason', 'invalidated', '--dry-run']);
  assert.equal(preview.ok, true, JSON.stringify(preview.error ?? {}));
  const direct = cli(['close-item', '--item', '1', '--reason', 'invalidated', '--dry-run', '--format', 'json', '--db', dbApp]);
  assert.deepEqual(preview.data, direct);
  const dependents = preview.data.changes.filter((c) => c.trigger_cause === 'dependency_closed');
  assert.equal(dependents.length, 1);
  assert.equal(dependents[0].item_id, 2); // the list story 57 needs
  assert.equal(preview.data.summary.closed, 1);

  // The write: same state as the CLI run on the twin file, and the
  // dry-run wrote nothing before it.
  assert.deepEqual(itemStatus(dbApp, 1), ['Active', null]); // preview did not write
  const applied = await client.runCommand('close-item', ['--item', '1', '--reason', 'invalidated']);
  assert.equal(applied.ok, true, JSON.stringify(applied.error ?? {}));
  execFileSync(EMBER, ['close-item', '--item', '1', '--reason', 'invalidated', '--db', dbCli], { stdio: 'ignore' });
  assert.deepEqual(itemStatus(dbApp, 1), ['Closed', 'invalidated']);
  assert.deepEqual(itemStatus(dbApp, 2), ['Challenged', null], 'the dependent is challenged by both paths alike');
  assert.deepEqual(itemStatus(dbCli, 2), itemStatus(dbApp, 2));
}, 60000);

test('undo and redo through the app equal the CLI (stories 111-112, 115-117)', async () => {
  const dir = freshDir('undo');
  const dbApp = seed('seed_closed', dir);
  const dbCli = path.join(dir, 'twin.db');
  fs.copyFileSync(dbApp, dbCli);
  const client = clientFor(dbApp);

  // The dry-run plan: pinned keys, equal to the CLI's.
  const plan = await client.runCommand('undo', ['--dry-run']);
  assert.equal(plan.ok, true, JSON.stringify(plan.error ?? {}));
  const direct = cli(['undo', '--dry-run', '--format', 'json', '--db', dbApp]);
  assert.deepEqual(plan.data, direct);
  for (const key of ['direction', 'source_group_id', 'source_action', 'target_label']) {
    assert.ok(key in plan.data.summary, `the label derivation needs summary.${key}`);
  }
  assert.equal(plan.data.summary.direction, 'undo');
  assert.equal(plan.data.summary.source_action, 'close-item');
  assert.equal(plan.data.summary.target_label, 'item 1');
  assert.equal(plan.data.summary.new_group_id, null); // nothing written on a dry run

  // Apply through the app; the state equals the CLI twin's.
  const done = await client.runCommand('undo', []);
  assert.equal(done.ok, true, JSON.stringify(done.error ?? {}));
  execFileSync(EMBER, ['undo', '--db', dbCli], { stdio: 'ignore' });
  assert.deepEqual(itemStatus(dbApp, 1), ['Active', null], 'undoing the close reopens the item');
  assert.deepEqual(itemStatus(dbCli, 1), itemStatus(dbApp, 1));
  assert.deepEqual(itemStatus(dbCli, 2), itemStatus(dbApp, 2));

  // Redo the same way.
  const redone = await client.runCommand('redo', []);
  assert.equal(redone.ok, true, JSON.stringify(redone.error ?? {}));
  assert.equal(redone.data.summary.direction, 'redo');
  assert.deepEqual(itemStatus(dbApp, 1), ['Closed', 'expired']);

  // Story 117: undo steps back newest first, twice in a row.
  const undo2 = await client.runCommand('undo', []);
  assert.equal(undo2.ok, true, JSON.stringify(undo2.error ?? {}));
  assert.deepEqual(itemStatus(dbApp, 1), ['Active', null]);
}, 60000);

test('forbidden actions stay forbidden through the app (stories 51, 53)', async () => {
  const dir = freshDir('forbidden');
  const dbApp = seed('seed_closed', dir); // item 1 Closed, item 2 Active Decision
  const client = clientFor(dbApp);

  // set-status on a Closed item: the engine's own refusal (MAINTAIN-006).
  const refused = await client.runCommand('set-status', ['--item', '1', '--to', 'Active']);
  assert.equal(refused.ok, false);
  assert.equal(refused.error.code, 'MAINTAIN-006');
  assert.deepEqual(itemStatus(dbApp, 1), ['Closed', 'expired'], 'nothing written');

  // The validated mark on a non-Assumption (story 53's forced path).
  const notAssumption = await client.runCommand('set-validated', ['--item', '2']);
  assert.equal(notAssumption.ok, false);
  assert.equal(notAssumption.error.code, 'CAPTURE-016');
}, 60000);

test('undo refused after a sweep changed the touched item (story 118)', async () => {
  const dir = freshDir('refusal');
  const dbPath = path.join(dir, 'kb.db');
  // The undo suite's own scenario: set-status to Active shields item 5;
  // a NEWER contradicts link lets the sweep un-shield and challenge it;
  // the undo must refuse and write nothing.
  PY(`from ember.adapters.sqlite import open_maintain_database; from tests.fakes import insert_item, insert_source
__import__('pathlib').Path(${JSON.stringify(dbPath)}).touch()
conn = open_maintain_database(${JSON.stringify(dbPath)})
sid = insert_source(conn)
insert_item(conn, source_id=sid, item_id=1, item_type='Finding')
insert_item(conn, source_id=sid, item_id=5, item_type='Decision', status='Challenged')
conn.commit(); conn.close()
`);
  execFileSync(EMBER, ['set-status', '--item', '5', '--to', 'Active', '--db', dbPath], { stdio: 'ignore' });
  PY(`from ember.adapters.sqlite import open_maintain_database; from tests.fakes import insert_link_with_confirmation
conn = open_maintain_database(${JSON.stringify(dbPath)})
insert_link_with_confirmation(conn, 1, 5, 'contradicts', created_at='2999-01-01T00:00:00+00:00')
conn.commit(); conn.close()
`);
  execFileSync(EMBER, ['maintain', '--db', dbPath], { stdio: 'ignore' });
  assert.deepEqual(itemStatus(dbPath, 5), ['Challenged', null], 'the sweep un-shielded and re-challenged the item');

  const client = clientFor(dbPath);
  const before = fs.readFileSync(dbPath);
  const refused = await client.runCommand('undo', []);
  const after = fs.readFileSync(dbPath);
  assert.equal(refused.ok, false);
  assert.equal(refused.error.code, 'MAINTAIN-025');
  assert.match(refused.error.name, /UndoRefused/);
  assert.deepEqual(after, before, 'a refusal writes zero rows');
  // ...and the honest disabled words do NOT fire for this code (the
  // click is where story 118's sentence shows, with Try again).
  const { undoDisabledReason } = await import('../shared/undo-labels.mjs');
  assert.equal(undoDisabledReason(refused.error), null);
}, 60000);

test('a shielded set-status made through the app behaves like the CLI one under the sweep (story 120)', async () => {
  const dir = freshDir('shield');
  const dbApp = path.join(dir, 'app.db');
  const dbCli = path.join(dir, 'cli.db');
  PY(`from ember.adapters.sqlite import open_maintain_database; from tests.fakes import insert_item, insert_source, insert_link_with_confirmation
for p in (${JSON.stringify(dbApp)}, ${JSON.stringify(dbCli)}):
    __import__('pathlib').Path(p).touch()
    conn = open_maintain_database(p)
    sid = insert_source(conn)
    insert_item(conn, source_id=sid, item_id=1, item_type='Finding')
    insert_item(conn, source_id=sid, item_id=5, item_type='Decision', status='Challenged')
    insert_link_with_confirmation(conn, 1, 5, 'contradicts')
    conn.commit(); conn.close()
`);
  // The SAME human move on both files: once through the app's client.
  const client = clientFor(dbApp);
  const done = await client.runCommand('set-status', ['--item', '5', '--to', 'Active']);
  assert.equal(done.ok, true, JSON.stringify(done.error ?? {}));
  execFileSync(EMBER, ['set-status', '--item', '5', '--to', 'Active', '--db', dbCli], { stdio: 'ignore' });

  // The sweep challenges both alike (the manual shield holds).
  execFileSync(EMBER, ['maintain', '--db', dbApp], { stdio: 'ignore' });
  execFileSync(EMBER, ['maintain', '--db', dbCli], { stdio: 'ignore' });
  assert.deepEqual(itemStatus(dbApp, 5), ['Active', null], 'the app-made shield holds like the CLI-made one');
  assert.deepEqual(itemStatus(dbCli, 5), itemStatus(dbApp, 5));

  // Undo through the app restores the earlier protection exactly: the
  // sweep afterwards behaves as it did before the change, on both files.
  const undone = await client.runCommand('undo', []);
  assert.equal(undone.ok, true, JSON.stringify(undone.error ?? {}));
  execFileSync(EMBER, ['undo', '--db', dbCli], { stdio: 'ignore' });
  assert.deepEqual(itemStatus(dbApp, 5), ['Challenged', null]);
  execFileSync(EMBER, ['maintain', '--db', dbApp], { stdio: 'ignore' });
  execFileSync(EMBER, ['maintain', '--db', dbCli], { stdio: 'ignore' });
  assert.deepEqual(itemStatus(dbApp, 5), ['Challenged', null], 'the revived shield behaves as before');
  assert.deepEqual(itemStatus(dbCli, 5), itemStatus(dbApp, 5));
}, 60000);

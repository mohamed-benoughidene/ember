'use strict';

/**
 * The step-04 contract tests (app step file §2): on a REAL temp
 * knowledge base seeded by the Python test helpers, the app's reads
 * must equal what the matching `ember` command prints — spec "counts
 * match exactly" and "one test seam".
 *
 * - Home's per-status counts and total come from FILTERED `list-items`
 *   calls; each total must equal the direct CLI run, and the
 *   Active+Challenged counts must equal `ember current-state`'s count.
 * - The provenance view reads `show-item`: its envelope (item, source,
 *   links_out, links_in) and the per-link other-item fields are pinned.
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

function seed(kind) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `ember-contract-${kind}-`));
  const dbPath = path.join(dir, 'kb.db');
  execFileSync(PYTHON, ['-c', `from tests.bridge import harness; harness.${kind}(${JSON.stringify(dbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
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

function cliJson(args) {
  return JSON.parse(execFileSync(EMBER, args, { encoding: 'utf8' }));
}

test('home counts equal list-items and current-state on a seeded KB', async () => {
  assert.ok(fs.existsSync(EMBER), 'the venv ember is missing — the contract test cannot run');
  const dbPath = seed('seed_contradicted_active');
  const client = clientFor(dbPath);
  const directAll = cliJson(['list-items', '--db', dbPath]);
  const directActive = cliJson(['list-items', '--status', 'Active', '--db', dbPath]);
  const directChallenged = cliJson(['list-items', '--status', 'Challenged', '--db', dbPath]);
  const directClosed = cliJson(['list-items', '--status', 'Closed', '--db', dbPath]);
  const directState = cliJson(['current-state', '--db', dbPath]);

  const [all, active, challenged, closed, state] = await Promise.all([
    client.runCommand('list-items', ['--limit', '1']),
    client.runCommand('list-items', ['--status', 'Active', '--limit', '1']),
    client.runCommand('list-items', ['--status', 'Challenged', '--limit', '1']),
    client.runCommand('list-items', ['--status', 'Closed', '--limit', '1']),
    client.runCommand('current-state', []),
  ]);
  for (const result of [all, active, challenged, closed, state]) {
    assert.equal(result.ok, true, JSON.stringify(result.error ?? {}));
  }
  assert.equal(all.data.total, directAll.total, 'the total must be the unfiltered list-items total');
  assert.equal(active.data.total, directActive.total);
  assert.equal(challenged.data.total, directChallenged.total);
  assert.equal(closed.data.total, directClosed.total);
  // The Active + Challenged counts must equal current-state's count
  // (the contract test the step file names).
  assert.equal(
    active.data.total + challenged.data.total,
    directState.count,
    'Active + Challenged (list-items) must equal current-state count',
  );
  assert.equal(state.data.count, directState.count);
  assert.equal(
    state.data.items.filter((it) => it.challenged).length,
    directState.items.filter((it) => it.challenged).length,
  );
}, 60000);

test('the totals also match the ledger-seeded KB of the undo suite', async () => {
  const dbPath = seed('seed_closed');
  const client = clientFor(dbPath);
  const direct = cliJson(['list-items', '--db', dbPath]);
  const result = await client.runCommand('list-items', ['--limit', '1']);
  assert.equal(result.ok, true, JSON.stringify(result.error ?? {}));
  assert.equal(result.data.total, direct.total);
}, 60000);

test('show-item carries the provenance the detail view renders', async () => {
  const dbPath = seed('seed_pair');
  const client = clientFor(dbPath);
  const direct = cliJson(['show-item', '--item', '1', '--db', dbPath]);
  const result = await client.runCommand('show-item', ['--item', '1']);
  assert.equal(result.ok, true, JSON.stringify(result.error ?? {}));
  assert.deepEqual(Object.keys(result.data).sort(), ['item', 'links_in', 'links_out', 'source']);
  assert.equal(result.data.source, direct.source, 'the source text must be verbatim, byte for byte');
  const allLinks = [...result.data.links_out, ...result.data.links_in];
  assert.equal(allLinks.length, direct.links_out.length + direct.links_in.length, 'ALL links, both directions');
  for (const link of allLinks) {
    for (const field of ['id', 'type', 'status', 'other_item_id', 'other_item_type', 'other_item_statement', 'other_item_status', 'reversed_at']) {
      assert.ok(field in link, `the app renders the other item's heat mark, so it needs ${field}`);
    }
  }
  // Unknown ids stay refused the same way the terminal refuses them.
  const missing = await client.runCommand('show-item', ['--item', '999']);
  assert.equal(missing.ok, false);
  assert.equal(missing.error.code, 'QUERY-001');
}, 60000);

'use strict';

/**
 * The step-04 contract tests (app step file §2): on a REAL temp
 * knowledge base seeded by the Python test helpers, the app's reads
 * must equal what the matching `ember` command prints — spec "counts
 * match exactly" and "one test seam".
 *
 * - Home's counts used to come from four FILTERED `list-items` calls;
 *   since Batch 5 chunk 11 (N11) they come from ONE `--counts` call,
 *   and that document's summary must equal the per-status CLI totals.
 * - Any status count still must equal the matching filtered call's
 *   total, and the Active+Challenged counts must equal `ember
 *   current-state`'s count.
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
const { listItemsArgs } = require('../main/command-args');
const { PYTHON, REPO_ROOT, APP_ROOT, errorPatternFixture } = require('./util');

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');

// Every folder seed() created for the running test. Each test removes
// them all in its `finally` (I4: mkdtemp folders are never orphaned).
const seededDirs = [];

function seed(kind) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `ember-contract-${kind}-`));
  seededDirs.push(dir);
  const dbPath = path.join(dir, 'kb.db');
  execFileSync(PYTHON, ['-c', `from tests.bridge import harness; harness.${kind}(${JSON.stringify(dbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  return dbPath;
}

/** Remove every seeded folder so far (seededDirs is drained). */
function removeSeededDirs() {
  for (const dir of seededDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
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
  try {
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
  } finally {
    removeSeededDirs();
  }
}, 60000);

test('one list-items --counts call answers the Home counts (chunk 11, N11)', async () => {
  assert.ok(fs.existsSync(EMBER), 'the venv ember is missing — the contract test cannot run');
  try {
    const dbPath = seed('seed_closed');
    const client = clientFor(dbPath);

    // The counts-builder's counts-ONLY form: one command, no filters,
    // no paging flags beside it (the app adapts to the bridge).
    const countsArgs = listItemsArgs({ counts: true });
    assert.deepEqual(countsArgs, ['--counts']);

    // The counts document equals the per-status CLI totals, and its
    // total equals the sum (the same equality the old four-call shape
    // carried, now verified in one document).
    const directCounts = cliJson(['list-items', '--counts', '--db', dbPath]).summary;
    const perStatus = {
      active: cliJson(['list-items', '--status', 'Active', '--db', dbPath]).total,
      challenged: cliJson(['list-items', '--status', 'Challenged', '--db', dbPath]).total,
      closed: cliJson(['list-items', '--status', 'Closed', '--db', dbPath]).total,
    };
    assert.deepEqual(directCounts, {
      active: perStatus.active,
      challenged: perStatus.challenged,
      closed: perStatus.closed,
      total: perStatus.active + perStatus.challenged + perStatus.closed,
    });

    // Through the app's seam: the ONE call the screen now makes must
    // bring the same document back.
    const result = await client.runCommand('list-items', countsArgs);
    assert.equal(result.ok, true, JSON.stringify(result.error ?? {}));
    assert.deepEqual(result.data.summary, directCounts);

    // The one-call pin: Home's counts block makes its ONE call and
    // renders every number through esc() (4.9 #25's escaping half —
    // the counts come from the engine document into HTML). The screen
    // source is pinned here so the old four-call shape cannot drift
    // back. loadAttention keeps its own listItems call (the challenged
    // probe), so the whole screen may hold exactly two call sites.
    const homeSource = fs.readFileSync(path.join(APP_ROOT, 'renderer', 'screens', 'home.mjs'), 'utf8');
    const callSites = [...homeSource.matchAll(/ctx\.api\.listItems\(/g)].length;
    assert.equal(callSites, 2, `Home must keep exactly two list-items call sites (attention + the one counts call), saw ${callSites}`);
    const start = homeSource.indexOf('async function loadCounts');
    const end = homeSource.indexOf('async function loadLedger');
    assert.ok(start !== -1 && end !== -1 && start < end, 'loadCounts moved — re-pin the one-call pin');
    const countsBlock = homeSource.slice(start, end);
    assert.equal(
      [...countsBlock.matchAll(/ctx\.api\.listItems\(/g)].length,
      1,
      'loadCounts must make its counts call ALONE (N11): one call on the wire, not four',
    );
    assert.match(countsBlock, /counts:\s*true/, 'the counts call must use the --counts form');
    for (const figure of ['active', 'challenged', 'closed', 'total']) {
      assert.match(
        countsBlock,
        new RegExp(`data-testid="count-${figure}">\\$\\{esc\\(`),
        `the ${figure} figure must be rendered through esc() (4.9 #25)`,
      );
    }
  } finally {
    removeSeededDirs();
  }
}, 60000);

test('the totals also match the ledger-seeded KB of the undo suite', async () => {
  try {
    const dbPath = seed('seed_closed');
    const client = clientFor(dbPath);
    const direct = cliJson(['list-items', '--db', dbPath]);
    const result = await client.runCommand('list-items', ['--limit', '1']);
    assert.equal(result.ok, true, JSON.stringify(result.error ?? {}));
    assert.equal(result.data.total, direct.total);
  } finally {
    removeSeededDirs();
  }
}, 60000);

test('show-item carries the provenance the detail view renders', async () => {
  try {
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
  } finally {
    removeSeededDirs();
  }
}, 60000);

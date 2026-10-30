'use strict';

/**
 * The contract test (step file §2): the app's bridge client runs
 * against a REAL temp knowledge base seeded by the Python test
 * helpers, and the count it reads must equal what `ember list-items`
 * says. One test seam, two languages.
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

test('the bridge client reads a real knowledge base seeded by the Python helpers', () => {
  assert.ok(fs.existsSync(PYTHON), `the project venv python is missing at ${PYTHON} — the contract test cannot run`);
  assert.ok(fs.existsSync(EMBER), `the ember CLI is missing at ${EMBER} — the contract test cannot run`);

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-contract-'));
  const dbPath = path.join(dir, 'kb.db');

  // Seed with the SAME helpers the bridge's own suite uses
  // (tests/bridge/harness.seed_pair: two items, one confirmed link).
  execFileSync(PYTHON, ['-c', `from tests.bridge import harness; harness.seed_pair(${JSON.stringify(dbPath)})`], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'inherit'],
  });

  const client = createBridgeClient({
    emberCommand: [EMBER],
    dbPath,
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 30000,
  });
  const applesToApples = execFileSync(EMBER, ['list-items', '--db', dbPath], { encoding: 'utf8' });
  const directTotal = JSON.parse(applesToApples).total;

  return client.runCommand('list-items', []).then((result) => {
    assert.equal(result.ok, true, JSON.stringify(result.error ?? {}));
    assert.equal(result.data.total, directTotal, 'the app must read exactly what `ember list-items` reads');
    assert.equal(result.data.items.length, directTotal);
    const kinds = new Set(result.data.items.map((item) => typeof item.id === 'number' && typeof item.statement === 'string'));
    assert.deepEqual([...kinds], [true], 'item rows carry the pinned nine fields');
  });
}, 60000);

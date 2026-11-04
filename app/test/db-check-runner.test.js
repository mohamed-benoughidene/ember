'use strict';

/**
 * The db-check runner (app step 09; ticket A38) against a fake `ember`
 * child: exit 0 AND exit 1 both carry the report document (that is the
 * engine's contract for OK vs DRIFT/UNREADABLE, docs/commands.md
 * "Engine E: Utility"); every other failure is a named APP-/house
 * error. The stdout document is validated once, here (D4).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { runDbCheck } = require('../main/db-check-runner');
const { errorPatternFixture } = require('./util');

const OK_DOC = {
  changes: [],
  command: 'db-check',
  dry_run: false,
  summary: {
    detail: null,
    lines: ['version: 13', 'floors: relate 12 ok', 'result: OK'],
    result: 'OK',
  },
};

/** A fake `ember` executable: the script body answers `db-check ... --format json`. */
function fakeEmber(scriptBody) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-dbrunner-'));
  const file = path.join(dir, 'fake-ember-dbrunner.js');
  fs.writeFileSync(file, `'use strict';\n${scriptBody}\n`);
  return { command: ['node', file], cleanup: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

test('exit 0 with a healthy report -> ok, and the report is DATA', async () => {
  const fake = fakeEmber(`process.stdout.write(JSON.stringify(${JSON.stringify(OK_DOC)}));\nprocess.exit(0);`);
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, true);
    assert.deepEqual(result.data, { result: 'OK', detail: null, lines: OK_DOC.summary.lines, exitCode: 0 });
  } finally {
    fake.cleanup();
  }
});

test('exit 1 with a DRIFT report is still a RESULT, not an error (the whole point of this runner)', async () => {
  const drift = {
    ...OK_DOC,
    summary: { detail: null, lines: ['version: 13', 'triggers: missing items_closed_reason_update', 'result: DRIFT'], result: 'DRIFT' },
  };
  const fake = fakeEmber(`process.stdout.write(JSON.stringify(${JSON.stringify(drift)}));\nprocess.exit(1);`);
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, true, 'DRIFT must come back as data for the screen (story 75)');
    assert.equal(result.data.result, 'DRIFT');
    assert.equal(result.data.exitCode, 1);
    assert.ok(result.data.lines.some((l) => l.startsWith('triggers: missing')));
  } finally {
    fake.cleanup();
  }
});

test('exit 1 with UNREADABLE carries the stderr detail alongside the report', async () => {
  const unreadable = { ...OK_DOC, summary: { detail: 'db open fail: not a database', lines: ['result: UNREADABLE'], result: 'UNREADABLE' } };
  const fake = fakeEmber(
    `process.stderr.write('detail: db open fail: not a database\\\\n');\nprocess.stdout.write(JSON.stringify(${JSON.stringify(unreadable)}));\nprocess.exit(1);`,
  );
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, true);
    assert.equal(result.data.result, 'UNREADABLE');
    assert.equal(result.data.detail, 'db open fail: not a database');
  } finally {
    fake.cleanup();
  }
});

test('stdout that is not ONE document -> APP-002 (D4, validated once)', async () => {
  const fake = fakeEmber(`process.stdout.write('hello, not json');\nprocess.exit(0);`);
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-002');
  } finally {
    fake.cleanup();
  }
});

test('a report of the wrong shape -> APP-002 (unknown result, missing lines)', async () => {
  for (const badSummary of [
    { detail: null, lines: [], result: 'MAYBE' },
    { detail: null, result: 'OK' },
    'a string',
  ]) {
    const fake = fakeEmber(
      `process.stdout.write(JSON.stringify({changes: [], command: 'db-check', summary: ${JSON.stringify(badSummary)}}));\nprocess.exit(0);`,
    );
    try {
      const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
      assert.equal(result.ok, false, `${JSON.stringify(badSummary)} must be refused`);
      assert.equal(result.error.code, 'APP-002');
    } finally {
      fake.cleanup();
    }
  }
});

test('a real house error line (exit outside 0/1) parses into its code', async () => {
  const fake = fakeEmber(
    `process.stderr.write('error: QUERY-003 KnowledgeBaseMissing | ember.query.rows | db file missing\\\\n');\nprocess.exit(3);`,
  );
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'QUERY-003');
  } finally {
    fake.cleanup();
  }
});

test('a house line on stderr after line 1 is still parsed', async () => {
  const fake = fakeEmber(
    // REAL newline-terminated stderr lines (like the fake's
    // warning-then-error mode): a warning, then the house line second.
    `process.stderr.write('warning: embedding model changed since build\\n');\nprocess.stderr.write('error: QUERY-003 KnowledgeBaseMissing | ember.query.rows | db file missing\\n');\nprocess.exit(3);`,
  );
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'QUERY-003');
  } finally {
    fake.cleanup();
  }
});

test('a stderr house line split across two reads parses', async () => {
  // Batch 5 chunk 3 (4.4 #1): the pipe delivers the house line in TWO
  // piecewise writes — the first carries NO newline — so a reader that
  // splits each chunk on '\n' sees two broken half-lines and the house
  // code is lost. Whole streamed lines must rejoin it.
  const fake = fakeEmber(
    `process.stderr.write('error: QUERY-003 KnowledgeBaseMissing | ember.que');\nsetTimeout(() => {\n  process.stderr.write('ry.rows | db file missing\\n');\n  process.exit(3);\n}, 25);`,
  );
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'QUERY-003', JSON.stringify(result.error));
    assert.equal(result.error.name, 'KnowledgeBaseMissing');
  } finally {
    fake.cleanup();
  }
});

test('exit 2 without a house line -> APP-002 (usage/abort)', async () => {
  const fake = fakeEmber(`process.exit(2);`);
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-002');
  } finally {
    fake.cleanup();
  }
});

test('a timed-out child retries once, then comes back as APP-008 (a read, I15)', async () => {
  // The script ignores SIGTERM long enough for the SECOND attempt to be
  // observed via a marker file; with a 1000 ms limit each attempt has
  // time to start and write its marker before it is judged, so the
  // marker count is the real number of tries.
  const marker = `${fs.mkdtempSync(path.join(os.tmpdir(), 'ember-dbrun-marker-'))}/calls`;
  const fake = fakeEmber(`
    const fs = require('node:fs');
    fs.appendFileSync(${JSON.stringify(marker)}, '1\\\\n');
    const end = Date.now() + 5000;
    while (Date.now() < end) {} // spin past any SIGTERM-then-settled window
  `);
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 2, timeoutMs: 1000 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-008');
    const calls = (fs.readFileSync(marker, 'utf8').match(/1/g) ?? []).length;
    assert.equal(calls, 2, `a read retries exactly once: saw ${calls} calls`);
  } finally {
    fake.cleanup();
    fs.rmSync(path.dirname(marker), { recursive: true, force: true });
  }
});

test('oversized stdout ends with the bridge-client kind of error (F8)', async () => {
  // 40 x 1 MB chunks = 40 MB > the 32 MB untrusted-output cap.
  // Each 1 MB chunk is written with backpressure (wait for `drain`), so
  // no byte sits in the child's buffer when it ends, and the child ends
  // by closing its output — never by `process.exit(0)` (which would drop
  // pending bytes and let the run finish under the cap). Every byte
  // really reaches the reader, so the 32 MB cap is really hit.
  const fake = fakeEmber(`
    const big = Buffer.alloc(1024 * 1024, 0x78);
    let n = 0;
    function writeChunk() {
      if (n >= 40) { process.stdout.end(); return; }
      n += 1;
      if (process.stdout.write(big)) writeChunk();
      else process.stdout.once('drain', writeChunk);
    }
    writeChunk();
  `);
  try {
    const result = await runDbCheck({ emberCommand: fake.command, errorPattern: errorPatternFixture(), dbPath: '/tmp/x.db', attempts: 1, timeoutMs: 20000 });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-002');
    assert.match(result.error.detail, /more than \d+ bytes/, result.error.detail);
  } finally {
    fake.cleanup();
  }
});

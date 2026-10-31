'use strict';

/**
 * The Clean up contract tests (app step 08 §2, ticket A37; the "one
 * test seam" rule): on a REAL temp knowledge base seeded by the Python
 * helpers, the app's sweep reads and writes must equal what the real
 * `ember maintain` prints and writes — the app calls the same command
 * with the same pinned flags (preview: `--dry-run --format json`;
 * apply: `maintain --confirm json`, the machine mode the step-02
 * bridge client always uses).
 *
 * - The dry-run preview document (rows, counts, and the
 *   `stale_candidates` shortlist) equals the direct CLI document.
 * - The apply session equals the terminal run on a byte-identical copy
 *   of the same seed: same document, same database rows (dump compare,
 *   write timestamps excluded — the clock is not part of the contract).
 * - A sweep with an empty stale shortlist never asks and never needs
 *   the AI key (the engine decides; the app does not).
 *
 * The AI is faked at the same seam the Python bridge tests use: a
 * local OpenAI-shaped server on EMBER_AI_BASE_URL (helpers here, the
 * same helper the cleanup E2E launches). No external network.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync, spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createBridgeClient } = require('../main/bridge-client');
const { startFakeAiServer } = require('./helpers/fake-ai-server');
const { PYTHON, REPO_ROOT, errorPatternFixture } = require('./util');

let maintainDocumentFromMessage = null;
test.before(async () => {
  ({ maintainDocumentFromMessage } = await import('../shared/maintain-words.mjs'));
});

/**
 * Run one child asynchronously with pipe input (the promisified
 * execFile has NO `input` option, so a confirm stdin would hang the
 * engine open forever). Resolves {status, stdout, stderr}.
 */
function runWithInput(program, args, { input = '', env } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, { cwd: REPO_ROOT, env });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    child.on('error', reject);
    child.on('close', (code) => resolve({ status: code, stdout, stderr }));
    child.stdin.write(input, () => child.stdin.end());
  });
}

const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');

/* ---------- the seeds (real temp knowledge bases) ---------- */

// One real sweep change (a confirmed contradicts link on an Active
// Finding) plus one stale, shielded Question (answered long ago; the
// shield means the sweep spares it, and Phase 5 asks the AI about it).
const SEED_MIXED = `
import sys
from pathlib import Path
from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_link_with_confirmation, insert_source

db = sys.argv[1]
Path(db).touch()
conn = open_maintain_database(db)
try:
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type='Decision', statement='We chose SQLite')
    insert_item(conn, source_id=source_id, item_id=2, item_type='Finding', statement='Auth is measured')
    insert_item(conn, source_id=source_id, item_id=3, item_type='Finding', statement='Contradicted claim')
    insert_item(conn, source_id=source_id, item_id=7, item_type='Question', statement='should we cache tokens?', status_origin='manual')
    insert_link_with_confirmation(conn, 2, 3, 'contradicts')
    insert_link_with_confirmation(conn, 2, 7, 'answers', created_at='2026-01-01T00:00:00+00:00')
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (7, NULL, 'status_origin', 'derived', 'manual',"
        " '2026-01-02T00:00:00+00:00', 'user_set_status')"
    )
    conn.commit()
finally:
    conn.close()
`;

function seed(script, name) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `ember-cleanup-${name}-`));
  const dbPath = path.join(dir, 'kb.db');
  execFileSync(PYTHON, ['-c', script, dbPath], {
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

/** A deterministic row dump (write timestamps excluded), for parity. */
const PY_DUMP = `
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
lines = []
for row in conn.execute("SELECT id,type,statement,status,close_reason,status_origin FROM items ORDER BY id"):
    lines.append(("item",) + row)
for row in conn.execute("SELECT id,source_item_id,target_item_id,link_type,status,reversed_at FROM links ORDER BY id"):
    lines.append(("link",) + row)
for row in conn.execute("SELECT item_id,link_id,field_changed,old_value,new_value,trigger_cause FROM change_log ORDER BY id"):
    lines.append(("log",) + row)
print("\\n".join(str(item) for item in lines))
`;

function dump(dbPath) {
  return execFileSync(PYTHON, ['-c', PY_DUMP, dbPath], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  });
}

/**
 * Drive one `maintain --confirm json` session (what the app's IPC
 * layer does), answering each REAL prompt event from `answerFor`.
 * `answerFor(nth, event)` returns the answer text, `null` to stop()
 * (close the input), or `undefined` to send nothing.
 */
function driveSession(client, args, answerFor = () => undefined) {
  return new Promise((resolve) => {
    const session = client.runConfirmSession('maintain', args);
    const events = [];
    let document = null;
    let error = null;
    let prompts = 0;
    session.on('event', (event) => {
      events.push(event);
      if (event.event === 'message' && typeof event.text === 'string') {
        const doc = maintainDocumentFromMessage(event.text);
        if (doc !== null) document = doc;
      }
      if (event.event === 'prompt') {
        const answer = answerFor(prompts, event);
        prompts += 1;
        if (answer === null) {
          session.stop();
          return;
        }
        if (answer !== undefined) session.answer(answer);
      }
    });
    session.on('error', (info) => {
      error = info;
    });
    session.on('exit', ({ exitCode }) => resolve({ events, document, error, exitCode }));
  });
}

function directJson(args, env) {
  // Asynchronous even for plain reads: keeping the event loop free is
  // the rule whenever any of these tests could share a process with a
  // server (the fake AI). Async costs nothing here.
  return runWithInput(EMBER, args, { input: '', env, maxBuffer: 32 * 1024 * 1024 }).then((r) => {
    if (r.status !== 0) throw new Error(`direct run failed: ${r.stderr}`);
    return JSON.parse(r.stdout);
  });
}

function withFakeAi(extra = {}) {
  return { ...process.env, ...extra };
}

/* ---------- the tests ---------- */

test('the preview document equals `maintain --dry-run --format json` on the same KB', async () => {
  assert.ok(fs.existsSync(EMBER), 'the venv ember is missing — the contract test cannot run');
  const dbPath = seed(SEED_MIXED, 'preview');
  const direct = await directJson(['maintain', '--dry-run', '--format', 'json', '--db', dbPath]);

  const run = await driveSession(clientFor(dbPath), ['--dry-run']);
  assert.equal(run.error, null, JSON.stringify(run.error ?? {}));
  assert.equal(run.exitCode, 0);
  assert.deepEqual(run.document, direct, 'the preview rows/counts/shortlist must be the command’s own document');
  assert.equal(direct.dry_run, true);
  assert.equal(direct.changes.length, 1, 'the seed has exactly one sweep change (item 3)');
  assert.equal(direct.summary.stale, 1, 'the seed has exactly one stale shielded question');
  assert.equal(direct.summary.stale_candidates.truncated, false);
  assert.equal(direct.summary.stale_candidates.candidates[0].item_id, 7);
  // The dump is untouched: a dry run writes nothing (B3, read side).
  const after = seed(SEED_MIXED, 'preview2');
  assert.equal(dump(dbPath), dump(after), 'a dry run leaves the database byte-identical');
}, 120000);

test('the apply session equals the terminal run on a byte-identical copy (parity)', async () => {
  const ai = await startFakeAiServer();
  process.env.EMBER_AI_BASE_URL = ai.url;
  process.env.EMBER_AI_API_KEY = 'sk-or-v1-fake-key-for-tests-only-000000';
  try {
    const dbA = seed(SEED_MIXED, 'parity-a');
    const dbB = path.join(path.dirname(dbA), 'parity-b.db');
    fs.copyFileSync(dbA, dbB); // byte-identical start (the harness rule)
    assert.equal(dump(dbA), dump(dbB), 'the copies start identical');

    const client = clientFor(dbA);
    const promptsSeen = [];
    const run = await driveSession(client, [], (nth) => {
      promptsSeen.push(nth);
      // Answer the FIRST prompt (the real one) with the app's choice;
      // the loop's own shape is asserted below.
      return nth === 0 ? 'y' : null;
    });

    // The REAL event stream: one close block per stale question, the
    // prompt, the accepted close's report lines, then the document.
    const closeBlocks = run.events.filter((e) => e.event === 'block' && e.kind === 'close');
    assert.equal(closeBlocks.length, 1);
    assert.equal(closeBlocks[0].fields.item_id, 7);
    assert.equal(closeBlocks[0].fields.reason, 'expired');
    const promptEvents = run.events.filter((e) => e.event === 'prompt');
    assert.equal(promptEvents.length, 1);
    assert.deepEqual(promptEvents[0].choices, ['y', 'n', 'q'], 'the prompt must carry the engine’s own choices');
    assert.deepEqual(promptsSeen, [0]);
    assert.ok(
      run.events.some((e) => e.event === 'message' && /item 7: Active -> Closed/.test(e.text ?? '')),
      'the accepted close’s report line must arrive as a message event',
    );
    assert.equal(run.error, null, JSON.stringify(run.error ?? {}));
    assert.equal(run.document.summary.accepted, 1);
    assert.equal(run.document.summary.challenged, 1, 'the sweep change is in the same document');
    assert.equal(ai.calls.length, 1, 'the session made exactly one AI call for one candidate');
    assert.ok(ai.calls[0].body.includes('should we cache tokens?'), 'the candidate’s own text rides the request');

    // The terminal run on the copy, same flags the app is allowed to
    // pin (`--format json`, human confirm with the same keys). Async —
    // the fake AI server lives in this process and must keep serving.
    const terminal = await runWithInput(
      EMBER,
      ['maintain', '--format', 'json', '--confirm', 'terminal', '--db', dbB],
      { input: 'y\n', env: withFakeAi() },
    );
    assert.equal(terminal.status, 0, `the terminal run must succeed: ${terminal.stderr}`);
    const terminalDoc = maintainDocumentFromMessage(terminal.stdout.trim().split('\n').pop());
    assert.ok(terminalDoc, 'the terminal run must end in the pinned document');
    assert.deepEqual(run.document, terminalDoc, 'the app’s apply document must equal the terminal run’s');
    assert.equal(dump(dbA), dump(dbB), 'the databases must be row-for-row equal after both runs');
    assert.equal(ai.calls.length, 2, 'the terminal run adds exactly one AI call of its own');
    assert.ok(ai.calls[1].body.includes('should we cache tokens?'));
  } finally {
    delete process.env.EMBER_AI_BASE_URL;
    delete process.env.EMBER_AI_API_KEY;
    await ai.close();
  }
}, 120000);

test('a sweep with an empty shortlist never prompts and never needs the key', async () => {
  const dbA = seed(
    `
import sys
from pathlib import Path
from ember.adapters.sqlite import open_maintain_database
from tests.bridge import harness
db = sys.argv[1]
harness.seed_contradicted_active(db)
`,
    'noai-a',
  );
  const dbB = path.join(path.dirname(dbA), 'noai-b.db');
  fs.copyFileSync(dbA, dbB);
  const env = { ...process.env };
  delete env.EMBER_AI_API_KEY;
  delete env.EMBER_AI_BASE_URL;
  delete env.OPENROUTER_API_KEY;

  const run = await driveSession(clientFor(dbA), [], () => undefined);
  assert.equal(run.error, null, JSON.stringify(run.error ?? {}));
  assert.equal(run.exitCode, 0);
  assert.equal(run.events.filter((e) => e.event === 'prompt').length, 0, 'no question, no prompt');
  assert.equal(run.document.summary.stale, 0);
  assert.equal(run.document.summary.challenged, 1);

  const terminal = await runWithInput(
    EMBER,
    ['maintain', '--format', 'json', '--confirm', 'terminal', '--db', dbB],
    { input: '', env },
  );
  assert.equal(terminal.status, 0, `the terminal run must succeed: ${terminal.stderr}`);
  const terminalDoc = maintainDocumentFromMessage(terminal.stdout.trim().split('\n').pop());
  assert.ok(terminalDoc);
  assert.deepEqual(run.document, terminalDoc);
  assert.equal(dump(dbA), dump(dbB), 'the databases are row-for-row equal after both runs');
}, 120000);

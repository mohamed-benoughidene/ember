'use strict';

/**
 * The bridge client tests against the FAKE ember executable (step
 * file §2). The real-ember contract runs in bridge-contract.test.js.
 *
 * The pins that matter most:
 * - every result is the plain {ok, data} / {ok, error} shape;
 * - `--db` is ALWAYS passed;
 * - the house error line becomes the error info (code/name/where/detail);
 * - a hung READ is retried exactly once, a hung WRITE never, and both
 *   end as APP-008 — never APP-001 or APP-002;
 * - garbage output is APP-002; a spawn failure is APP-001;
 * - confirm sessions emit only validated events, and garbage in a
 *   stream raises APP-002 instead of reaching the renderer.
 */

const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createBridgeClient } = require('../main/bridge-client');
const { FAKE_EMBER, errorPatternFixture } = require('./util');

function tempPath(name) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-bridge-'));
  tempDirs.push(dir);
  return path.join(dir, name);
}

// I4: every mkdtemp folder above is tracked and removed once, at the
// very end of the file (node:test's after() runs a single time).
const tempDirs = [];
after(() => {
  for (const dir of tempDirs) fs.rmSync(dir, { recursive: true, force: true });
});

function makeClient(overrides = {}) {
  const { fakeMode = 'session', env = {}, ...rest } = overrides;
  return createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    // 5000 ms: a healthy-but-slow read (the fake's `slow` mode takes
    // 400 ms) must answer, never die as APP-008. The hung-read/hung-
    // write tests set their tight 150 ms limit explicitly.
    timeoutReadMs: 5000,
    timeoutWriteMs: 5000,
    sessionIdleMs: 5000,
    ...rest,
    spawnFn:
      rest.spawnFn ??
      ((exe, args, opts) => spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: fakeMode, ...env } })),
  });
}

// --- one-shot commands ---------------------------------------------------------

test('a read returns the pinned shape: {ok:true, data:{total, items}}', async () => {
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 5000,
  });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, true);
  assert.equal(result.data.total, 2);
  assert.equal(result.data.items.length, 2);
  assert.deepEqual(
    Object.keys(result.data).sort(),
    ['items', 'total'],
  );
});

test('a slow-but-answering read succeeds with the default limit', async () => {
  // A healthy engine that merely takes 400 ms must NOT be judged by
  // the dead-session limit: makeClient's defaults (5000 ms after the
  // Batch 0 fix) have to let the normal document through, never APP-008.
  const client = makeClient({ fakeMode: 'slow' });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, true, `the slow read must answer, never timeout: ${JSON.stringify(result)}`);
  assert.equal(result.data.total, 2, JSON.stringify(result));
});

test('the knowledge base path rides along as --db on EVERY call', async () => {
  const dbPath = tempPath('kb.db');
  const spawnLog = tempPath('spawns.log');
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath,
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 5000,
    spawnFn: (exe, args, opts) => {
      fs.appendFileSync(spawnLog, `${JSON.stringify(args)}\n`);
      return spawn(exe, args, opts);
    },
  });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, true);
  const lines = fs.readFileSync(spawnLog, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  for (const args of lines) {
    const dbIndex = args.indexOf('--db');
    assert.ok(dbIndex !== -1, `no --db in ${JSON.stringify(args)}`);
    assert.equal(args[dbIndex + 1], dbPath);
  }
});

test('a house error line becomes the error info with code, name, where, detail', async () => {
  const client = makeClient({ fakeMode: 'error' });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'QUERY-003');
  assert.equal(result.error.name, 'DbOpenFailed');
  assert.equal(result.error.where, 'fake.ember');
  assert.ok(result.error.detail.includes('db file missing'), result.error.detail);
  assert.ok(result.error.detail.includes('continuation line one'), result.error.detail);
  assert.ok(!Object.values(result.error).some((v) => v === undefined));
});

test('a non-house error line becomes APP-002 (never guessed)', async () => {
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 5000,
    spawnFn: (exe, args, opts) => spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'unparsable-error' } }),
  });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.deepEqual({ code: result.error.code, name: result.error.name }, {
    code: 'APP-002',
    name: 'BridgeOutputInvalid',
  });
});

test('a warning line before the house error line does not hide the real error (F2)', async () => {
  const client = makeClient({ fakeMode: 'warning-then-error' });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'RELATE-036');
  assert.equal(result.error.name, 'AiResponseWriteFailed');
  assert.equal(result.error.where, 'fake.ember');
  assert.ok(result.error.detail.startsWith('raw answer save failed'), result.error.detail);
  // The warning before the error is not the error: it must not be in
  // the detail, and the code must never degrade to APP-002.
  assert.ok(!result.error.detail.includes('warning:'), result.error.detail);
  assert.notEqual(result.error.code, 'APP-002');
});

test('a traceback with no house line keeps the LAST non-empty stderr line in the APP-002 details', async () => {
  const client = makeClient({ fakeMode: 'traceback' });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-002');
  // The real cause is the LAST line, not the leading `Traceback` line.
  assert.ok(result.error.detail.includes('sqlite3.OperationalError'), result.error.detail);
  assert.ok(!result.error.detail.includes('Traceback'), result.error.detail);
});

// --- Batch 5 chunk 3 (4.4 #1, #11): whole streamed lines -----------------------

test('a house error line split across two writes parses to the engine\'s code', async () => {
  // The fake writes the house line in TWO piecewise pipe writes (the
  // first carries no newline), the way a real engine's stderr can
  // arrive. A reader that splits each chunk on '\n' sees two broken
  // half-lines and loses the house code.
  const client = makeClient({ fakeMode: 'error', env: { FAKE_STDERR_SPLIT: '1' } });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'QUERY-003', JSON.stringify(result.error));
  assert.equal(result.error.name, 'DbOpenFailed');
  assert.equal(result.error.where, 'fake.ember');
});

test('a stderr line split mid-multi-byte character is intact', async () => {
  // The two writes cut INSIDE the ellipsis (U+2026, three UTF-8
  // bytes): decoding each chunk on its own replaces the broken half
  // characters with U+FFFD, so the detail must NOT contain one.
  const client = makeClient({ fakeMode: 'error', env: { FAKE_STDERR_SPLIT: '1' } });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.ok(result.error.detail.includes('db file… missing'), result.error.detail);
  assert.ok(!result.error.detail.includes('\uFFFD'), result.error.detail);
});

test('the final unterminated stdout line is read', async () => {
  // Story 30: the session's LAST event line arrives WITHOUT its
  // newline — the reader must flush that partial line when the child
  // closes, not drop the summary event.
  const client = makeClient({ env: { FAKE_STDOUT_SPLIT: '1' } });
  const { events, errors, exitPromise } = openSession(client, 'capture');
  await exitPromise;
  assert.deepEqual(events.map((e) => e.event), ['message', 'block', 'prompt', 'summary']);
  assert.deepEqual(errors, [], JSON.stringify(errors));
  assert.equal(events[3].aborted, false);
  // The split line was cut inside its ellipsis: the text survives.
  assert.ok(events[0].text.includes('…reading the file'), JSON.stringify(events[0]));
});

test('stdout that is not one JSON document is APP-002', async () => {
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 5000,
    spawnFn: (exe, args, opts) => spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'garbage' } }),
  });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-002');
});

test('a missing binary is APP-001 BridgeSpawnFailed, never a crash', async () => {
  const client = createBridgeClient({
    emberCommand: ['definitely-not-a-binary-anywhere-xyz'],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
  });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-001');
  assert.equal(result.error.name, 'BridgeSpawnFailed');
});

test('a hung READ times out, is retried EXACTLY once, and ends APP-008', async () => {
  const spawnLog = tempPath('spawns.log');
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 150,
    spawnFn: (exe, args, opts) => {
      fs.appendFileSync(spawnLog, 'spawn\n');
      return spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'hang' } });
    },
  });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-008', JSON.stringify(result.error));
  assert.equal(result.error.name, 'BridgeTimeout');
  assert.equal(fs.readFileSync(spawnLog, 'utf8').match(/spawn/g).length, 2, 'exactly one retry');
}, 10000);

test('a hung WRITE is NEVER retried and ends APP-008 (a repeated undo could run twice)', async () => {
  const spawnLog = tempPath('spawns.log');
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutWriteMs: 150,
    spawnFn: (exe, args, opts) => {
      fs.appendFileSync(spawnLog, 'spawn\n');
      return spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'hang' } });
    },
  });
  const result = await client.runCommand('undo', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-008');
  assert.ok(result.error.detail.includes('NOT retried'), result.error.detail);
  assert.equal(fs.readFileSync(spawnLog, 'utf8').match(/spawn/g).length, 1, 'no retry on writes');
}, 10000);

test('a hung capture-source is treated as a WRITE: never retried (F7)', async () => {
  const spawnLog = tempPath('spawns.log');
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutWriteMs: 150,
    spawnFn: (exe, args, opts) => {
      fs.appendFileSync(spawnLog, 'spawn\n');
      return spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'hang' } });
    },
  });
  const result = await client.runCommand('capture-source', []);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-008');
  assert.ok(result.error.detail.includes('NOT retried'), result.error.detail);
  assert.equal(fs.readFileSync(spawnLog, 'utf8').match(/spawn/g).length, 1, 'capture-source stores text: no retry');
}, 10000);

test('capture and relate may NOT go through runCommand (they are sessions)', async () => {
  const client = makeClient({ fakeMode: 'list' });
  await assert.rejects(() => client.runCommand('capture', []), TypeError);
  await assert.rejects(() => client.runCommand('relate', []), TypeError);
});

test('an unknown one-shot command is a caller bug, named loudly', async () => {
  const client = makeClient({ fakeMode: 'list' });
  await assert.rejects(() => client.runCommand('frobnicate', []), /unknown one-shot command/);
});

// --- confirm sessions ---------------------------------------------------------

/** Open one session against the fake and collect channels. */
function openSession(client, command, args = []) {
  const events = [];
  const errors = [];
  let session;
  const exitPromise = new Promise((resolve) => {
    session = client
      .runConfirmSession(command, args)
      .on('event', (e) => events.push(e))
      .on('error', (e) => errors.push(e))
      .on('exit', (e) => resolve(e));
  });
  return { session, events, errors, exitPromise };
}

test('a confirm session emits only the pinned event kinds, in order', async () => {
  const client = makeClient();
  const { session, events, errors, exitPromise } = openSession(client, 'capture');
  await testHelpers.waitFor(() => events.some((e) => e.event === 'summary'));
  session.stop(); // this test only pins the stream shape; a quiet quit ends it
  const exit = await exitPromise;
  assert.deepEqual(errors, []);
  assert.deepEqual(events.map((e) => e.event), ['message', 'block', 'prompt', 'summary']);
  assert.equal(events[1].kind, 'item');
  assert.deepEqual(events[2].choices, ['y', 'n', 'q']);
  assert.equal(exit.exitCode, 2, 'the fake reads the closed stdin as a user quit');
}, 10000);

test('answer(text) reaches the child as exactly one {"answer": "<text>"} line', async () => {
  const client = makeClient();
  const { session, events, exitPromise } = openSession(client, 'capture');
  await testHelpers.waitFor(() => events.some((e) => e.event === 'prompt'));
  session.answer('y');
  const exit = await exitPromise;
  assert.equal(exit.exitCode, 0);
  // The fake echoes the shape it received, so the test pins the wire
  // format without reading the child's stdin directly.
  const report = events.find((e) => String(e.text ?? '').startsWith('answer-shape-ok'));
  assert.ok(report, 'the child never received a well-formed answer line');
  assert.equal(report.text, 'answer-shape-ok: true, answer-was: y');
}, 10000);

test('answer(non-string) is refused on the error channel and never written', async () => {
  const client = makeClient();
  const { session, events, errors, exitPromise } = openSession(client, 'capture');
  await testHelpers.waitFor(() => events.some((e) => e.event === 'prompt'), 3000);
  session.answer(42);
  session.answer(null);
  await testHelpers.waitFor(() => errors.length === 2, 3000);
  assert.ok(errors.every((e) => e.code === 'APP-002' && e.detail.includes('not a string')), JSON.stringify(errors));
  session.stop(); // end the session; the fake reads a closed stdin as a quit
  await exitPromise;
}, 10000);

test('stop() closes stdin and the session ends without hanging', async () => {
  const client = makeClient({ sessionIdleMs: 20000 });
  const { session, exitPromise } = openSession(client, 'relate');
  await testHelpers.waitFor(() => true, 200); // a beat so the child starts
  session.stop();
  const exit = await exitPromise;
  assert.equal(exit.exitCode, 2, 'the fake reads the closed stdin as a quiet quit');
}, 15000);

test('an idle confirm session ends as APP-008 (I15: a limit on every call)', async () => {
  const client = makeClient({
    sessionIdleMs: 250,
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'session', FAKE_SESSION_IDLE: '1' } }),
  });
  const { errors, exitPromise } = openSession(client, 'maintain');
  await exitPromise;
  assert.ok(errors.some((e) => e.code === 'APP-008' && e.name === 'BridgeTimeout'), JSON.stringify(errors));
}, 10000);

// --- F4: the user may take longer than the output limit to answer -------

test('a prompt the user has not answered outlives the normal output limit (F4)', async () => {
  // The session ends in a prompt; the child then stays silent. The
  // normal output limit (250 ms) must NOT kill it while the user
  // thinks; the long prompt-wait limit (15 s) is what bounds it.
  const client = makeClient({
    sessionIdleMs: 250,
    sessionPromptWaitMs: 15_000,
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, {
        ...opts,
        env: {
          ...opts.env,
          FAKE_MODE: 'session',
          FAKE_SESSION_SCRIPT: JSON.stringify([
            { event: 'message', text: 'here is a question' },
            { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [q]uit', choices: ['y', 'n', 'q'] },
          ]),
        },
      }),
  });
  const { session, exitPromise } = openSession(client, 'maintain');
  let exited = false;
  exitPromise.then(() => {
    exited = true;
  });
  await new Promise((r) => setTimeout(r, 1000)); // > 4x the output limit
  assert.equal(exited, false, 'the unanswered prompt must still be waiting');
  session.stop();
  const exit = await exitPromise;
  assert.equal(exit.exitCode, 2);
}, 15000);

test('after the answer the normal silence limit ends a hung engine again (F4)', async () => {
  // The engine receives the answer and then hangs with no output: the
  // POST-answer limit is the normal output limit, so APP-008 must
  // arrive quickly even though a prompt was seen.
  const client = makeClient({
    sessionIdleMs: 250,
    sessionPromptWaitMs: 60_000,
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'session', FAKE_SESSION_SILENT_AFTER_ANSWER: '1' } }),
  });
  const { session, events, errors, exitPromise } = openSession(client, 'maintain');
  // Answer only once the prompt really arrived (the screen answers in
  // response to a prompt event; this removes the queued-event race).
  await testHelpers.waitFor(() => events.some((e) => e.event === 'prompt'), 3000);
  session.answer('y');
  await exitPromise;
  assert.ok(errors.some((e) => e.code === 'APP-008' && /produced no output/.test(e.detail)), JSON.stringify(errors));
}, 15000);

test('a forgotten prompt still ends under the long prompt-wait limit (F4)', async () => {
  const client = makeClient({
    sessionIdleMs: 10_000,
    sessionPromptWaitMs: 400,
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, {
        ...opts,
        env: {
          ...opts.env,
          FAKE_MODE: 'session',
          FAKE_SESSION_SCRIPT: JSON.stringify([
            { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [q]uit', choices: ['y', 'n', 'q'] },
          ]),
        },
      }),
  });
  const { errors, exitPromise } = openSession(client, 'maintain');
  await exitPromise;
  assert.ok(errors.some((e) => e.code === 'APP-008' && /waiting for an answer for 400 ms/.test(e.detail)), JSON.stringify(errors));
}, 15000);

test('garbage in a confirm stream raises APP-002 and never reaches the renderer', async () => {
  const client = createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    sessionIdleMs: 5000,
    spawnFn: (exe, args, opts) => spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'garbage' } }),
  });
  const { events, errors, exitPromise } = openSession(client, 'maintain');
  await exitPromise;
  assert.deepEqual(events, [], 'no garbage event may pass');
  assert.ok(errors.some((e) => e.code === 'APP-002'), JSON.stringify(errors));
});

// --- Batch 5 chunk 5: sessions cap their bytes; stdin survives (4.4 #2, #5; 4.2 #14) ---

test('confirm-session stdout beyond the 32 MB cap settles with a named error', async () => {
  // 4.2 #14, story 33: a confirm session's stdout is untrusted output
  // too — the same 32 MB cap the one-shot path has must end the
  // session with a NAMED cap error (APP-002, the same wording), not
  // let a chatty engine stream forever. The fake floods ~40 MB (40 x
  // 1 MB, drain-aware, so every byte really reaches the reader).
  const client = makeClient({
    sessionIdleMs: 20_000, // the CAP must end it, never the idle limit
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'session', FAKE_FLOOD: '1' } }),
  });
  const { errors, exitPromise } = openSession(client, 'maintain');
  await exitPromise;
  assert.ok(
    errors.some((e) => e.code === 'APP-002' && /more than \d+ bytes/.test(e.detail)),
    `expected the named output-cap error, got: ${JSON.stringify(errors)}`,
  );
}, 30_000);

test('writing an answer to a session whose stdin closed is an error event, not a crash', async () => {
  // 4.4 #2: an answer written after the engine stopped reading its
  // stdin raises EPIPE as an 'error' event on the parent's stdin
  // stream — without a handler that unhandled error would take down
  // the whole app process. The session must surface it as an error
  // event and end, quietly.
  const client = makeClient({
    sessionIdleMs: 20_000,
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'session', FAKE_SESSION_CLOSE_STDIN: '1' } }),
  });
  const { session, events, errors, exitPromise } = openSession(client, 'maintain');
  await testHelpers.waitFor(() => events.some((e) => e.event === 'prompt'), 5000);
  session.answer('y'); // the engine no longer reads its stdin -> EPIPE
  const exit = await exitPromise;
  assert.ok(
    errors.some((e) => e.code === 'APP-002' && /stdin/.test(e.detail)),
    `expected the named broken-stdin error, got: ${JSON.stringify(errors)}`,
  );
}, 20_000);

test('one-shot output beyond the cap returns the cap error', async () => {
  // 4.2 #14: the MAX_OUTPUT_BYTES branch in the ONE-SHOT path (kill at
  // > 32 MB, then the interpret() step returns the cap error) had no
  // test. The same flood, run through runCommand, must come back as
  // APP-002 naming the byte count.
  const client = makeClient({ fakeMode: 'list', env: { FAKE_FLOOD: '1' }, timeoutReadMs: 30_000 });
  const result = await client.runCommand('list-items', []);
  assert.equal(result.ok, false, JSON.stringify(result));
  assert.equal(result.error.code, 'APP-002', JSON.stringify(result.error));
  assert.match(result.error.detail, /more than \d+ bytes/, result.error.detail);
}, 60_000);

test('a chatty child that never completes a line still times out on idle (4.4 #5)', async () => {
  // 4.4 #5: raw stdout chunks must NOT reset the idle timer — only
  // COMPLETE lines do (the line reader feeds bumpIdle). This child
  // writes a small fragment every 50 ms and never a '\n': the session
  // must still end with the named idle error.
  const client = makeClient({
    sessionIdleMs: 300,
    spawnFn: (exe, args, opts) =>
      spawn(exe, args, { ...opts, env: { ...opts.env, FAKE_MODE: 'session', FAKE_SESSION_NO_FULL_LINE: '1' } }),
  });
  const { errors, exitPromise } = openSession(client, 'maintain');
  await exitPromise;
  assert.ok(
    errors.some((e) => e.code === 'APP-008' && /produced no output/.test(e.detail)),
    `expected the idle timeout despite constant raw output, got: ${JSON.stringify(errors)}`,
  );
}, 10_000);

// --- Batch 5 chunk 6: timeouts are hard bounds (4.4 #6; stories 20, 21) ---

/** True while the fake's logged grandchild still answers at that pid. */
function grandchildAlive(pidFile) {
  let pid = NaN;
  try {
    pid = Number(fs.readFileSync(pidFile, 'utf8').trim());
  } catch {
    return true; // the fake has not logged it yet — assume still alive
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false; // ESRCH: nothing is left at that pid
  }
}

test('with a short timeout, a session whose grandchild holds the pipes settles within a short bound after the kill, not when the grandchild dies', async () => {
  // 4.4 #6, story 21. The engine emits its events, asks its question,
  // leaves a GRANDCHILD holding its stdout/stderr, and exits. The
  // grandchild never exits on its own (a bare setInterval), so the
  // child's pipes stay open forever: a settle that waits for stdio to
  // close waits for the grandchild's death and hangs the call. The
  // settle must be the process exit plus a short hard bound for pipe
  // close, and the client's kill must reach the whole process group so
  // the stuck helper cannot outlive the session. The fake logs the
  // grandchild's pid so this test can pin the helper really ended.
  const grandchildLog = tempPath('grandchild.pid');
  const client = makeClient({
    fakeMode: 'session',
    // No builtin limit may settle this on its own: the settle must be
    // the engine's own exit plus a short bound, never a timer.
    sessionIdleMs: 60_000,
    env: {
      FAKE_SESSION_SCRIPT: JSON.stringify([
        { event: 'message', text: 'working' },
        { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [q]uit', choices: ['y', 'n', 'q'] },
      ]),
      FAKE_GRANDCHILD: '1',
      FAKE_GRANDCHILD_LOG: grandchildLog,
    },
  });
  const start = Date.now();
  const { session, events, exitPromise } = openSession(client, 'capture');
  try {
    const settle = await Promise.race([
      exitPromise,
      new Promise((resolve) => setTimeout(() => resolve('bound'), 8000)),
    ]);
    if (settle === 'bound') {
      assert.fail(
        `the session did not settle within ${Date.now() - start} ms: the engine exited at once, so the settle was left waiting for the pipes the grandchild holds`,
      );
    }
    const elapsed = Date.now() - start;
    assert.ok(elapsed < 8000, `settled after ${elapsed} ms — too close to the grandchild's lifetime`);
    assert.deepEqual(events.map((e) => e.event), ['message', 'prompt']);
    assert.equal(settle.exitCode, 0, JSON.stringify(settle));
    // The stuck helper must not outlive the session: the app's kill
    // reaches the whole process group, grandchild included.
    session.stop();
    await testHelpers.waitFor(() => !grandchildAlive(grandchildLog), 8000);
  } finally {
    // Hygiene on ANY path (a failing settle must not leak a node
    // process): end the session, then kill the grandchild directly.
    session.stop();
    try {
      const pid = Number(fs.readFileSync(grandchildLog, 'utf8').trim());
      process.kill(pid, 'SIGKILL');
    } catch {
      /* already gone or never started */
    }
  }
}, 20_000);

test('an engine that exits early settles the session, it does not hang', async () => {
  // 4.4 #6 / story 20: an engine that dies right after spawn with NO
  // output must settle the session on its process exit — the call may
  // never hang waiting for a summary that will not come.
  const client = makeClient({ fakeMode: 'session', env: { FAKE_EXIT_EARLY: '1' } });
  const start = Date.now();
  const { exitPromise } = openSession(client, 'capture');
  const settle = await Promise.race([
    exitPromise,
    new Promise((resolve) => setTimeout(() => resolve('bound'), 8000)),
  ]);
  assert.notEqual(settle, 'bound', `the session did not settle within ${Date.now() - start} ms`);
  const elapsed = Date.now() - start;
  assert.ok(elapsed < 5000, `the engine died at once but the session settled only after ${elapsed} ms`);
  assert.equal(settle.exitCode, 0);
}, 20_000);

// --- tiny poll helper (sessions are event-driven) ------------------------------

const testHelpers = {
  async waitFor(predicate, timeoutMs = 5000) {
    const start = Date.now();
    while (!predicate()) {
      if (Date.now() - start > timeoutMs) throw new Error('waitFor: condition never became true');
      await new Promise((r) => setTimeout(r, 25));
    }
  },
};

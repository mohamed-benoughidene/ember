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

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createBridgeClient } = require('../main/bridge-client');
const { FAKE_EMBER, errorPatternFixture } = require('./util');

function tempPath(name) {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'ember-bridge-')), name);
}

function makeClient(overrides = {}) {
  const { fakeMode = 'session', env = {}, ...rest } = overrides;
  return createBridgeClient({
    emberCommand: ['node', FAKE_EMBER],
    dbPath: tempPath('kb.db'),
    errorPattern: errorPatternFixture(),
    timeoutReadMs: 150,
    timeoutWriteMs: 150,
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

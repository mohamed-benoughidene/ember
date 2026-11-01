'use strict';

/**
 * Batch 1 chunk 3 (decision N1): the runtime gate is its own script,
 * `scripts/gate-ember-runtime.sh` — the same no-key capture + db-check
 * proof the build script runs today (build-ember-runtime.sh:174-202),
 * with its bugs fixed:
 * - the capture must end 1 with EXACTLY ONE stderr line starting
 *   `error: CAPTURE-008` (the old any-`error:`-prefix acceptance let a
 *   second line or another code through; a Python traceback was only
 *   caught by luck);
 * - the FULL error is printed and the gate log folder SURVIVES a
 *   failure (the build's trap deleted its gate files at :74-75 always);
 * - the temp files are cleaned only on success.
 *
 * The stubs follow the fake-ember seam (test seam 4): each case builds
 * a stub runtime folder with a stub `ember` shell script, then runs
 * `bash gate-ember-runtime.sh <stub-dir>` with EVERY AI key variable
 * removed — exactly as the plan types it — and asserts exit codes and
 * log survival, never prose beyond the code.
 */

const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');
const GATE = path.join(APP_ROOT, 'scripts', 'gate-ember-runtime.sh');

// The no-key env, exactly as the plan types it: both key variables gone.
const NO_KEY_ENV = { ...process.env };
delete NO_KEY_ENV.EMBER_AI_API_KEY;
delete NO_KEY_ENV.OPENROUTER_API_KEY;

// I4: the one temp root is tracked and removed once, at the very end.
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-runtime-gate-'));
after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));

const OK_CAPTURE = 'error: CAPTURE-008 set-up | fake.ember.capture | ai api key missing | key=';

// The stub `ember`: on `capture ... --file ... --db ...` print nothing
// on stdout, write the scripted line(s) on stderr, exit 1 (the healthy
// no-key shape); on `db-check --db ... --format json` print the real
// JSON document shape with `version: 13` and `result: OK`, exit 0.
function stubEmberScript(captureStderr) {
  return [
    '#!/bin/sh',
    '# Stub `ember` for the gate tests (test seam 4). The scripted',
    '# capture stderr comes from $STUB_CAPTURE_STDERR (may be multiline).',
    'case "$1" in',
    '  capture)',
    '    db=""',
    '    prev=""',
    '    for a in "$@"; do',
    '      if [ "$prev" = "--db" ]; then db="$a"; fi',
    '      prev="$a"',
    '    done',
    '    # the real capture migrates the file BEFORE the key check',
    '    : > "$db"',
    "    printf '%s\\n' \"$STUB_CAPTURE_STDERR\" >&2",
    '    exit 1',
    '    ;;',
    '  db-check)',
    "    printf '%s\\n' '{\"command\": \"db-check\", \"changes\": [], \"summary\": {\"result\": \"OK\", \"detail\": null, \"lines\": [\"version: 13\", \"triggers: on\", \"result: OK\"]}}'",
    '    exit 0',
    '    ;;',
    '  *)',
    "    printf '%s\\n' 'error: QUERY-003 DbOpenFailed | fake.ember | unknown command' >&2",
    '    exit 1',
    '    ;;',
    'esac',
    '',
  ].join('\n');
}

// One isolated run dir per case: the stub runtime folder lives in
// <runDir>/stub-runtime, so the gate's scratch (which it creates NEXT
// TO the runtime, the build script's disk rule) lands in <runDir>.
function makeCase(name, captureStderr) {
  const runDir = path.join(tempRoot, name);
  const runtime = path.join(runDir, 'stub-runtime');
  fs.mkdirSync(runtime, { recursive: true });
  fs.writeFileSync(path.join(runtime, 'ember'), stubEmberScript(captureStderr), { mode: 0o755 });
  return { runDir, runtime, captureStderr };
}

function runGate(c, runtime) {
  // The stub's capture stderr travels via STUB_CAPTURE_STDERR; the
  // gate itself strips BOTH key variables for the engine child.
  return spawnSync('bash', [GATE, runtime ?? c.runtime], {
    env: { ...NO_KEY_ENV, STUB_CAPTURE_STDERR: c.captureStderr ?? '' },
    encoding: 'utf8',
  });
}

// The gate's log folders (survivors of a failure), in the case run dir.
function logFolders(runDir) {
  return fs
    .readdirSync(runDir)
    .filter((n) => n.startsWith('gate-ember-runtime-'))
    .map((n) => path.join(runDir, n));
}

test('(a) a healthy stub runtime (one CAPTURE-008 line, db-check 13+OK) passes the gate; temp files cleaned', () => {
  const c = makeCase('a-pass', OK_CAPTURE);
  const result = runGate(c);
  assert.equal(result.status, 0, `gate should exit 0, got ${result.status}\nstderr: ${result.stderr}`);
  assert.equal(logFolders(c.runDir).length, 0, 'a PASSED gate must leave no log folder behind (success cleans up)');
});

test('(b) a second stderr line fails the gate; the log folder survives', () => {
  const c = makeCase('b-two-lines', `${OK_CAPTURE}\nnormal second line the old gate swallowed`);
  const result = runGate(c);
  assert.notEqual(result.status, 0, 'a second stderr line must not pass the one-line rule');
  const folders = logFolders(c.runDir);
  assert.ok(folders.length === 1, `the gate log folder must survive the failure, found ${folders.length}`);
  const kept = fs.readFileSync(path.join(folders[0], 'gate-capture.err'), 'utf8');
  assert.ok(kept.includes('normal second line the old gate swallowed'), 'the kept log carries the FULL error');
});

test('(c) a capture line starting error: CAPTURE-999 fails the gate; the log folder survives', () => {
  const c = makeCase('c-wrong-code', 'error: CAPTURE-999 other-failure | fake.ember.capture | not the no-key line');
  const result = runGate(c);
  assert.notEqual(result.status, 0, 'the gate must pin CAPTURE-008, not any error: line');
  const folders = logFolders(c.runDir);
  assert.ok(folders.length === 1, `the gate log folder must survive the failure, found ${folders.length}`);
  const kept = fs.readFileSync(path.join(folders[0], 'gate-capture.err'), 'utf8');
  assert.ok(kept.startsWith('error: CAPTURE-999'), 'the kept log carries the wrong code verbatim');
});

test('(d) a Python traceback fails the gate; the FULL error (not 200 bytes) is printed and kept', () => {
  const filler = '  File "/x/' + 'p'.repeat(240) + '.py", line 1, in <module>\n';
  const traceback = `Traceback (most recent call last):\n${filler}ModuleNotFoundError: No module named 'ember.adapters'\n`;
  const c = makeCase('d-traceback', traceback);
  const result = runGate(c);
  assert.notEqual(result.status, 0, 'a traceback must fail the gate, not ride an error: prefix');
  assert.ok(result.stderr.includes("ModuleNotFoundError: No module named 'ember.adapters'"), 'the gate PRINTS the full error');
  const folders = logFolders(c.runDir);
  assert.ok(folders.length === 1, `the gate log folder must survive the failure, found ${folders.length}`);
  const kept = fs.readFileSync(path.join(folders[0], 'gate-capture.err'), 'utf8');
  assert.ok(
    kept.includes(filler) && kept.includes("ModuleNotFoundError: No module named 'ember.adapters'"),
    'the kept log is the FULL error, not a 200-byte cut',
  );
  assert.ok(kept.length >= traceback.length, `the kept log is ${kept.length} bytes, the error was ${traceback.length}`);
});

test('(e) a gate run on a missing runtime folder exits non-zero with one message line', () => {
  const result = runGate({}, path.join(tempRoot, 'no-such-runtime'));
  assert.notEqual(result.status, 0, 'a missing runtime folder must fail the gate');
  assert.ok(result.stderr.startsWith('error: '), 'the one message is a house error line');
  assert.equal(result.stderr.trim().split('\n').length, 1, 'exactly one message line on stderr');
});

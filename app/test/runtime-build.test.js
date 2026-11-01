'use strict';

/**
 * Chunk 4 (stories 13, 14, 15): the runtime build refuses bad input
 * BEFORE the slow step — before the 20-minute PyInstaller call, before
 * the old runtime is removed, and before any folder is created.
 *
 * How the stub works: EMBER_PACK_VENV points at a fake venv whose
 * bin/python is a `#!/bin/sh` script that exits 0, so the script's
 * check_pkg probes and the torch check pass with no torch and no
 * pyinstaller on the machine. Every run here must end in a seconds-long
 * refusal — a real build would blow the test timeout anyway, because
 * nothing in this suite must ever trigger one (the scratch the real
 * build makes is multi-GB, and /tmp is a small tmpfs).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');
const BUILD = path.join(APP_ROOT, 'scripts', 'build-ember-runtime.sh');
const MODEL_ID = 'BAAI/bge-base-en-v1.5'; // the script's own default

// Keep every stub folder on THIS machine's normal disk rules: the
// script's real scratch is made NEXT TO EMBER_RUNTIME_OUT (never in
// /tmp), and /tmp here is a small tmpfs — only stub flows run, but the
// folders still live under /tmp/opencode/batch1/ per the batch plan.
const SCRATCH_ROOT = '/tmp/opencode/batch1/chunk4';
fs.mkdirSync(SCRATCH_ROOT, { recursive: true });

// The stub pack venv: only bin/python, exiting 0, so the check_pkg
// probes and the torch check pass without the real packages.
const STUB_VENV = path.join(SCRATCH_ROOT, 'stub-pack-venv');
fs.mkdirSync(path.join(STUB_VENV, 'bin'), { recursive: true });
const stubPython = path.join(STUB_VENV, 'bin', 'python');
fs.writeFileSync(stubPython, '#!/bin/sh\nexit 0\n');
fs.chmodSync(stubPython, 0o755);

function runBuild(env, cwd) {
  const childEnv = { ...process.env };
  delete childEnv.EMBER_AI_API_KEY; // no real key may ever reach the script
  delete childEnv.OPENROUTER_API_KEY;
  return spawnSync('bash', [BUILD], {
    cwd,
    encoding: 'utf8',
    timeout: 60_000, // refusal only; a runaway run dies here, not on torch
    env: {
      ...childEnv,
      TMPDIR: SCRATCH_ROOT,
      EMBER_PACK_VENV: STUB_VENV,
      ...env,
    },
  });
}

test('a relative EMBER_RUNTIME_OUT is refused BEFORE any output folder is created', () => {
  const dir = fs.mkdtempSync(path.join(SCRATCH_ROOT, 'rel-out-'));
  try {
    const run = runBuild({ EMBER_RUNTIME_OUT: 'relative-out' }, dir);
    assert.notEqual(run.status, 0, 'a relative output path must be refused');
    assert.match(run.stderr, /EMBER_RUNTIME_OUT/, `the refusal must name the variable; stderr was:\n${run.stderr}`);
    const made = fs.readdirSync(dir);
    assert.deepEqual(made, [], [
      'the refusal must come BEFORE any folder is created;',
      `the work folder holds: ${made.join(', ') || '(empty)'}`,
    ].join(' '));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('a cache without the bge-base weights is refused, naming the model', () => {
  const dir = fs.mkdtempSync(path.join(SCRATCH_ROOT, 'foreign-cache-'));
  try {
    const out = path.join(dir, 'runtime-out');
    const cache = path.join(dir, 'model-cache');
    // A FOREIGN models--* tree — right shape, wrong model, and even a
    // model.safetensors in it; none of it is OUR model's weights.
    const foreign = path.join(cache, 'hub', 'models--foreign-owner--some-other-model');
    fs.mkdirSync(foreign, { recursive: true });
    fs.writeFileSync(path.join(foreign, 'model.safetensors'), 'not the weights ember loads');
    const run = runBuild({ EMBER_RUNTIME_OUT: out, EMBER_MODEL_CACHE: cache }, dir);
    assert.notEqual(run.status, 0, 'a weightless / foreign cache must be refused');
    assert.match(run.stderr, /bge-base-en-v1\.5/, [
      'the refusal must NAME the missing model;',
      `stderr was:\n${run.stderr}`,
    ].join(' '));
    assert.equal(fs.existsSync(out), false, 'the refusal must come before the output folder is touched');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('EMBER_RUNTIME_OUT=/ is refused and / is left untouched', () => {
  // READ-ONLY verification only: the root listing is compared before
  // and after. Nothing is ever written to or removed from / here.
  const before = fs.readdirSync('/').sort();
  const run = runBuild({ EMBER_RUNTIME_OUT: '/' }, APP_ROOT);
  const after = fs.readdirSync('/').sort();
  assert.notEqual(run.status, 0, 'EMBER_RUNTIME_OUT=/ must be refused');
  assert.deepEqual(after, before, 'the root folder must be untouched — no rm -rf on an unchecked path');
});

'use strict';

/**
 * Chunk 4 (stories 13, 14, 15): the runtime build refuses bad input
 * BEFORE the slow step — before the 20-minute PyInstaller call, before
 * the old runtime is removed, and before any folder is created.
 *
 * Chunk 5 (stories 11, 12, 21, 22) adds the stub pyinstaller and the
 * fixture weights: the stub build must pass the gate (marker .gate-ok),
 * carry the weights, and never destroy the old runtime on failure.
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
const SCRATCH_ROOT = '/tmp/opencode/batch1/chunk5';
fs.mkdirSync(SCRATCH_ROOT, { recursive: true });

// The stub pack venv: only bin/python, exiting 0, so the check_pkg
// probes and the torch check pass without the real packages. Chunk 5
// adds a stub bin/pyinstaller next to it (below) that "builds" the
// onedir output in seconds.
const STUB_VENV = path.join(SCRATCH_ROOT, 'stub-pack-venv');
fs.mkdirSync(path.join(STUB_VENV, 'bin'), { recursive: true });
const stubPython = path.join(STUB_VENV, 'bin', 'python');
fs.writeFileSync(stubPython, '#!/bin/sh\nexit 0\n');
fs.chmodSync(stubPython, 0o755);

// The STUB PYINSTALLER (chunk 5): simulates what the real ONEDIR build
// leaves in --distpath — a folder `<name>/` whose launcher file
// `<name>` (renamed to `ember` by the build script) answers --help,
// the gate capture, db-check, and --version — plus an
// `_internal/torch/` folder like `--collect-all torch` would make
// (the build script's closing size report reads it, chunk 7 touches
// that report, not this stub). A few bytes, done in milliseconds.
const stubPyinstaller = path.join(STUB_VENV, 'bin', 'pyinstaller');
fs.writeFileSync(stubPyinstaller, `#!/bin/sh
# stub PyInstaller: no torch, no real build — a seconds-long simulation
set -eu
distpath=.
name=ember-runtime
while [ \$# -gt 0 ]; do
  case "\$1" in
    --distpath) distpath=\$2; shift 2 ;;
    --workpath|--specpath|--clean) shift 2 ;;
    --name) name=\$2; shift 2 ;;
    *) shift ;;
  esac
done
out="\$distpath/\$name"
mkdir -p "\$out/_internal/torch"
echo "stub torch, collected by the stub pyinstaller" > "\$out/_internal/torch/torch.txt"
cat > "\$out/\$name" <<'STUB_EMBER'
#!/bin/sh
# stub ember: the frozen CLI as the gate and the smoke need it
case "\${1:-}" in
  --help)
    echo "usage: ember [options] <command> (stub)"
    exit 0 ;;
  --version)
    echo "ember, version 0.1.0 (stub)"
    exit 0 ;;
  capture)
    # the gate's no-key capture: ONE honest house line on stderr, exit 1.
    # EMBER_STUB_GATE=broken pretends a wrong code (CAPTURE-999) so the
    # gate must refuse the bundle (case e).
    if [ "\${EMBER_STUB_GATE:-}" = broken ]; then
      echo 'error: CAPTURE-999 broken on purpose (stub)' >&2
    else
      echo 'error: CAPTURE-008 no ai api key set - set EMBER_AI_API_KEY and run ember setup again (stub)' >&2
    fi
    exit 1 ;;
  db-check)
    # the capture migrated the file before the key check
    echo '{"db": "stub.kb", "version: 13", "migrated": true, "result: OK"}'
    exit 0 ;;
  *)
    echo "error: CAPTURE-008 stub ember: unknown command \${1:-}" >&2
    exit 1 ;;
esac
STUB_EMBER
chmod +x "\$out/\$name"
echo "stub pyinstaller: made onedir \$out"
`);
fs.chmodSync(stubPyinstaller, 0o755);

// The FIXTURE MODEL CACHE (chunk 5): the real hub layout in miniature —
// blobs/<hash>, snapshots/<sha>/model.safetensors -> ../../blobs/<hash>,
// refs/main holding the sha. A few bytes, snapshotted like the real hub.
function makeModelCache(dir) {
  const tree = path.join(dir, 'hub', 'models--BAAI--bge-base-en-v1.5');
  const blobSha = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
  const snapSha = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678';
  fs.mkdirSync(path.join(tree, 'blobs'), { recursive: true });
  fs.mkdirSync(path.join(tree, 'snapshots', snapSha), { recursive: true });
  fs.mkdirSync(path.join(tree, 'refs'), { recursive: true });
  fs.writeFileSync(path.join(tree, 'blobs', blobSha), 'stub weights: a few bytes, not a real model');
  fs.symlinkSync(`../../blobs/${blobSha}`, path.join(tree, 'snapshots', snapSha, 'model.safetensors'));
  fs.writeFileSync(path.join(tree, 'refs', 'main'), `${snapSha}\n`);
  return dir;
}

// findUnder: the file names under root, walking into real folders only
// (symlinks are matched by name, never followed — the snapshot layout).
function findUnder(root, wanted) {
  const hits = [];
  (function walk(dir) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (ent.name === wanted) hits.push(p);
    }
  })(root);
  return hits;
}

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

// ---------------------------------------------------------------------------
// Chunk 5 (stories 11, 12, 21, 22): the build runs the gate on the NEW tree
// in its scratch dir, writes the .gate-ok marker only after the gate passes,
// and replaces the old runtime only then — so an old runtime survives any
// failed build.
// ---------------------------------------------------------------------------

test('the stub build passes the gate and swaps: ember runs, weights ride along, .gate-ok present', () => {
  const dir = fs.mkdtempSync(path.join(SCRATCH_ROOT, 'happy-'));
  try {
    const out = path.join(dir, 'runtime-out');
    makeModelCache(path.join(dir, 'model-cache'));
    const run = runBuild(
      { EMBER_RUNTIME_OUT: out, EMBER_MODEL_CACHE: path.join(dir, 'model-cache') },
      dir,
    );
    assert.equal(run.status, 0, [
      'the stub build must pass the gate and swap the new tree in;',
      `stderr was:\n${run.stderr}`,
      `stdout was:\n${run.stdout}`,
    ].join('\n'));
    assert.equal(fs.existsSync(path.join(out, 'ember')), true, 'the new runtime must be at <out>/ember');
    const version = spawnSync(path.join(out, 'ember'), ['--version'], { encoding: 'utf8' });
    assert.equal(version.status, 0, `the built ember must run standalone; stderr: ${version.stderr}`);
    const weights = findUnder(path.join(out, 'models', 'hub'), 'model.safetensors');
    assert.ok(weights.length >= 1, 'the bundle must carry the model weights under <out>/models/hub');
    assert.equal(fs.existsSync(path.join(out, '.gate-ok')), true, 'the gate-passed marker must be in <out>');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('a failed gate leaves the OLD runtime in place: no marker, canary intact', () => {
  const dir = fs.mkdtempSync(path.join(SCRATCH_ROOT, 'gate-fail-'));
  try {
    const out = path.join(dir, 'runtime-out');
    // The OLD runtime, as a previous build left it: the canary proves it
    // is still the old tree after this build fails.
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, 'canary.txt'), 'the old runtime survives a failed gate');
    makeModelCache(path.join(dir, 'model-cache'));
    const run = runBuild(
      {
        EMBER_RUNTIME_OUT: out,
        EMBER_MODEL_CACHE: path.join(dir, 'model-cache'),
        EMBER_STUB_GATE: 'broken', // the stub ember answers the wrong capture code
      },
      dir,
    );
    assert.notEqual(run.status, 0, 'a build whose runtime fails the gate must fail');
    assert.equal(fs.existsSync(path.join(out, '.gate-ok')), false, 'no gate-passed marker may appear on a failed gate');
    assert.equal(
      fs.readFileSync(path.join(out, 'canary.txt'), 'utf8'),
      'the old runtime survives a failed gate',
      'the canary in the OLD runtime must still be there — the old runtime survives',
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

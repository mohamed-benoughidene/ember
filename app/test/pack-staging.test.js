'use strict';

/**
 * The packer's staging step as a testable seam (Batch 1, Chunk 8;
 * test seam 2). stageBundle() is called DIRECTLY on fixture trees in
 * /tmp/opencode/batch1/chunk8 — never on the real dist, never with
 * dpkg-deb. It must:
 *   (a) copy a relative symlink AS a relative link (verbatimSymlinks:
 *       true — fixes 4.1 #1);
 *   (b) normalize staged modes (files 0644, executables 0755, dirs
 *       0755 — chrome-sandbox stays 0755 in the stage, the postinst
 *       sets 4755 at INSTALL time) and REFUSE a world-writable file
 *       mixed into the stage before dpkg-deb --build (fixes 4.1 #2);
 *   (c) refuse a runtime folder WITHOUT the gate's .gate-ok marker
 *       (story 12 — the packer never packs a runtime the gate did
 *       not pass);
 *   (d) refuse a build machine that is not amd64 (D-19; the arch
 *       input is stubbed here, the real value is read from the
 *       MACHINE with `dpkg --print-architecture`, never a label);
 *   (e) read the runtime from the ONE location the build reports
 *       (EMBER_RUNTIME_OUT — fixes 4.1 #18).
 * And: merely requiring scripts/pack.js builds NOTHING (no stage).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');
const TMP_ROOT = '/tmp/opencode/batch1/chunk8';

const pack = require(path.join(APP_ROOT, 'scripts', 'pack.js'));

/** Run one test against a fresh case folder under TMP_ROOT; the
 * folder is always removed afterwards (test temp dirs are cleaned). */
function withCase(label, fn) {
  return () => {
    const dir = fs.mkdtempSync(path.join(TMP_ROOT, `pack-staging-${label}-`));
    try {
      fn(dir);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  };
}

/** The fixture tree: a relative symlink, a mode-777 regular file
 * (plain data), a mode-777 executable (shebang script), a 0700
 * subdirectory, and Electron's setuid helper name (it ships 4755 in
 * the electron zip — the stage must keep it at plain 0755). */
function makeTree(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const sub = path.join(dir, 'sub');
  fs.mkdirSync(sub);
  fs.chmodSync(sub, 0o700);
  fs.writeFileSync(path.join(dir, 'real-file'), 'plain data\n');
  fs.writeFileSync(path.join(dir, '777-data.bin'), 'raw bytes\n');
  fs.chmodSync(path.join(dir, '777-data.bin'), 0o777);
  fs.writeFileSync(path.join(dir, '777-exec.sh'), '#!/bin/sh\ntrue\n');
  fs.chmodSync(path.join(dir, '777-exec.sh'), 0o777);
  fs.writeFileSync(path.join(dir, 'chrome-sandbox'), '\x7fELF-fake-binary\n');
  fs.chmodSync(path.join(dir, 'chrome-sandbox'), 0o4755);
  fs.symlinkSync('real-file', path.join(dir, 'link')); // RELATIVE link
  return dir;
}

/** A stub runtime. marker: the build writes .gate-ok only after the
 * gate passes (Batch 1 Chunk 5). */
function makeRuntime(dir, { marker = true } = {}) {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'ember'), '#!/bin/sh\ntrue\n');
  fs.writeFileSync(path.join(dir, 'weights.bin'), 'fake model weights\n');
  if (marker) fs.writeFileSync(path.join(dir, '.gate-ok'), '');
  return dir;
}

/** Stage one case: the fixture tree under app/code, the case's stub
 * runtime, amd64 machine (unless stubbed otherwise). */
function stageCase(dir, overrides = {}) {
  const options = {
    stage: path.join(dir, 'stage'),
    entries: [{ src: makeTree(path.join(dir, 'tree')), dest: path.join('app', 'code') }],
    machineArch: 'amd64',
    version: '0.0.0',
    ...overrides,
  };
  if (!('runtime' in overrides)) options.runtime = makeRuntime(path.join(dir, 'runtime'));
  return pack.stageBundle(options);
}

test('case a: the staged tree keeps the relative symlink a RELATIVE link', withCase('a-relative-link', (dir) => {
  stageCase(dir);
  const stagedLink = path.join(dir, 'stage', 'app', 'code', 'link');
  assert.ok(fs.lstatSync(stagedLink).isSymbolicLink(), 'the staged link must be copied AS a link (verbatimSymlinks: true — finding 4.1 #1)');
  const target = fs.readlinkSync(stagedLink);
  assert.ok(!path.isAbsolute(target), `the staged link target must stay RELATIVE, got ${JSON.stringify(target)}`);
  assert.ok(fs.existsSync(path.join(path.dirname(stagedLink), target)), 'the staged relative link must still resolve inside the stage');
}));

test('case b: staged modes are safe (0644 files, 0755 executables and dirs, chrome-sandbox 0755) and a mixed-in 777 file is refused', withCase('b-safe-modes', (dir) => {
  stageCase(dir);
  const code = path.join(dir, 'stage', 'app', 'code');

  // Modes are normalized while staging: source modes are never trusted.
  assert.equal(fs.statSync(path.join(code, '777-data.bin')).mode & 0o7777, 0o644, 'a 777 plain data file must stage as 0644');
  assert.equal(fs.statSync(path.join(code, '777-exec.sh')).mode & 0o7777, 0o755, 'a 777 executable (shebang) must stage as 0755');
  assert.equal(fs.statSync(path.join(code, 'sub')).mode & 0o7777, 0o755, 'every directory must stage as 0755');
  assert.equal(fs.statSync(path.join(code, 'real-file')).mode & 0o7777, 0o644, 'a plain file must stage as 0644');
  assert.equal(
    fs.statSync(path.join(code, 'chrome-sandbox')).mode & 0o7777,
    0o755,
    'chrome-sandbox stays 0755 in the stage (the postinst sets setuid 4755 at INSTALL time)',
  );

  // No staged file is world-writable anywhere in the tree (4.1 #2:
  // the shipped 0.2.0 deb carried 70 of them).
  const staged = [];
  const walk = (d) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.isFile()) staged.push(p);
    }
  };
  walk(path.join(dir, 'stage'));
  for (const p of staged) {
    assert.equal(fs.statSync(p).mode & 0o002, 0, `${p} must not be world-writable in the stage`);
  }

  // The pre-build gate: a world-writable file that sneaks INTO the
  // staged tree is refused before dpkg-deb --build.
  const sneaky = path.join(code, 'sneaky');
  fs.writeFileSync(sneaky, 'planted\n');
  fs.chmodSync(sneaky, 0o777);
  assert.throws(
    () => pack.assertNoWorldWritable(path.join(dir, 'stage')),
    (err) => {
      assert.match(err.message, /world-writable/);
      assert.match(err.message, /sneaky/);
      return true;
    },
    'the pre-build assert must refuse a mixed-in world-writable staged file',
  );
}));

test('case c: staging refuses a runtime folder WITHOUT the .gate-ok marker', withCase('c-no-marker', (dir) => {
  assert.throws(
    () => stageCase(dir, { runtime: makeRuntime(path.join(dir, 'runtime'), { marker: false }) }),
    /\.gate-ok/,
    'the packer must never pack a runtime the gate did not pass (story 12)',
  );
}));

test('case d: staging refuses a machine that is not amd64; the real arch is read from the MACHINE', withCase('d-not-amd64', (dir) => {
  assert.throws(
    () => stageCase(dir, { machineArch: 'arm64' }),
    /amd64/,
    'the .deb is amd64-only (D-19, finding 4.1 #15)',
  );
  // The shipped helper checks the MACHINE, never a label.
  const fromDpkg = execFileSync('dpkg', ['--print-architecture'], { encoding: 'utf8' }).trim();
  assert.equal(pack.machineArch(), fromDpkg);
}));

test('case e: the runtime comes from the ONE location the build reports (EMBER_RUNTIME_OUT)', withCase('e-runtime-out', (dir) => {
  const runtime = makeRuntime(path.join(dir, 'runtime'));
  process.env.EMBER_RUNTIME_OUT = runtime;
  try {
    assert.equal(pack.runtimeOut(), runtime, 'runtimeOut() must be exactly EMBER_RUNTIME_OUT (finding 4.1 #18)');
    stageCase(dir, { runtime: pack.runtimeOut() });
    assert.ok(fs.existsSync(path.join(dir, 'stage', 'app', 'ember-runtime', 'ember')), 'the runtime is staged from the ONE EMBER_RUNTIME_OUT location');
  } finally {
    delete process.env.EMBER_RUNTIME_OUT;
  }
}));

test('merely requiring the module builds nothing (no stage)', () => {
  // A fresh child process: with the old pack.js, requiring it RAN the
  // pack (main() at load). EMBER_RUNTIME_OUT points at a folder that
  // does not exist, so an at-load run would fail loudly, and the
  // export check below fails while pack.js exports nothing.// The guarantee: requiring pack.js must not run the pack, so the stage
// folder is neither created nor changed. On a machine with an old build
// the folder already exists — pin its exact state instead of demanding
// it be absent.
const stageRoot = path.join(APP_ROOT, 'dist', 'ember-app');
const snapshotStage = (root) => {
  if (!fs.existsSync(root)) return null;
  const out = {};
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      const st = fs.statSync(p);
      out[path.relative(root, p)] = `${st.size}:${st.mtimeMs}:${entry.isDirectory() ? 'd' : 'f'}`;
      if (entry.isDirectory()) walk(p);
    }
  };
  walk(root);
  return out;
};
const stageBefore = snapshotStage(stageRoot);
const child = spawnSync(
    process.execPath,
    [
      '-e',
      `const p = require(${JSON.stringify(path.join(APP_ROOT, 'scripts', 'pack.js'))});` +
        `if (typeof p.stageBundle !== 'function') { console.error('pack.js exports nothing'); process.exit(3); }`,
    ],
    { env: { ...process.env, EMBER_RUNTIME_OUT: path.join(TMP_ROOT, 'no-such-runtime') } },
  );
  assert.equal(child.status, 0, `requiring scripts/pack.js must not run the pack and must export stageBundle:\n${child.stderr}`);
  assert.deepEqual(snapshotStage(stageRoot), stageBefore, 'merely requiring pack.js must not create or change ANY stage file (app/dist/ember-app)');
});

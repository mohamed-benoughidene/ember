'use strict';

/**
 * The .deb check script (app/scripts/check-deb.sh), Batch 1 Chunk 10.
 *
 * The check is the last gate an installable package passes through:
 *   - every symlink target must stay INSIDE the package (decision I12:
 *     every library is bundled — a link to /usr/lib/... or to the build
 *     box is refused),
 *   - no regular file may be world-writable,
 *   - the bundled runtime must carry the migrations .sql files,
 *   - the model weights must be under models/hub,
 *   - the control Architecture must be amd64 (decision D-19).
 *
 * Save policy (D-12 + D-21): on PASS the .deb + a dated report are saved
 * into the release folder and only the newest 3 builds are kept; on FAIL
 * the report is saved but the .deb never is.
 *
 * Fixtures: tiny packages built with `dpkg-deb --build` (no fakeroot —
 * the check reads modes, not ownership), built here under TMPDIR.
 * The release folder is an INPUT to the script (argument 2), so the
 * tests never write into the real app/dist/release.
 * The script does NOT run in CI (D-11); these tests only exercise it
 * on tiny fixtures — no full build, no real .deb touched.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');
const SCRIPT = path.join(APP_ROOT, 'scripts', 'check-deb.sh');

// Plan safety rule: all test temp files under /tmp/opencode/batch1/ (the
// harness sets TMPDIR to a folder inside it).
const TMP_BASE = process.env.TMPDIR && path.isAbsolute(process.env.TMPDIR)
  ? process.env.TMPDIR
  : '/tmp/opencode/batch1';

// The two content paths the check requires inside the package
// (the same layout the real pack produces, see scripts/pack.js).
const MIGRATIONS_DIR = 'opt/ember/app/ember-runtime/_internal/ember/adapters/migrations';
const HUB_DIR = 'opt/ember/app/ember-runtime/models/hub';

function makeTree(root) {
  fs.mkdirSync(root, { recursive: true });
  // control: the plan's clean fixture says Architecture: amd64 (case f overrides)
  fs.mkdirSync(path.join(root, 'DEBIAN'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'DEBIAN', 'control'),
    [
      'Package: ember-app-fixture',
      'Version: 0.0.0-1',
      'Section: utils',
      'Priority: optional',
      'Architecture: amd64',
      'Maintainer: Ember maintainer <maintainer@problem.invalid>',
      'Description: ember-app .deb check fixture',
      ' A throwaway package built by test/check-deb.test.js.',
      '',
    ].join('\n'),
  );
  // the required migrations .sql (plan fixture a: one 001_create_sources.sql-style file)
  fs.mkdirSync(path.join(root, MIGRATIONS_DIR), { recursive: true });
  fs.writeFileSync(path.join(root, MIGRATIONS_DIR, '001_create_sources.sql'), 'CREATE TABLE sources (id INTEGER PRIMARY KEY);\n');
  // the required model weight, as a REAL file (a relative snapshot link points at it)
  const blob = path.join(root, HUB_DIR, 'models--BAAI--bge-base-en-v1.5', 'blobs', '61');
  fs.mkdirSync(blob, { recursive: true });
  fs.writeFileSync(path.join(blob, 'model.safetensors'), 'fixture-weights');
  // one RELATIVE symlink (fixture a: relative symlinks only) — the real
  // hub snapshot layout, pointing from snapshots/<sha>/ into blobs/
  const snap = path.join(root, HUB_DIR, 'models--BAAI--bge-base-en-v1.5', 'snapshots', 'a5');
  fs.mkdirSync(snap, { recursive: true });
  fs.symlinkSync('../../blobs/61/model.safetensors', path.join(snap, 'model.safetensors'));
  return root;
}

function buildDeb(tmpRoot, tree, debName) {
  const debPath = path.join(tmpRoot, debName);
  const out = spawnSync('dpkg-deb', ['--build', tree, debPath], { encoding: 'utf8' });
  assert.equal(out.status, 0, `dpkg-deb --build failed for ${debName}:\n${out.stderr}`);
  return debPath;
}

function runCheck(debPath, releaseDir) {
  return spawnSync('bash', [SCRIPT, debPath, releaseDir], { encoding: 'utf8' });
}

const tmpRoot = path.join(TMP_BASE, `check-deb-test-${process.pid}-${Date.now()}`);
let cleanTrees = [];

test.before(() => {
  fs.mkdirSync(tmpRoot, { recursive: true });
  // four distinct clean builds for the retention case (each with its own
  // control version, so release-file names cannot collide)
  for (const n of [1, 2, 3, 4]) {
    const tree = makeTree(path.join(tmpRoot, `clean-tree-${n}`));
    let control = fs.readFileSync(path.join(tree, 'DEBIAN', 'control'), 'utf8');
    control = control.replace('Version: 0.0.0-1', `Version: 0.0.${n}-1`);
    fs.writeFileSync(path.join(tree, 'DEBIAN', 'control'), control);
    cleanTrees.push(tree);
  }
  // (b) clean + ONE absolute symlink (to a build-box path, as the real
  // 0.2.0 .deb has for its scipy libs)
  const b = makeTree(path.join(tmpRoot, 'abs-link-tree'));
  fs.symlinkSync('/home/mo/lab/ember/app/dist/ember-runtime/_internal/libgfortran.so.5', path.join(b, 'opt/ember/app/ember-runtime/_internal/libgfortran.so.5'));
  // (c) clean + ONE world-writable REGULAR file
  const c = makeTree(path.join(tmpRoot, 'world-writable-tree'));
  const ww = path.join(c, 'opt/ember/app/ember-runtime/_internal/leaky-data.json');
  fs.writeFileSync(ww, '{}');
  fs.chmodSync(ww, 0o666);
  // (d) clean but NO migrations .sql
  const d = makeTree(path.join(tmpRoot, 'no-migrations-tree'));
  fs.rmSync(path.join(d, MIGRATIONS_DIR, '001_create_sources.sql'));
  // (e) clean but NO model.safetensors under models/hub
  const e = makeTree(path.join(tmpRoot, 'no-model-tree'));
  fs.rmSync(path.join(e, HUB_DIR, 'models--BAAI--bge-base-en-v1.5', 'blobs', '61'), { recursive: true });
  fs.rmSync(path.join(e, HUB_DIR, 'models--BAAI--bge-base-en-v1.5', 'snapshots', 'a5', 'model.safetensors'));
  // (f) clean but Architecture: arm64
  const f = makeTree(path.join(tmpRoot, 'arm64-tree'));
  const fControl = fs.readFileSync(path.join(f, 'DEBIAN', 'control'), 'utf8').replace('Architecture: amd64', 'Architecture: arm64');
  fs.writeFileSync(path.join(f, 'DEBIAN', 'control'), fControl);
});

test.after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

test('(a) a clean fixture passes and a dated report is written into the release folder', () => {
  const deb = buildDeb(tmpRoot, cleanTrees[0], 'ember-app-fixture_0.0.1-1_amd64.deb');
  const release = path.join(tmpRoot, 'release-a');
  const out = runCheck(deb, release);
  assert.equal(out.status, 0, `expected PASS, got ${out.status}\nstdout:\n${out.stdout}\nstderr:\n${out.stderr}`);
  // the .deb is saved into the release folder
  assert.ok(fs.existsSync(path.join(release, 'ember-app-fixture_0.0.1-1_amd64.deb')), 'the .deb was not saved into the release folder');
  // the report is written and dated (an 8-digit date + T + 6-digit UTC time in the name)
  const reports = fs.readdirSync(release).filter((f) => f.endsWith('.report.txt'));
  assert.equal(reports.length, 1, `exactly one report expected, got: ${reports.join(', ')}`);
  assert.match(reports[0], /\d{8}T\d{6}Z/, 'the report name carries no UTC date');
  const report = fs.readFileSync(path.join(release, reports[0]), 'utf8');
  assert.match(report, /PASS/);
  assert.match(report, /ember-app-fixture_0\.0\.1-1_amd64\.deb/, 'the report does not say which package it is about');
});

test('(b) an absolute symlink is refused and the link is named', () => {
  const deb = buildDeb(tmpRoot, path.join(tmpRoot, 'abs-link-tree'), 'ember-app-fixture-abs-link_amd64.deb');
  const release = path.join(tmpRoot, 'release-b');
  const out = runCheck(deb, release);
  assert.notEqual(out.status, 0, 'the check PASSED a package with a link to /home/mo/...');
  const said = out.stdout + out.stderr;
  assert.match(said, /libgfortran\.so\.5/, 'the refusing output does not name the link');
  // D-12: the failing check never saves the .deb
  assert.equal(fs.readdirSync(release).filter((f) => f.endsWith('.deb')).length, 0, 'a failing check saved the .deb');
});

test('(c) a world-writable regular file is refused', () => {
  const deb = buildDeb(tmpRoot, path.join(tmpRoot, 'world-writable-tree'), 'ember-app-fixture-ww_amd64.deb');
  const release = path.join(tmpRoot, 'release-c');
  const out = runCheck(deb, release);
  assert.notEqual(out.status, 0, 'the check PASSED a package with a mode-666 regular file');
  const said = out.stdout + out.stderr;
  assert.match(said, /leaky-data\.json/, 'the refusing output does not name the world-writable file');
  assert.match(said, /world-writable/, 'the refusing output does not say why');
});

test('(d) missing migrations .sql files are refused', () => {
  const deb = buildDeb(tmpRoot, path.join(tmpRoot, 'no-migrations-tree'), 'ember-app-fixture-nomig_amd64.deb');
  const release = path.join(tmpRoot, 'release-d');
  const out = runCheck(deb, release);
  assert.notEqual(out.status, 0, 'the check PASSED a package without migrations');
  assert.match(out.stdout + out.stderr, /migration/i, 'the refusing output does not mention the migrations path');
});

test('(e) a missing model.safetensors under models/hub is refused', () => {
  const deb = buildDeb(tmpRoot, path.join(tmpRoot, 'no-model-tree'), 'ember-app-fixture-nomodel_amd64.deb');
  const release = path.join(tmpRoot, 'release-e');
  const out = runCheck(deb, release);
  assert.notEqual(out.status, 0, 'the check PASSED a package without the model weights');
  assert.match(out.stdout + out.stderr, /model\.safetensors/, 'the refusing output does not name the missing weight');
});

test('(f) a control Architecture other than amd64 is refused', () => {
  const deb = buildDeb(tmpRoot, path.join(tmpRoot, 'arm64-tree'), 'ember-app-fixture_arm64.deb');
  const release = path.join(tmpRoot, 'release-f');
  const out = runCheck(deb, release);
  assert.notEqual(out.status, 0, 'the check PASSED an arm64 package as an amd64 release');
  const said = out.stdout + out.stderr;
  assert.match(said, /arm64/, 'the refusing output does not name the found architecture');
  assert.match(said, /amd64/, 'the refusing output does not name the required architecture');
});

test('(g) retention keeps the newest 3 deb+report; a failing check saves the report, never the .deb', () => {
  const release = path.join(tmpRoot, 'release-g');
  // 4 passing checks -> exactly the 3 newest .deb (D-21) + their reports remain
  for (let i = 0; i < 4; i++) {
    const deb = buildDeb(tmpRoot, cleanTrees[i], `ember-app-fixture_0.0.${i + 1}-1_amd64.deb`);
    const out = runCheck(deb, release);
    assert.equal(out.status, 0, `passing check ${i + 1} failed:\n${out.stderr}`);
  }
  const debNames = fs.readdirSync(release).filter((f) => f.endsWith('.deb')).sort();
  assert.deepEqual(debNames, [
    'ember-app-fixture_0.0.2-1_amd64.deb',
    'ember-app-fixture_0.0.3-1_amd64.deb',
    'ember-app-fixture_0.0.4-1_amd64.deb',
  ], 'retention did not keep exactly the 3 newest builds (0.0.1 must be deleted)');
  const reportNames = fs.readdirSync(release).filter((f) => f.endsWith('.report.txt')).sort();
  assert.equal(reportNames.length, 3, `3 reports expected next to the 3 kept builds, got: ${reportNames.join(', ')}`);
  assert.ok(!reportNames.some((f) => f.includes('0.0.1')), "the deleted build's report was not deleted with it");

  // a failing check in the same release folder: report saved, .deb never (D-12)
  const badDeb = buildDeb(tmpRoot, path.join(tmpRoot, 'world-writable-tree'), 'ember-app-fixture-bad_amd64.deb');
  const out = runCheck(badDeb, release);
  assert.notEqual(out.status, 0, 'the failing check exited 0');
  assert.equal(fs.readdirSync(release).filter((f) => f.endsWith('.deb')).length, 3, 'the failing check must NOT save its .deb');
  const badReports = fs.readdirSync(release).filter((f) => f.startsWith('ember-app-fixture-bad') && f.endsWith('.report.txt'));
  assert.equal(badReports.length, 1, 'the failing check must still save its dated report');
  assert.match(fs.readFileSync(path.join(release, badReports[0]), 'utf8'), /FAIL/, 'the failing report does not say FAIL');
});

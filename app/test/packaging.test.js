'use strict';

/**
 * App step 13 static pins: the version lives in ONE place (package.json,
 * shown in the About box through app.getVersion()), the packaging
 * scripts exist and are executable, and the packer's layout names are
 * the ones the main-process resolver expects (bundle.json /
 * ember-runtime).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');

test('the app version is pinned in package.json, the engine version has ONE source (N2)', () => {
  // (a) the engine version's ONE source
  const initPy = fs.readFileSync(path.join(APP_ROOT, '..', 'ember', '__init__.py'), 'utf8');
  assert.match(initPy, /^__version__ = "\d+\.\d+\.\d+"$/m, 'ember/__init__.py must define __version__ as x.y.z');
  // (b) the CLI reads it from that one source (Chunk 1)
  const cliPy = fs.readFileSync(path.join(APP_ROOT, '..', 'ember', 'cli.py'), 'utf8');
  assert.ok(cliPy.includes('from ember import __version__'), 'ember/cli.py must import __version__ from ember');
  // (c) the engine package pulls its version from that one source, dynamically
  const pyproject = fs.readFileSync(path.join(APP_ROOT, '..', 'pyproject.toml'), 'utf8');
  assert.match(pyproject, /^dynamic = \["version"\]$/m, 'pyproject.toml must declare dynamic = ["version"]');
  assert.match(pyproject, /^version = \{attr = "ember\.__version__"\}$/m, 'pyproject.toml must set version attr = ember.__version__');
  // (d) the app version: plain x.y.z in package.json, and the known
  // hardcoded copies in the live-test doc still say that app version
  const pkg = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8'));
  assert.match(pkg.version ?? '', /^\d+\.\d+\.\d+$/, `package.json version ${JSON.stringify(pkg.version)} is not x.y.z`);
  const doc = fs.readFileSync(path.join(APP_ROOT, '..', 'docs', 'T50-live-test.md'), 'utf8').split('\n');
  for (const lineNo of [3, 203]) {
    const line = doc[lineNo - 1] ?? '';
    assert.ok(line.includes(pkg.version), `docs/T50-live-test.md:${lineNo} no longer names app version ${pkg.version}: ${JSON.stringify(line)}`);
  }
});

test('main.js reads the version from app.getVersion (what the About box shows)', () => {
  const text = fs.readFileSync(path.join(APP_ROOT, 'main', 'main.js'), 'utf8');
  assert.match(text, /function appVersion\(\)/);
  assert.match(text, /app\.getVersion\(\)/);
  assert.match(text, /`Ember \$\{appVersion\(\)\}`/, 'the About box must show the version');
});

test('the packaging scripts exist and are executable', () => {
  for (const script of ['scripts/pack.js', 'scripts/build-ember-runtime.sh']) {
    const p = path.join(APP_ROOT, script);
    assert.ok(fs.existsSync(p), `${script} is missing`);
    if (script.endsWith('.sh')) {
      const mode = fs.statSync(p).mode;
      assert.ok(mode & 0o111, `${script} is not executable`);
    }
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8'));
  assert.equal(pkg.scripts.package, 'node scripts/pack.js', 'npm run package must call the packer');
});

test('the packer, the resolver and the docs agree on the bundle layout names', () => {
  const pack = fs.readFileSync(path.join(APP_ROOT, 'scripts', 'pack.js'), 'utf8');
  const command = fs.readFileSync(path.join(APP_ROOT, 'main', 'ember-command.js'), 'utf8');
  for (const name of ['ember-runtime', 'bundle.json', 'BAAI/bge-base-en-v1.5']) {
    assert.ok(pack.includes(name), `scripts/pack.js does not name ${name}`);
  }
  for (const name of ['ember-runtime', 'bundle.json']) {
    assert.ok(command.includes(name), `main/ember-command.js does not name ${name}`);
  }
});

test('the runtime build bundles the migrations package and runs the F1 build gate', () => {
  // Fix F1: collect-all ember alone shipped no ember.adapters.migrations,
  // so EVERY capture in the installed app died in a Python traceback
  // (ModuleNotFoundError) before it even read the key. The build script
  // must name the package explicitly, and the gate must prove the
  // packed program: a no-key capture ends on the honest house line
  // (never a traceback) with every AI key variable stripped from its
  // env, and db-check on the same file reports version 13, result OK.
  const script = fs.readFileSync(path.join(APP_ROOT, 'scripts', 'build-ember-runtime.sh'), 'utf8');
  for (const needle of [
    '--hidden-import ember.adapters.migrations',
    '--add-data "$REPO_ROOT/ember/adapters/migrations:ember/adapters/migrations"',
  ]) {
    assert.ok(script.includes(needle), `build-ember-runtime.sh misses ${needle}`);
  }
  for (const needle of [
    'env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY',
    'the build gate',
    "must start 'error: '",
    '"version: 13"',
    '"result: OK"',
  ]) {
    assert.ok(script.includes(needle), `the F1 build gate is missing: ${needle}`);
  }
});

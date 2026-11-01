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

test('the version is a plain x.y.z in package.json and in ONE place only', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8'));
  assert.match(pkg.version ?? '', /^\d+\.\d+\.\d+$/, `package.json version ${JSON.stringify(pkg.version)} is not x.y.z`);
  const literal = new RegExp(`['"]${pkg.version.replace(/\./g, '\\.')}['"]`);
  const hits = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (/\.(js|mjs|html|css)$/.test(entry.name)) {
        if (literal.test(fs.readFileSync(p, 'utf8'))) hits.push(path.relative(APP_ROOT, p));
      }
    }
  };
  walk(path.join(APP_ROOT, 'main'));
  assert.deepEqual(hits, [], `the version is hardcoded in ${hits.join(', ')} — About must read package.json (app.getVersion)`);
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

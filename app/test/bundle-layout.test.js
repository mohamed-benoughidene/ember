'use strict';

/**
 * App step 13: the BUNDLED Ember runtime layout (decision 3-B) and the
 * APP-007 launch refusal when a packaged install lost it.
 *
 * Layout decision (recorded in docs/interface-measure.md): the bundled
 * runtime lives at `<appRoot>/ember-runtime/` — a PyInstaller ONEDIR
 * build of the real CLI with the relate embedder (CPU torch) and the
 * model weights (`<ember-runtime>/models/hub`) inside. The packer
 * writes `bundle.json` at the app root; its presence makes the runtime
 * REQUIRED, so a deleted runtime is APP-007 at boot (the step-file
 * test deletes it and expects the message), while a dev tree without
 * the manifest falls back to `ember` on PATH as always.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  resolveEmberCommand,
  checkEmberCommand,
  bundleLayout,
  bundledEmber,
  bundledChildEnv,
} = require('../main/ember-command');

function tempAppDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ember-bundle-'));
}

test('the env override still wins over everything (step 02 behaviour unchanged)', () => {
  assert.deepEqual(resolveEmberCommand({ EMBER_APP_COMMAND: 'node /x/fake-ember.js' }), [
    'node',
    '/x/fake-ember.js',
  ]);
  // ...even when a bundle is present and required:
  assert.deepEqual(
    resolveEmberCommand({ EMBER_APP_COMMAND: 'ember' }, { emberPath: '/nowhere/ember-runtime/ember', required: true }),
    ['ember'],
  );
});

test('a plain dev tree resolves to `ember` on PATH (no bundle, no manifest)', () => {
  const appDir = tempAppDir();
  assert.deepEqual(bundledEmber(appDir), { emberPath: null, required: false });
  assert.deepEqual(resolveEmberCommand({}, bundledEmber(appDir)), ['ember']);
});

test('a dev tree that BUILT a runtime uses it without a manifest (opportunistic)', () => {
  const appDir = tempAppDir();
  const exe = path.join(appDir, 'ember-runtime', 'ember');
  fs.mkdirSync(path.dirname(exe), { recursive: true });
  fs.writeFileSync(exe, '');
  assert.deepEqual(bundledEmber(appDir), { emberPath: exe, required: false });
  assert.deepEqual(resolveEmberCommand({}, bundledEmber(appDir)), [exe]);
  assert.deepEqual(checkEmberCommand(resolveEmberCommand({}, bundledEmber(appDir))), { ok: true });
});

test('the packer manifest makes the runtime REQUIRED; a real file resolves to it', () => {
  const appDir = tempAppDir();
  const exe = path.join(appDir, 'ember-runtime', 'ember');
  fs.mkdirSync(path.dirname(exe), { recursive: true });
  fs.writeFileSync(exe, '#!/bin/sh\n');
  fs.writeFileSync(path.join(appDir, 'bundle.json'), JSON.stringify({ kind: 'ember-app-bundle', emberRuntime: 'ember-runtime' }));
  assert.deepEqual(bundledEmber(appDir), { emberPath: exe, required: true });
  assert.deepEqual(resolveEmberCommand({}, bundledEmber(appDir)), [exe]);
});

test('APP-007: a packaged install whose bundled runtime was DELETED is refused at boot', () => {
  const appDir = tempAppDir();
  fs.writeFileSync(path.join(appDir, 'bundle.json'), JSON.stringify({ kind: 'ember-app-bundle', emberRuntime: 'ember-runtime' }));
  // noember-runtime/ folder at all — the step-file test deletes it
  const bundling = bundledEmber(appDir);
  assert.equal(bundling.required, true);
  const argv = resolveEmberCommand({}, bundling);
  const result = checkEmberCommand(argv);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-007');
  assert.equal(result.error.name, 'RuntimeMissing');
  assert.match(result.error.detail, /not found/);
});

test('APP-007: a corrupt or foreign bundle.json is never treated as ours (fail to PATH)', () => {
  const appDir = tempAppDir();
  fs.writeFileSync(path.join(appDir, 'bundle.json'), '{not json');
  assert.deepEqual(bundledEmber(appDir), { emberPath: null, required: false });
  fs.writeFileSync(path.join(appDir, 'bundle.json'), JSON.stringify({ emberRuntime: 'something-else' }));
  assert.deepEqual(bundledEmber(appDir), { emberPath: null, required: false });
});

test('bundledChildEnv: the model weights are read from inside the runtime, offline', () => {
  const exe = '/opt/ember/app/ember-runtime/ember';
  const env = bundledChildEnv(exe);
  assert.equal(env.HF_HOME, '/opt/ember/app/ember-runtime/models');
  assert.equal(env.HF_HUB_OFFLINE, '1');
  assert.equal(env.TRANSFORMERS_OFFLINE, '1');
  assert.deepEqual(bundledChildEnv(null), {});
});

test('bundleLayout: the on-disk names the packer and the resolver share', () => {
  const layout = bundleLayout();
  assert.equal(layout.manifest, 'bundle.json');
  assert.equal(layout.dir, 'ember-runtime');
  assert.equal(layout.exe, path.join('ember-runtime', 'ember'));
  assert.deepEqual(layout, bundleLayout('ember'));
});

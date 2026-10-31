'use strict';

/**
 * The packer (app step 13, decision 2-A: Debian is the only real
 * installer for V1; Windows/macOS stay CI launch checks).
 *
 *   npm run package
 *     -> app/dist/ember-app/            the staged install tree
 *        (electron/, app/, app/ember-runtime/, app/bundle.json)
 *     -> app/dist/ember-app_<version>_amd64.deb   the Debian package
 *     and prints the size of every part (the step's install-size
 *     report; the honest totals land in docs/interface-measure.md).
 *
 * The runtime must exist first (build-ember-runtime.sh — PyInstaller
 * onedir WITH the relate embedder and the model weights, decision 3-B);
 * the packer never builds it silently.
 *
 * No new npm packages are used: the copying is plain Node, and the
 * `.deb` is built with the system `dpkg-deb`. Signing is NOT done (no
 * key on this machine) — the release notes must say the package is
 * unsigned.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');

/** All packaging artifacts live here. Default app/dist; override with
 * EMBER_PACK_ROOT when the working tree sits on a small filesystem
 * (the bundle with torch needs ~3.5 GB of scratch, stage and .deb). */
const PACK_ROOT = process.env.EMBER_PACK_ROOT || path.join(APP_ROOT, 'dist');

function fail(message) {
  process.stderr.write(`npm run package FAILED: ${message}\n`);
  process.exit(1);
}

/** cp -a that does not cross into npm env expansion. */
function cp(src, dest) {
  fs.cpSync(src, dest, { recursive: true, verbatimSymlinks: false });
}

function duMB(p) {
  return Number(execFileSync('du', ['-sm', p], { encoding: 'utf8' }).split('\t')[0]);
}

function main() {
  const pkg = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8'));
  const version = pkg.version;
  if (typeof version !== 'string' || !/^\d+\.\d+\.\d+$/.test(version)) {
    fail(`package.json must carry a plain x.y.z version in ONE place; found ${JSON.stringify(version)}`);
  }

  const electronDist = path.join(APP_ROOT, 'node_modules', 'electron', 'dist');
  if (!fs.existsSync(path.join(electronDist, 'electron'))) {
    fail('electron is not installed — run `npm ci --prefix app` first');
  }
  const runtime = process.env.EMBER_RUNTIME_OUT || path.join(APP_ROOT, 'dist', 'ember-runtime');
  if (!fs.existsSync(path.join(runtime, 'ember'))) {
    fail(`the bundled ember runtime is missing at ${runtime} — build it first:
  EMBER_PACK_VENV=<venv with ember + CPU torch + pyinstaller> \\
  EMBER_MODEL_CACHE=<HF hub cache with BAAI/bge-base-en-v1.5> \\
  bash app/scripts/build-ember-runtime.sh`);
  }
  const weights = fs.existsSync(path.join(runtime, 'models', 'hub'));
  if (!weights) {
    fail(`the runtime at ${runtime} carries NO model weights (rebuild with EMBER_MODEL_CACHE set) — decision 3-B bundles them so relate never downloads`);
  }

  const dist = PACK_ROOT;
  const stage = path.join(dist, 'ember-app');
  const optApp = path.join(stage, 'app');
  fs.rmSync(stage, { recursive: true, force: true });
  fs.mkdirSync(path.join(stage, 'electron'), { recursive: true });
  fs.mkdirSync(optApp, { recursive: true });

  process.stdout.write('== copying the Electron runtime ==\n');
  cp(electronDist, path.join(stage, 'electron'));

  process.stdout.write('== copying the app (renderer, main, preload, shared, assets, licence) ==\n');
  for (const part of ['main', 'preload', 'shared', 'renderer', 'assets']) {
    cp(path.join(APP_ROOT, part), path.join(optApp, part));
  }
  fs.copyFileSync(path.join(APP_ROOT, 'package.json'), path.join(optApp, 'package.json'));
  // The error-line pattern is shared with the Python suite (anti-drift);
  // the packaged app needs the fixture next to the app folder.
  fs.mkdirSync(path.join(optApp, 'tests', 'fixtures', 'bridge'), { recursive: true });
  fs.copyFileSync(
    path.join(APP_ROOT, '..', 'tests', 'fixtures', 'bridge', 'error_parsing_rule.txt'),
    path.join(optApp, 'tests', 'fixtures', 'bridge', 'error_parsing_rule.txt'),
  );
  fs.copyFileSync(path.join(APP_ROOT, '..', 'LICENSE'), path.join(optApp, 'LICENSE'));

  process.stdout.write('== copying the bundled ember runtime + model weights ==\n');
  cp(runtime, path.join(optApp, 'ember-runtime'));

  // The bundle manifest: when present, the bundled runtime is REQUIRED
  // (missing -> APP-007 at boot) and the model env points inside the app.
  fs.writeFileSync(
    path.join(optApp, 'bundle.json'),
    `${JSON.stringify(
      { kind: 'ember-app-bundle', version, emberRuntime: 'ember-runtime', model: 'BAAI/bge-base-en-v1.5' },
      null,
      2,
    )}\n`,
  );

  process.stdout.write('== building the .deb (dpkg-deb, no npm packages) ==\n');
  const debTree = path.join(dist, 'debian-tree');
  fs.rmSync(debTree, { recursive: true, force: true });
  const opt = path.join(debTree, 'opt', 'ember');
  fs.mkdirSync(path.join(debTree, 'DEBIAN'), { recursive: true });
  fs.mkdirSync(path.join(debTree, 'usr', 'share', 'applications'), { recursive: true });
  fs.mkdirSync(path.join(debTree, 'usr', 'share', 'doc', 'ember-app'), { recursive: true });
  fs.mkdirSync(path.join(debTree, 'usr', 'share', 'icons', 'hicolor', '256x256', 'apps'), { recursive: true });
  fs.mkdirSync(path.join(debTree, 'usr', 'bin'), { recursive: true });
  cp(stage, opt);

  // postinst: Electron's setuid chrome-sandbox helper (its own docs:
  // without 4755 root:root the GPU/kernel sandbox cannot start on Debian).
  fs.writeFileSync(
    path.join(debTree, 'DEBIAN', 'postinst'),
    ['#!/bin/sh', 'set -e', 'if [ -x /opt/ember/electron/chrome-sandbox ]; then chmod 4755 /opt/ember/electron/chrome-sandbox; fi', 'true', ''].join('\n'),
    { mode: 0o755 },
  );
  fs.chmodSync(path.join(debTree, 'DEBIAN', 'postinst'), 0o755);

  const control = [
    'Package: ember-app',
    `Version: ${version}-1`,
    'Section: utils',
    'Priority: optional',
    'Architecture: amd64',
    'Maintainer: Ember maintainer <maintainer@problem.invalid>',
    'Depends: libgtk-3-0, libnss3, libxtst6, libxss1, libgbm1, libdrm2, libxkbcommon0, libasound2 | libasound2t64, libatk-bridge2.0-0 | libatk-bridge2.0-0t64, libcups2 | libcups2t64',
    'Recommends: kwalletd6',
    'Installed-Size: <FILL>',
    'Description: Ember - your knowledge base, with a window over it',
    ' The Ember desktop app over the bundled `ember` CLI and relate embedder.',
    ' Local-first: the only network use is the AI service you choose.',
    ' Debian-only for V1 (Windows and macOS are launch-checked in CI).',
    ' This package is UNSIGNED.',
    '',
  ].join('\n');
  fs.writeFileSync(path.join(debTree, 'DEBIAN', 'control'), `${control}\n`);

  fs.writeFileSync(
    path.join(debTree, 'usr', 'bin', 'ember-app'),
    ['#!/bin/sh', 'exec /opt/ember/electron/electron /opt/ember/app "$@"', ''].join('\n'),
    { mode: 0o755 },
  );

  fs.writeFileSync(
    path.join(debTree, 'usr', 'share', 'applications', 'ember-app.desktop'),
    [
      '[Desktop Entry]',
      'Type=Application',
      'Name=Ember',
      'Comment=Your knowledge base, with a window over it',
      'Exec=/usr/bin/ember-app %F',
      'Icon=/usr/share/icons/hicolor/256x256/apps/ember-app.png',
      'Terminal=false',
      'Categories=Office;',
      '',
    ].join('\n'),
  );
  fs.copyFileSync(
    path.join(debTree, 'opt', 'ember', 'app', 'assets', 'icons', 'ember-256.png'),
    path.join(debTree, 'usr', 'share', 'icons', 'hicolor', '256x256', 'apps', 'ember-app.png'),
  );
  fs.copyFileSync(path.join(optApp, 'LICENSE'), path.join(debTree, 'usr', 'share', 'doc', 'ember-app', 'copyright'));

  const installedMB = duMB(path.join(opt, 'app')) + duMB(path.join(opt, 'electron'));
  let controlText = fs.readFileSync(path.join(debTree, 'DEBIAN', 'control'), 'utf8');
  controlText = controlText.replace('Installed-Size: <FILL>', `Installed-Size: ${Math.round(installedMB * 1024)}`);
  fs.writeFileSync(path.join(debTree, 'DEBIAN', 'control'), controlText);

  const debPath = path.join(dist, `ember-app_${version}-1_amd64.deb`);
  fs.rmSync(debPath, { force: true });
  // fakeroot: the archive entries must be root:root; this process is
  // not root — fakeroot fakes the ownership ONLY inside the archive.
  execFileSync('fakeroot', ['dpkg-deb', '--build', debTree, debPath], { stdio: 'inherit' });
  execFileSync('dpkg-deb', ['--info', debPath], { stdio: 'inherit' });

  process.stdout.write('\n== sizes (the step-13 install-size report) ==\n');
  const emberRuntimeMB = duMB(path.join(optApp, 'ember-runtime'));
  const sizes = {
    electron: duMB(path.join(stage, 'electron')),
    appCode: duMB(optApp) - emberRuntimeMB,
    emberRuntime: emberRuntimeMB,
    modelWeights: duMB(path.join(optApp, 'ember-runtime', 'models', 'hub')),
    stagedTotal: duMB(stage),
    deb: duMB(debPath),
  };
  const lines = [
    `electron runtime        ${sizes.electron} MB`,
    `app code + fonts        ${sizes.appCode} MB`,
    `bundled ember runtime   ${sizes.emberRuntime} MB (PyInstaller onedir, CPU torch inside)`,
    `  of which model hub    ${sizes.modelWeights} MB (BAAI/bge-base-en-v1.5, bundled — no first-run download)`,
    `installed (staged)      ${sizes.stagedTotal} MB`,
    `the .deb                ${sizes.deb} MB  ${debPath}`,
    '',
    'Stage tree:      ' + stage,
    'Deb file:        ' + debPath,
    'Runtime source:  ' + runtime,
    'NOT VERIFIED here: a real `dpkg -i` install (it would modify this machine).',
    'Check instead:   dpkg-deb --contents ' + debPath,
  ];
  for (const line of lines) process.stdout.write(`${line}\n`);
  fs.writeFileSync(path.join(PACK_ROOT, 'sizes.txt'), `${lines.join('\n')}\n`);
}

try {
  main();
} catch (err) {
  fail(err instanceof Error ? err.message : String(err));
}

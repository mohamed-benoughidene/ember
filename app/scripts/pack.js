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
 * The staging step is a testable seam (Batch 1 Chunk 8, seam 2): the
 * pack-staging tests call stageBundle() directly on fixture trees, so
 * `main()` runs ONLY for the real `npm run package` (the require.main
 * guard at the bottom — merely requiring this module builds nothing).
 *
 * No new npm packages are used: the copying is plain Node, and the
 * `.deb` is built with the system `dpkg-deb`. Signing is NOT done (no
 * key on this machine) — the release notes must say the package is
 * unsigned.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const APP_ROOT = path.join(__dirname, '..');

/** All packaging artifacts live here. Default app/dist; override with
 * EMBER_PACK_ROOT when the working tree sits on a small filesystem
 * (the bundle with torch needs ~3.5 GB of scratch, stage and .deb). */
const PACK_ROOT = process.env.EMBER_PACK_ROOT || path.join(APP_ROOT, 'dist');

function fail(message) {
  process.stderr.write(`npm run package FAILED: ${message}\n`);
  process.exit(1);
}

/** cp -a that does not cross into npm env expansion. verbatimSymlinks:
 * true — a link is copied AS a link, so a relative link stays relative
 * (finding 4.1 #1). With `false` Node FOLLOWS the link and copies the
 * target as a real file — the link would be gone from the package. */
function cp(src, dest) {
  fs.cpSync(src, dest, { recursive: true, verbatimSymlinks: true });
}

/** The build machine's architecture, read from the MACHINE (never
 * from a control-file label): `dpkg --print-architecture` (D-19). */
function machineArch() {
  return execFileSync('dpkg', ['--print-architecture'], { encoding: 'utf8' }).trim();
}

/** The ONE runtime location: the build reports where it left the
 * runtime in EMBER_RUNTIME_OUT, and the packer reads exactly that
 * (finding 4.1 #18). */
function runtimeOut() {
  return process.env.EMBER_RUNTIME_OUT || path.join(APP_ROOT, 'dist', 'ember-runtime');
}

/** The ENGINE version, read from the one source (ember/__init__.py —
 * the same file `ember --version` uses). The app version (package.json)
 * and the engine version MAY differ; bundle.json records BOTH (story
 * 18, finding 4.1 #16). */
function engineVersion() {
  const source = fs.readFileSync(path.join(APP_ROOT, '..', 'ember', '__init__.py'), 'utf8');
  const match = source.match(/^__version__\s*=\s*["']([^"']+)["']/m);
  if (!match) {
    throw new Error('cannot read the engine version: no __version__ = "x.y.z" line in ember/__init__.py');
  }
  return match[1];
}

/** A deterministic CONTENT hash of a runtime tree: every entry (dirs,
 * files, symlinks), sorted by relative path; files hash their bytes.
 * The same tree hashes the same everywhere; one changed byte changes
 * the hash. Recorded in bundle.json so a shipped package can be
 * checked against the runtime the packer actually staged (finding
 * 4.1 #16). */
function runtimeContentHash(root) {
  const lines = [];
  const walk = (dir) => {
    const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const entry of entries) {
      const p = path.join(dir, entry.name);
      const rel = path.relative(root, p).split(path.sep).join('/');
      if (entry.isSymbolicLink()) {
        lines.push(`l ${rel} ${fs.readlinkSync(p)}`);
      } else if (entry.isDirectory()) {
        lines.push(`d ${rel}`);
        walk(p);
      } else if (entry.isFile()) {
        lines.push(`f ${rel} ${crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')}`);
      }
    }
  };
  walk(root);
  const hash = crypto.createHash('sha256');
  for (const line of lines) hash.update(`${line}\n`);
  return hash.digest('hex');
}

/** Every regular file under directory `root` whose mode is
 * world-writable. Symlinks are skipped: they are copied as links,
 * never followed, and a link's own mode bits mean nothing. */
function findWorldWritable(root) {
  const hits = [];
  const stack = [root];
  while (stack.length > 0) {
    const dir = stack.pop();
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      const st = fs.lstatSync(p);
      if (st.isSymbolicLink()) continue;
      if (st.isDirectory()) stack.push(p);
      else if (st.isFile() && (st.mode & 0o002) !== 0) hits.push(p);
    }
  }
  return hits;
}

/** The pre-build gate: refuse any world-writable file in the staged
 * tree (finding 4.1 #2). Runs before `dpkg-deb --build` turns the
 * tree into the shipped archive. */
function assertNoWorldWritable(root) {
  const hits = findWorldWritable(root);
  if (hits.length > 0) {
    throw new Error(`refusing to pack: ${hits.length} world-writable file(s) in the stage, e.g. ${hits[0]} — staged files must be 0644 or 0755 only`);
  }
}

/** True when the file's CONTENT says "executable": an ELF binary
 * (\x7fELF) or a script with a shebang (#!). Source modes are never
 * trusted — a world-writable 777 plain data file must stage as 0644,
 * not as an "executable". */
function contentIsExecutable(p) {
  const fd = fs.openSync(p, 'r');
  try {
    const head = Buffer.alloc(4);
    fs.readSync(fd, head, 0, 4, 0);
    return (
      (head[0] === 0x7f && head[1] === 0x45 && head[2] === 0x4c && head[3] === 0x46) || // \x7fELF
      (head[0] === 0x23 && head[1] === 0x21) // "#!"
    );
  } finally {
    fs.closeSync(fd);
  }
}

/** Safe modes everywhere in the stage: dirs 0755, executables 0755,
 * every other file 0644. chrome-sandbox included — it stays 0755 in
 * the stage; the .deb's postinst sets setuid 4755 at INSTALL time. */
function normalizeModes(root) {
  fs.chmodSync(root, 0o755);
  const stack = [root];
  while (stack.length > 0) {
    const dir = stack.pop();
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      const st = fs.lstatSync(p);
      if (st.isSymbolicLink()) continue;
      if (st.isDirectory()) {
        fs.chmodSync(p, 0o755);
        stack.push(p);
      } else if (st.isFile()) {
        fs.chmodSync(p, contentIsExecutable(p) ? 0o755 : 0o644);
      }
    }
  }
}

/**
 * The staging step, as a testable seam (Batch 1 Chunk 8, seam 2): copy
 * the pack inputs into one clean stage folder — `entries` (a list of
 * {src, dest}, dest relative to the stage) plus the runtime to
 * app/ember-runtime — and write bundle.json. Refuses, BEFORE a single
 * byte is copied:
 *   - a stage path that is not a safe absolute folder;
 *   - a build machine that is not amd64 (D-19 — the caller passes the
 *     machine's `dpkg --print-architecture`, so the tests can stub it);
 *   - a runtime without the gate's `.gate-ok` marker (the packer never
 *     packs a runtime the gate did not pass — story 12).
 * Copies are verbatim (relative symlinks stay relative); modes are
 * normalized; the finished stage is re-checked world-writable-free
 * before `dpkg-deb --build`. Returns { stage, app }.
 */
function stageBundle({ stage, entries, runtime, machineArch, version }) {
  if (!path.isAbsolute(stage) || path.resolve(stage) === '/') {
    throw new Error(`refusing to pack: the stage must be a safe absolute folder path, not ${JSON.stringify(stage)}`);
  }
  if (machineArch !== 'amd64') {
    throw new Error(`refusing to pack: this build machine is ${machineArch ? JSON.stringify(machineArch) : 'of unknown architecture'}, not amd64 — the .deb is amd64-only (D-19)`);
  }
  if (!fs.existsSync(path.join(runtime, '.gate-ok'))) {
    throw new Error(`refusing to pack: the runtime at ${runtime} carries NO .gate-ok marker — the gate did not pass, so it must not be packed (rebuild the runtime)`);
  }

  fs.rmSync(stage, { recursive: true, force: true });
  fs.mkdirSync(stage, { recursive: true });
  const optApp = path.join(stage, 'app');
  fs.mkdirSync(optApp, { recursive: true });
  for (const { src, dest } of entries) {
    const destAbs = path.join(stage, dest);
    fs.mkdirSync(path.dirname(destAbs), { recursive: true });
    cp(src, destAbs);
  }

  process.stdout.write('== copying the bundled ember runtime + model weights ==\n');
  cp(runtime, path.join(optApp, 'ember-runtime'));

  normalizeModes(stage);

  // The bundle manifest: when present, the bundled runtime is REQUIRED
  // (missing -> APP-007 at boot) and the model env points inside the
  // app. It records BOTH versions (app from package.json via the
  // `version` input; engine read here from ember/__init__.py — they
  // may differ, story 18) and a sha256 content hash of the runtime
  // tree (story 20, finding 4.1 #16).
  fs.writeFileSync(
    path.join(optApp, 'bundle.json'),
    `${JSON.stringify(
      {
        kind: 'ember-app-bundle',
        version,
        engineVersion: engineVersion(),
        emberRuntime: 'ember-runtime',
        model: 'BAAI/bge-base-en-v1.5',
        runtimeHash: runtimeContentHash(runtime),
      },
      null,
      2,
    )}\n`,
  );

  // The last gate before `dpkg-deb --build`: nothing world-writable.
  assertNoWorldWritable(stage);
  return { stage, app: optApp };
}

function duMB(p) {
  return Number(execFileSync('du', ['-sm', p], { encoding: 'utf8' }).split('\t')[0]);
}

/**
 * The .deb control file, as a small exported function (its output is
 * data the pack-staging test checks directly). Depends carries every
 * Electron base lib PLUS the four the shipped 0.2.0 missed (finding
 * 4.1 #17, story 20): libnotify4 (desktop notifications), libatspi2.0-0
 * (accessibility), libuuid1, and libsecret-1-0 — the secret-service
 * backend Electron's safeStorage crypts the API key against.
 */
function buildControl({ version }) {
  return [
    'Package: ember-app',
    `Version: ${version}-1`,
    'Section: utils',
    'Priority: optional',
    'Architecture: amd64',
    'Maintainer: Ember maintainer <maintainer@problem.invalid>',
    'Depends: libgtk-3-0, libnss3, libxtst6, libxss1, libgbm1, libdrm2, libxkbcommon0, libasound2 | libasound2t64, libatk-bridge2.0-0 | libatk-bridge2.0-0t64, libcups2 | libcups2t64, libnotify4, libatspi2.0-0, libuuid1, libsecret-1-0',
    'Recommends: kwalletd6',
    'Installed-Size: <FILL>',
    'Description: Ember - your knowledge base, with a window over it',
    ' The Ember desktop app over the bundled `ember` CLI and relate embedder.',
    ' Local-first: the only network use is the AI service you choose.',
    ' Debian-only for V1 (Windows and macOS are launch-checked in CI).',
    ' This package is UNSIGNED.',
    '',
  ].join('\n');
}

function main() {
  const pkg = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8'));
  const version = pkg.version;
  if (typeof version !== 'string' || !/^\d+\.\d+\.\d+$/.test(version)) {
    throw new Error(`package.json must carry a plain x.y.z version in ONE place; found ${JSON.stringify(version)}`);
  }

  const electronDist = path.join(APP_ROOT, 'node_modules', 'electron', 'dist');
  if (!fs.existsSync(path.join(electronDist, 'electron'))) {
    throw new Error('electron is not installed — run `npm ci --prefix app` first');
  }
  const runtime = runtimeOut();
  if (!fs.existsSync(path.join(runtime, 'ember'))) {
    throw new Error(`the bundled ember runtime is missing at ${runtime} — build it first:
  EMBER_PACK_VENV=<venv with ember + CPU torch + pyinstaller> \\
  EMBER_MODEL_CACHE=<HF hub cache with BAAI/bge-base-en-v1.5> \\
  bash app/scripts/build-ember-runtime.sh`);
  }
  const weights = fs.existsSync(path.join(runtime, 'models', 'hub'));
  if (!weights) {
    throw new Error(`the runtime at ${runtime} carries NO model weights (rebuild with EMBER_MODEL_CACHE set) — decision 3-B bundles them so relate never downloads`);
  }

  const dist = PACK_ROOT;
  const stage = path.join(dist, 'ember-app');
  const buildArch = machineArch(); // check the MACHINE, not the label (D-19)

  console.log('== staging the bundle ==');
  const { app: optApp } = stageBundle({
    stage,
    entries: [
      { src: electronDist, dest: 'electron' },
      // the app code: main, preload, shared, renderer, assets, licence
      ...['main', 'preload', 'shared', 'renderer', 'assets'].map((part) => ({
        src: path.join(APP_ROOT, part),
        dest: path.join('app', part),
      })),
      { src: path.join(APP_ROOT, 'package.json'), dest: path.join('app', 'package.json') },
      // The error-line pattern is shared with the Python suite (anti-drift);
      // the packaged app needs the fixture next to the app folder.
      {
        src: path.join(APP_ROOT, '..', 'tests', 'fixtures', 'bridge', 'error_parsing_rule.txt'),
        dest: path.join('app', 'tests', 'fixtures', 'bridge', 'error_parsing_rule.txt'),
      },
      { src: path.join(APP_ROOT, '..', 'LICENSE'), dest: path.join('app', 'LICENSE') },
    ],
    runtime,
    machineArch: buildArch,
    version,
  });

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

  const control = buildControl({ version });
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
  // The stage leaves here clean or not at all (finding 4.1 #2).
  assertNoWorldWritable(stage);
  // fakeroot: the archive entries must be root:root; this process is
  // not root — fakeroot fakes the ownership ONLY inside the archive.
  execFileSync('fakeroot', ['dpkg-deb', '--build', debTree, debPath], { stdio: 'inherit' });

  // The pack ends with the check (Batch 1 Chunk 11; D-11/D-12/D-21
  // wiring): the freshly built .deb must pass scripts/check-deb.sh
  // before it counts as built. On FAIL the check saves its dated
  // report and never the .deb (D-12), and its non-zero exit throws out
  // of execFileSync — the fail() in the require.main guard below turns
  // that into a pack failure. On PASS the .deb + report are saved into
  // the release folder, newest 3 kept (D-21). The release folder
  // follows EMBER_PACK_ROOT (default app/dist/release), the same way
  // the check-deb tests pass their own release folder as argument 2.
  execFileSync(
    'bash',
    [path.join(APP_ROOT, 'scripts', 'check-deb.sh'), debPath, path.join(PACK_ROOT, 'release')],
    { stdio: 'inherit' },
  );

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

module.exports = { stageBundle, assertNoWorldWritable, runtimeOut, machineArch, buildControl };

// Only the real `npm run package` runs the pack; merely requiring the
// module (the pack-staging tests) builds nothing.
if (require.main === module) {
  try {
    main();
  } catch (err) {
    fail(err instanceof Error ? err.message : String(err));
  }
}

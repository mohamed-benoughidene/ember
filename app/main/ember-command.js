'use strict';

/**
 * Where the app finds the `ember` command, and whether the chosen
 * knowledge-base file is usable (APP-006 / APP-007).
 *
 * Step 02: the command comes from the `EMBER_APP_COMMAND` environment
 * override (space-separated, e.g. "/path/.venv/bin/ember" or
 * "node /path/fake-ember.js"); the default is plain `ember` on PATH.
 *
 * Step 13 (packaging): the app can also use a BUNDLED Ember runtime —
 * the PyInstaller onedir build of the CLI placed at
 * `<appDir>/ember-runtime/` (with the model weights under
 * `<appDir>/ember-runtime/models/hub`). Two ways to land on it:
 *  - A packaged install carries `bundle.json` at the app root (written
 *    by `npm run package`). The bundled runtime is then REQUIRED:
 *    `resolveEmberCommand` returns its path even if the file is gone,
 *    so `checkEmberCommand` raises APP-007 (the step-file test deletes
 *    the runtime and expects the message).
 *  - Without the manifest (a dev tree), an existing
 *    `<appDir>/ember-runtime/` is used opportunistically; otherwise
 *    the app falls back to `ember` on PATH.
 * `EMBER_APP_COMMAND`, when set, always wins over everything above.
 */

const fs = require('node:fs');
const path = require('node:path');
const { appErrorInfo } = require('../shared/errors');

const WHERE = 'main.ember-command';
const SQLITE_MAGIC = Buffer.from('SQLite format 3\x00');

/** The packaging manifest the packer writes at the app root (step 13). */
const BUNDLE_MANIFEST = 'bundle.json';
/** The bundled Ember runtime, relative to the app root (step 13). */
const BUNDLE_DIR = 'ember-runtime';

/**
 * @param {string} exeName the platform executable name inside the bundle
 * @returns {string} the app-root-relative layout, one folder pair.
 */
function bundleLayout(exeName = process.platform === 'win32' ? 'ember.exe' : 'ember') {
  return { manifest: BUNDLE_MANIFEST, dir: BUNDLE_DIR, exe: path.join(BUNDLE_DIR, exeName) };
}

/**
 * The bundled Ember runtime for an app root: its absolute command path
 * and whether the bundle is REQUIRED there (the packer's `bundle.json`
 * manifest names it). When the bundle is required the path is returned
 * EVEN IF the file is gone, so the APP-007 boot check fires with the
 * exact delete-the-runtime message; in a dev tree (no manifest) the
 * runtime is used only when it exists.
 *
 * @param {string} appDir the app root (the folder holding package.json)
 * @returns {{emberPath: string|null, required: boolean}}
 */
function bundledEmber(appDir) {
  const layout = bundleLayout();
  const emberPath = path.join(appDir, layout.exe);
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(appDir, layout.manifest), 'utf8'));
    if (manifest && manifest.emberRuntime === layout.dir) return { emberPath, required: true };
  } catch {
    // no manifest, or not ours: fall through to the dev-tree rules
  }
  return { emberPath: fs.existsSync(emberPath) ? emberPath : null, required: false };
}

/**
 * The offline model-weights environment for the bundled runtime (step
 * 13): the weights ride inside the bundle (`<emberRuntime>/models` is
 * a Hugging Face hub cache), so the child must read them from the app
 * folder instead of the network (decision 3-B, story 107).
 *
 * @param {string} emberPath the bundled runtime path (from bundledEmber)
 * @returns {Record<string, string>} extra child environment variables
 */
function bundledChildEnv(emberPath) {
  if (!emberPath) return {};
  return {
    HF_HOME: path.join(path.dirname(emberPath), 'models'),
    HF_HUB_OFFLINE: '1',
    TRANSFORMERS_OFFLINE: '1',
  };
}

/** @returns {string[]} the command argv prefix. */
function resolveEmberCommand(env = process.env, bundling = null) {
  const override = env.EMBER_APP_COMMAND;
  if (typeof override === 'string' && override.trim() !== '') {
    return override.trim().split(/\s+/);
  }
  if (bundling && bundling.emberPath) return [bundling.emberPath];
  return ['ember'];
}

/**
 * APP-007: the bundled Python/Ember must exist at launch. A bare
 * command name (`ember`) rides PATH and cannot be pre-checked; a
 * path-shaped first element can.
 *
 * @param {string[]} argv
 * @returns {{ok: true} | {ok: false, error: info}}
 */
function checkEmberCommand(argv) {
  const exe = argv[0] ?? '';
  if (exe.includes('/') && !fs.existsSync(exe)) {
    return {
      ok: false,
      error: appErrorInfo('APP-007', `${WHERE}.checkEmberCommand`, `the ember program was not found at ${exe}`),
    };
  }
  return { ok: true };
}

/**
 * APP-006: the chosen knowledge base must exist, be a file and carry
 * the SQLite header (the same check any reader would trip over).
 * Whether the file obeys Ember's schema stays the commands' job.
 *
 * @param {string} dbPath
 * @returns {{ok: true} | {ok: false, error: info}}
 */
function validateKnowledgeBasePath(dbPath) {
  if (typeof dbPath !== 'string' || dbPath.trim() === '') {
    return { ok: false, error: appErrorInfo('APP-006', WHERE, 'no knowledge base is chosen yet') };
  }
  let stat;
  try {
    stat = fs.statSync(dbPath);
  } catch {
    return { ok: false, error: appErrorInfo('APP-006', WHERE, `the knowledge base file is not there: ${dbPath}`) };
  }
  if (!stat.isFile()) {
    return { ok: false, error: appErrorInfo('APP-006', WHERE, `the knowledge base path is not a file: ${dbPath}`) };
  }
  let header;
  try {
    const fd = fs.openSync(dbPath, 'r');
    try {
      header = Buffer.alloc(SQLITE_MAGIC.length);
      fs.readSync(fd, header, 0, header.length, 0);
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    return { ok: false, error: appErrorInfo('APP-006', WHERE, `the knowledge base file could not be read: ${dbPath}`) };
  }
  if (!header.equals(SQLITE_MAGIC)) {
    return { ok: false, error: appErrorInfo('APP-006', WHERE, `the chosen file is not an Ember knowledge base: ${dbPath}`) };
  }
  return { ok: true };
}

/**
 * A plain status for the chosen knowledge base, so the screens can
 * tell "no file yet (normal before the first Add)" from "chosen file
 * is not an Ember file (APP-006 state)" WITHOUT calling any command
 * (app step file §1 fact: until the first Add the file may not exist).
 * Reads the file: an edge effect (T2), but the same cheap check
 * `validateKnowledgeBasePath` does.
 *
 * @param {string} dbPath
 * @returns {{path: string, exists: boolean, looksValid: boolean}}
 */
function knowledgeBaseStatus(dbPath) {
  if (typeof dbPath !== 'string' || dbPath.trim() === '') {
    return { path: '', exists: false, looksValid: false };
  }
  let stat = null;
  try {
    stat = fs.statSync(dbPath);
  } catch {
    return { path: dbPath, exists: false, looksValid: false };
  }
  if (!stat.isFile()) return { path: dbPath, exists: false, looksValid: false };
  return { path: dbPath, exists: true, looksValid: validateKnowledgeBasePath(dbPath).ok };
}

module.exports = {
  resolveEmberCommand,
  checkEmberCommand,
  validateKnowledgeBasePath,
  knowledgeBaseStatus,
  bundleLayout,
  bundledEmber,
  bundledChildEnv,
};


'use strict';

/**
 * The shared e2e launcher (step 04): one real Electron shell per
 * scenario, with a throwaway XDG_CONFIG_HOME (settings never touch the
 * developer's own folder) and the fake ember stub speaking the pinned
 * step-04 shapes from a fixture file. The throwaway XDG_STATE_HOME
 * beside it (Batch 2 Chunk 14) keeps engine crash reports in the
 * scenario's own folder too — never in the developer's ~/.local/state.
 *
 * `withDb: true` (default) passes EMBER_APP_DB, so the app boots
 * straight into Home with a valid knowledge base. `withDb: false` and
 * a fresh config produce the FIRST RUN screen (no knowledge base is
 * chosen yet).
 */

const { _electron } = require('playwright');
const path = require('node:path');
const { APP_ROOT, FAKE_EMBER } = require('../../util');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'steps-04.json');

/**
 * @param {object} options
 * @param {string} options.workDir throwaway directory (created by the caller)
 * @param {string} [options.mode] FAKE_MODE (default 'app')
 * @param {boolean} [options.withDb] EMBER_APP_DB override (default true)
 * @param {string} [options.fixture] the fake-ember fixture file
 * @param {object} [options.extraEnv] extra env entries (plain object,
 *   merged after the defaults) — a scenario can set e.g. FAKE_APP_FAIL
 *   or FAKE_SPAWN_LOG without touching the other callers.
 * @returns {Promise<{app: object, workDir: string, kbPath: string}>}
 */
async function launchShell({ workDir, mode = 'app', withDb = true, fixture = FIXTURE, extraEnv = {} }) {
  const configDir = path.join(workDir, 'config');
  const stateDir = path.join(workDir, 'state');
  const { mkdirSync, writeFileSync } = require('node:fs');
  mkdirSync(configDir, { recursive: true });
  mkdirSync(stateDir, { recursive: true });
  const kbPath = path.join(workDir, 'kb.db');
  // A throwaway "knowledge base" with the SQLite header: the fake
  // ember never reads it, but the APP-006 guard may.
  writeFileSync(kbPath, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(3000, 0)]));

  const env = {
    ...process.env,
    XDG_CONFIG_HOME: configDir,
    XDG_STATE_HOME: stateDir,
    EMBER_APP_COMMAND: `node ${FAKE_EMBER}`,
    FAKE_MODE: mode,
    FAKE_FIXTURE: fixture,
    ...extraEnv,
  };
  if (withDb) env.EMBER_APP_DB = kbPath;

  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  return { app, workDir, kbPath, configDir, stateDir };
}

/** The exact settings.json the store would write (schema 1). */
function settingsJson(kbPath, lastPane = 'home') {
  return `${JSON.stringify(
    {
      schema: 1,
      textSize: 'default',
      colourTheme: 'system',
      quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' },
      menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
      menuHidden: [],
      lastPane,
      knowledgeBasePath: kbPath,
    },
    null,
    2,
  )}\n`;
}

/**
 * Pre-seed settings BEFORE a launch: with a knowledge-base path that
 * does not exist yet, the app boots to Home's pre-Add empty state.
 */
function seedSettings(configDir, kbPath) {
  const { mkdirSync, writeFileSync } = require('node:fs');
  const userData = path.join(configDir, 'ember-app');
  mkdirSync(userData, { recursive: true });
  writeFileSync(path.join(userData, 'settings.json'), settingsJson(kbPath));
}

module.exports = { launchShell, FIXTURE, seedSettings };

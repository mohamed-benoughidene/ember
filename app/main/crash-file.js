'use strict';

/**
 * The crash-folder rule on the app side (Spec-Batch2, decision N4).
 *
 * When the engine dies with EMBER-000 it writes a crash file under
 * `$XDG_STATE_HOME/ember/crashes` (default `~/.local/state/ember/
 * crashes` when the variable is unset). The engine children inherit
 * the app's environment, so the app resolves the SAME folder with the
 * SAME rule and can find the file again (Chunk 13: Copy crash report
 * / Show file).
 *
 * Pure path rules (T1): strings in, strings out; no reading, no
 * listing, no creating of folders happens here.
 */

const os = require('node:os');
const path = require('node:path');

const EMBER_DIR = 'ember';
const CRASH_DIR = 'crashes';
const CRASH_SUFFIX = '.txt';

/**
 * The folder that holds crash files, by the N4 XDG rule:
 * `$XDG_STATE_HOME/ember/crashes`, default
 * `~/.local/state/ember/crashes`. An empty variable counts as unset.
 */
function crashDir() {
  const stateHome =
    typeof process.env.XDG_STATE_HOME === 'string' && process.env.XDG_STATE_HOME.trim() !== ''
      ? process.env.XDG_STATE_HOME
      : path.join(os.homedir(), '.local', 'state');
  return path.join(stateHome, EMBER_DIR, CRASH_DIR);
}

/**
 * The full path of one crash report file: `<crashDir()>/<crashId>.txt`.
 * Refuses (throws on) a crash id that could climb out of the folder —
 * anything containing `/` (a path separator) or a `..` segment. The id
 * comes off an engine error line, so it is never trusted blindly.
 *
 * @param {string} crashId e.g. "20261101T120000Z-a1b2c3"
 * @returns {string} the crash file's full path
 */
function crashPath(crashId) {
  if (typeof crashId !== 'string' || crashId.trim() === '') {
    throw new Error(`refused: a crash id is required, got ${JSON.stringify(crashId)}`);
  }
  if (crashId.includes('/') || crashId.includes('\\') || crashId.split(path.sep).includes('..')) {
    throw new Error(`refused: a crash id may not contain / or .. — got ${JSON.stringify(crashId)}`);
  }
  return path.join(crashDir(), `${crashId}${CRASH_SUFFIX}`);
}

module.exports = { crashDir, crashPath };

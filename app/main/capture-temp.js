'use strict';

/**
 * The pasted-text temp file (app step 05, step file §1 fact).
 *
 * `capture` without `--file` reads ALL of stdin, so stdin cannot carry
 * the confirm answers too. The app therefore writes the pasted text to
 * a temp file in the user-data folder and runs
 * `capture --file <temp> --confirm json --db <kb>`; the file is deleted
 * when the session ends, and anything left by a crash is wiped at the
 * next start (cleanStaleTempFiles, called once at registration).
 *
 * Plain Node fs edges (T2); the naming rule is pure.
 */

const fs = require('node:fs');
const path = require('node:path');
const { appErrorInfo } = require('../shared/errors');

const TEMP_PREFIX = 'add-text-';
const TEMP_SUFFIX = '.txt';

function tempName(now = Date.now, random = Math.random) {
  return `${TEMP_PREFIX}${now()}-${String(Math.floor(random() * 1_000_000)).padStart(6, '0')}${TEMP_SUFFIX}`;
}

/**
 * Write the pasted text to one temp file in the user-data folder.
 * Owner-only permissions (0600): it is the user's own draft.
 */
function writeTempText(userDataPath, text, { name = tempName() } = {}) {
  const filePath = path.join(userDataPath, name);
  try {
    fs.writeFileSync(filePath, text, { encoding: 'utf8', mode: 0o600 });
  } catch (err) {
    return {
      ok: false,
      error: appErrorInfo('APP-000', 'main.capture-temp', `the pasted text could not be kept in the app's working folder: ${err instanceof Error ? err.message : String(err)}`),
    };
  }
  return { ok: true, path: filePath };
}

/** Delete one temp file; missing is fine, never throws. */
function removeTempFile(filePath) {
  if (typeof filePath !== 'string' || filePath === '') return;
  try {
    fs.unlinkSync(filePath);
  } catch {
    /* already gone */
  }
}

/**
 * Wipe temp files a crash left behind (step file §1: "also on a crash
 * at next start"). Only touches this module's own add-text-*.txt names.
 *
 * @returns {number} how many leftovers were removed
 */
function cleanStaleTempFiles(userDataPath) {
  let names = [];
  try {
    names = fs.readdirSync(userDataPath);
  } catch {
    return 0;
  }
  let removed = 0;
  for (const name of names) {
    if (!name.startsWith(TEMP_PREFIX) || !name.endsWith(TEMP_SUFFIX)) continue;
    try {
      fs.unlinkSync(path.join(userDataPath, name));
      removed += 1;
    } catch {
      /* a file that cannot be removed is not ours to fight over */
    }
  }
  return removed;
}

module.exports = { TEMP_PREFIX, TEMP_SUFFIX, tempName, writeTempText, removeTempFile, cleanStaleTempFiles };

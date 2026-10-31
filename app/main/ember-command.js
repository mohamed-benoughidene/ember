'use strict';

/**
 * Where the app finds the `ember` command, and whether the chosen
 * knowledge-base file is usable (APP-006 / APP-007).
 *
 * Step 02: the command comes from the `EMBER_APP_COMMAND` environment
 * override (space-separated, e.g. "/path/.venv/bin/ember" or
 * "node /path/fake-ember.js"); the default is plain `ember` on PATH.
 * The bundled embedder location is decided at packaging (step 13).
 */

const fs = require('node:fs');
const { appErrorInfo } = require('../shared/errors');

const WHERE = 'main.ember-command';
const SQLITE_MAGIC = Buffer.from('SQLite format 3\x00');

/** @returns {string[]} the command argv prefix. */
function resolveEmberCommand(env = process.env) {
  const override = env.EMBER_APP_COMMAND;
  if (typeof override === 'string' && override.trim() !== '') {
    return override.trim().split(/\s+/);
  }
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

module.exports = { resolveEmberCommand, checkEmberCommand, validateKnowledgeBasePath, knowledgeBaseStatus };


'use strict';

/**
 * The key store (interface-app-plan.md §5.4, maintainer decision 4-A).
 *
 * The AI key lives in the OS secure storage through Electron's
 * `safeStorage` — the encrypted bytes in a small file in the user-data
 * folder. On the founder's machine the backend is kwallet6 (a real
 * keyring; spike findings, check 4). When the backend is weak or
 * missing (`basic_text` or none), the store REFUSES to save (APP-003)
 * and offers a session-only key held in memory — the key file is
 * never written in plain text. Remove is a real delete (story 89).
 *
 * The key leaves the main process ONLY as the child's
 * EMBER_AI_API_KEY environment variable (the bridge client's job) and
 * NEVER into a log, an error or the ledger (I20/I21).
 */

const fs = require('node:fs');
const path = require('node:path');
const { appErrorInfo } = require('../shared/errors');

const WHERE = 'main.key-store';

/**
 * Decide whether the safeStorage backend is one we trust. Only real
 * OS keyrings pass; `basic_text` (a built-in obscuring key, not a
 * real keyring) and an absent backend fail.
 *
 * @param {object|null} safeStorage Electron's safeStorage (or a fake)
 * @returns {boolean}
 */
function isBackendTrusted(safeStorage) {
  if (!safeStorage || typeof safeStorage.encryptString !== 'function') return false;
  if (typeof safeStorage.decryptString !== 'function') return false;
  const backend =
    typeof safeStorage.getSelectedStorageBackend === 'function'
      ? safeStorage.getSelectedStorageBackend()
      : null;
  if (typeof backend !== 'string' || backend === '') return false;
  return backend !== 'basic_text';
}

/**
 * @param {object} options
 * @param {string} options.file absolute path of the encrypted key file
 * @param {object} options.safeStorage Electron's safeStorage (or a fake with
 *   the same four methods)
 * @param {typeof import('node:fs')} [options.fsImpl] test seam
 */
function createKeyStore(options) {
  const { file, safeStorage, fsImpl = fs } = options;
  let sessionKey = null; // the "use for this session only" fallback

  /**
   * @returns {{stored: boolean, sessionOnly: boolean, backend: string|null}}
   *   backend is the OS backend name for the status screen; it is not
   *   a secret.
   */
  function status() {
    return {
      stored: fsImpl.existsSync(file),
      sessionOnly: sessionKey !== null,
      backend:
        typeof safeStorage?.getSelectedStorageBackend === 'function'
          ? safeStorage.getSelectedStorageBackend()
          : null,
    };
  }

  /** @returns {string|null} the key, from the file or the session-only slot. */
  function get() {
    if (sessionKey !== null) return sessionKey;
    let raw;
    try {
      raw = fsImpl.readFileSync(file);
    } catch {
      return null; // no key stored yet
    }
    try {
      const decrypted = safeStorage.decryptString(Buffer.from(raw.toString('utf8'), 'base64'));
      return decrypted === '' ? null : decrypted;
    } catch {
      // Wrong backend or corrupt bytes: treat as absent, never crash,
      // never echo the bytes anywhere. The user re-enters the key.
      return null;
    }
  }

  /**
   * Store the key encrypted. Refuses (APP-003) when the backend is
   * weak or missing — the caller offers "use for this session only".
   *
   * @param {string} key
   * @returns {{ok: true} | {ok: false, error: info}}
   */
  function set(key) {
    if (typeof key !== 'string' || key === '') {
      return { ok: false, error: appErrorInfo('APP-003', `${WHERE}.set`, 'the key text was empty') };
    }
    if (!isBackendTrusted(safeStorage)) {
      return {
        ok: false,
        error: appErrorInfo('APP-003', `${WHERE}.set`, 'the operating system keyring is not available, so the key was NOT saved'),
      };
    }
    try {
      const encrypted = safeStorage.encryptString(key);
      fsImpl.mkdirSync(path.dirname(file), { recursive: true });
      fsImpl.writeFileSync(file, Buffer.from(encrypted).toString('base64'), { mode: 0o600 });
      sessionKey = null; // a saved key replaces any session-only one
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-003', `${WHERE}.set`, `the key could not be saved to the keyring (${err instanceof Error ? err.message : 'unknown error'})`),
      };
    }
  }

  /**
   * Keep the key for this session only (the APP-003 offer). Nothing
   * touches the disk.
   *
   * @param {string} key
   * @returns {{ok: true} | {ok: false, error: info}}
   */
  function setSessionOnly(key) {
    if (typeof key !== 'string' || key === '') {
      return { ok: false, error: appErrorInfo('APP-003', `${WHERE}.setSessionOnly`, 'the key text was empty') };
    }
    sessionKey = key;
    return { ok: true };
  }

  /** Remove the saved key (and any session-only one). Careful action, story 89. */
  function remove() {
    sessionKey = null;
    try {
      fsImpl.unlinkSync(file);
    } catch (err) {
      if (err && err.code === 'ENOENT') return { ok: true };
      return {
        ok: false,
        error: appErrorInfo('APP-003', `${WHERE}.remove`, `the key file could not be removed (${err instanceof Error ? err.message : 'unknown error'})`),
      };
    }
    return { ok: true };
  }

  return { status, get, set, setSessionOnly, remove };
}

module.exports = { createKeyStore, isBackendTrusted };

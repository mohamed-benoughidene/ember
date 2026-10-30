'use strict';

/**
 * The APP- error namespace (interface-app-plan.md §6).
 *
 * Stable code numbers, never reused (I17). Every error carries
 * `code`, `name`, `where` (module.function) and `detail`; none ever
 * carries a secret (the AI key must never reach here — I20/I21).
 */

const APP_CODES = Object.freeze({
  APP_000: 'APP-000',
  APP_001: 'APP-001',
  APP_002: 'APP-002',
  APP_003: 'APP-003',
  APP_004: 'APP-004',
  APP_005: 'APP-005',
  APP_006: 'APP-006',
  APP_007: 'APP-007',
  APP_008: 'APP-008',
});

/**
 * The named error the app raises and shows. `detail` is a plain
 * sentence; it may quote the bridge's own (already public) error text.
 */
class AppError extends Error {
  /**
   * @param {string} code one of APP_CODES
   * @param {string} name the stable name from plan §6
   * @param {string} where "module.function"
   * @param {string} detail plain sentence, no secrets
   */
  constructor(code, name, where, detail) {
    super(`${code} ${name} | ${where} | ${detail}`);
    this.name = name;
    this.code = code;
    this.where = where;
    this.detail = detail;
  }

  /** The plain shape sent to the renderer and used in tests. */
  toInfo() {
    return { code: this.code, name: this.name, where: this.where, detail: this.detail };
  }
}

const NAMES = Object.freeze({
  'APP-000': 'AppError',
  'APP-001': 'BridgeSpawnFailed',
  'APP-002': 'BridgeOutputInvalid',
  'APP-003': 'KeyStoreUnavailable',
  'APP-004': 'SettingsUnreadable',
  'APP-005': 'ShortcutRegistrationFailed',
  'APP-006': 'KnowledgeBaseMissing',
  'APP-007': 'RuntimeMissing',
  'APP-008': 'BridgeTimeout',
});

/** Build the plain info shape without throwing (for fakes and notices). */
function appErrorInfo(code, where, detail) {
  if (!(code in NAMES)) {
    throw new TypeError(`unknown APP code: ${code}`);
  }
  return { code, name: NAMES[code], where, detail };
}

/** Wrap plain info into a real AppError. */
function asAppError(info) {
  return new AppError(info.code, info.name, info.where, info.detail);
}

module.exports = { APP_CODES, NAMES, AppError, appErrorInfo, asAppError };

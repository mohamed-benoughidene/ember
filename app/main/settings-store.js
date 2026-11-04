'use strict';

/**
 * The settings store (interface-app-plan.md §5.3).
 *
 * One JSON file in Electron's user-data folder. Atomic write: write a
 * temp file, then rename over the target. An unreadable / corrupt file
 * gives defaults and an APP-004 notice — never a crash.
 *
 * I13: settings load once at boot and are passed down; the renderer
 * only sees them through named IPC calls. The save ends quietly
 * ("Saved", spec story 81) — the renderer owns the words; this store
 * just reports a successful save.
 */

const fs = require('node:fs');
const path = require('node:path');
const { appErrorInfo } = require('../shared/errors');
const { DEFAULTS, normalizeSettings } = require('../shared/settings-schema');

const WHERE = 'main.settings-store';

/**
 * @param {object} options
 * @param {string} options.file absolute path of settings.json
 * @param {typeof import('node:fs')} [options.fsImpl] test seam
 */
function createSettingsStore(options) {
  const { file, fsImpl = fs } = options;

  /**
   * @returns {{settings: object, notice: {code,name,where,detail}|null}}
   */
  function load() {
    let raw;
    try {
      raw = fsImpl.readFileSync(file, 'utf8');
    } catch (err) {
      if (err && err.code === 'ENOENT') {
        // First run: no file yet. Defaults, but not an APP-004 notice.
        return { settings: structuredClone(DEFAULTS), notice: null };
      }
      return {
        settings: structuredClone(DEFAULTS),
        notice: appErrorInfo('APP-004', `${WHERE}.load`, `the settings file could not be read (${describe(err)}); defaults are in use`),
      };
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return {
        settings: structuredClone(DEFAULTS),
        notice: appErrorInfo('APP-004', `${WHERE}.load`, 'the settings file is corrupt; defaults are in use. Saving will rewrite it.'),
      };
    }
    const { settings, schemaChanged } = normalizeSettings(parsed);
    if (schemaChanged) {
      return {
        settings,
        notice: appErrorInfo('APP-004', `${WHERE}.load`, 'the settings file was written by another version; defaults are in use'),
      };
    }
    return { settings, notice: null };
  }

  /**
   * Merge a patch over the current settings, validate once, and write
   * atomically (temp file + rename, D5/D6).
   *
   * @param {object} patch plain object of field -> value
   * @returns {{settings: object, ok: true} | {ok: false, error: info}}
   */
  function save(patch) {
    const { settings } = load();
    const { settings: merged } = normalizeSettings({ ...settings, ...patch, schema: DEFAULTS.schema });
    const dir = path.dirname(file);
    try {
      fsImpl.mkdirSync(dir, { recursive: true });
      const temp = `${file}.tmp-${process.pid}`;
      fsImpl.writeFileSync(temp, `${JSON.stringify(merged, null, 2)}\n`, 'utf8');
      fsImpl.renameSync(temp, file);
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-004', `${WHERE}.save`, `the settings file could not be written (${describe(err)})`),
      };
    }
    return { ok: true, settings: merged };
  }

  return { load, save };
}

function describe(err) {
  return err instanceof Error ? err.message : String(err);
}

module.exports = { createSettingsStore };

'use strict';

/**
 * The IPC surface: the ONE narrow, named call list the renderer may
 * use (plan §4 rule, B5). Every handler validates its inputs once at
 * this edge (I9/D4) and returns plain objects or plain error info
 * ({code, name, where, detail}) — never a thrown error, never the key.
 *
 * Step 04 extended the list from eight to fifteen named channels: the
 * read commands Home and Look up use (list-items with its filters,
 * current-state, topic-search, show-item, history), the sweep dry-run
 * pending count (maintain --dry-run), and the knowledge-base status /
 * chooser calls first run needs. The full list is pinned by
 * test/preload-allowlist.test.js.
 */

const path = require('node:path');
const { createBridgeClient } = require('./bridge-client');
const {
  validateKnowledgeBasePath,
  knowledgeBaseStatus,
} = require('./ember-command');
const { appErrorInfo } = require('../shared/errors');
const { checkKeyShape } = require('../shared/key-shape.mjs');
const {
  listItemsArgs,
  topicSearchArgs,
  showItemArgs,
  historyArgs,
} = require('./command-args');
// App step 09 (Keep safe) — added as its own line; see the end-of-file
// handler block below and test/preload-allowlist.test.js (channel count).
const { runDbCheck } = require('./db-check-runner');
const { validateChosenPath } = require('../shared/keep-safe-paths.mjs');

const WHERE = 'main.ipc';

/**
 * @param {object} options
 * @param {object} options.ipcMain Electron's ipcMain (or a fake)
 * @param {{load, save}} options.settingsStore
 * @param {{status, get, set, setSessionOnly, remove}} options.keyStore
 * @param {() => string|null} options.apiKeyProvider
 * @param {string|null} options.errorPattern shared regex source
 * @param {string[]} options.emberCommand resolved command prefix
 * @param {string|null} [options.dbOverride] EMBER_APP_DB override
 * @param {string} options.appVersion for the window
 * @param {string} options.userDataPath the user-data folder (the default
 *   knowledge-base location proposal lives there)
 * @param {{code,name,where,detail}|null} [options.bootNotice] APP-007 etc,
 *   raised once at boot (main.js) and shown once at the top of the app
 * @param {() => {path: string}|null} [options.kbChooser] the open-file
 *   dialog adapter (Electron dialog in production, a fake in tests)
 * @param {(ask: {kind: string, defaultName: string}) => {path: string}|null}
 *   [options.saveChooser] the save-file dialog adapter (step 09; the
 *   `where to save` side of backup/export; a fake in tests)
 * @param {(name: string, args: string[]) => void} [options.onCommand] test seam
 */
function registerIpcHandlers(options) {
  const {
    ipcMain,
    settingsStore,
    keyStore,
    apiKeyProvider,
    errorPattern,
    emberCommand,
    dbOverride = null,
    appVersion,
    userDataPath,
    bootNotice = null,
    kbChooser = () => null,
    saveChooser = () => null,
    onCommand = () => {},
  } = options;

  let cachedClient = null;
  let cachedDbPath = null;

  /** One bridge client per knowledge-base path (one child per call inside). */
  function clientFor(dbPath) {
    if (cachedClient === null || cachedDbPath !== dbPath) {
      cachedClient = createBridgeClient({
        emberCommand,
        dbPath,
        errorPattern,
        apiKeyProvider,
      });
      cachedDbPath = dbPath;
    }
    return cachedClient;
  }

  function dbPath() {
    if (dbOverride !== null) return dbOverride;
    return settingsStore.load().settings.knowledgeBasePath;
  }

  /**
   * Read commands refuse to spawn while the knowledge base is not there
   * or is not an Ember file: the screens show the empty state or the
   * APP-006 state, no child process is started (app step §1).
   */
  function guardKnowledgeBase() {
    return validateKnowledgeBasePath(dbPath());
  }

  const handlers = {
    'ember:ping': () => 'pong',

    'ember:getState': () => {
      const { settings, notice } = settingsStore.load();
      return {
        appVersion,
        settings,
        settingsNotice: notice,
        bootNotice,
        defaultKbPath: path.join(userDataPath, 'ember.db'),
        effectiveKbPath: dbPath(),
      };
    },

    'ember:saveSettings': (patch) => {
      if (typeof patch !== 'object' || patch === null || Array.isArray(patch)) {
        return { ok: false, error: appErrorInfo('APP-004', `${WHERE}.saveSettings`, 'the settings change was not a plain object') };
      }
      return settingsStore.save(patch);
    },

    'ember:kbStatus': () => knowledgeBaseStatus(dbPath()),

    'ember:pickKnowledgeBaseFile': () => {
      const chosen = kbChooser();
      if (chosen === null || chosen.path === null) return { ok: false, cancelled: true };
      const check = validateKnowledgeBasePath(chosen.path);
      if (!check.ok) return { ok: false, error: check.error };
      return { ok: true, path: chosen.path };
    },

    'ember:listItems': async (payload) => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      const page = typeof payload === 'object' && payload !== null ? payload : {};
      const args = listItemsArgs({
        status: page.status ?? null,
        type: page.type ?? null,
        limit: page.limit ?? null,
        offset: page.offset ?? null,
      });
      onCommand('list-items', args);
      return clientFor(dbPath()).runCommand('list-items', args);
    },

    'ember:topicSearch': async (payload) => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      const page = typeof payload === 'object' && payload !== null ? payload : {};
      const args = topicSearchArgs({
        query: page.query,
        status: page.status ?? null,
        type: page.type ?? null,
        limit: page.limit ?? null,
      });
      onCommand('topic-search', args);
      return clientFor(dbPath()).runCommand('topic-search', args);
    },

    'ember:showItem': async (payload) => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      const args = showItemArgs(typeof payload === 'object' && payload !== null ? payload.item : null);
      onCommand('show-item', args);
      return clientFor(dbPath()).runCommand('show-item', args);
    },

    'ember:history': async (payload) => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      const page = typeof payload === 'object' && payload !== null ? payload : {};
      const args = historyArgs({
        item: page.item ?? null,
        limit: page.limit ?? null,
        offset: page.offset ?? null,
        since: page.since ?? null,
      });
      onCommand('history', args);
      return clientFor(dbPath()).runCommand('history', args);
    },

    'ember:currentState': async () => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      onCommand('current-state', []);
      return clientFor(dbPath()).runCommand('current-state', []);
    },

    /**
     * The sweep pending count for the Home attention block:
     * `maintain --dry-run` (writes nothing; the bridge client always
     * runs sessions with `--confirm json --format json`, and in that
     * mode the dry-run document rides ONE message event, as the pinned
     * FORMAT_JSON_KEYS shape). D3: the count comes from the command's
     * own `changes` list, never recomputed.
     */
    'ember:maintainDryRun': async () => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      onCommand('maintain', ['--dry-run']);
      const session = clientFor(dbPath()).runConfirmSession('maintain', ['--dry-run']);
      return new Promise((resolve) => {
        let document = null;
        let failure = null;
        session.on('event', (event) => {
          if (event.event !== 'message' || typeof event.text !== 'string') return;
          try {
            const parsed = JSON.parse(event.text);
            if (parsed && typeof parsed === 'object' && parsed.command === 'maintain' && Array.isArray(parsed.changes)) {
              document = parsed;
            }
          } catch {
            /* short information lines (paths etc.) are not the document */
          }
        });
        session.on('error', (info) => {
          failure = info;
        });
        session.on('exit', () => {
          if (document !== null) return resolve({ ok: true, pending: document.changes.length });
          if (failure !== null) return resolve({ ok: false, error: failure });
          resolve({
            ok: false,
            error: appErrorInfo('APP-002', `${WHERE}.maintainDryRun`, 'the sweep preview ended without a report document'),
          });
        });
      });
    },

    'ember:keyStatus': () => keyStore.status(),

    'ember:setKey': (key) => {
      if (typeof key !== 'string') {
        return { ok: false, error: appErrorInfo('APP-003', `${WHERE}.setKey`, 'the key text was not text') };
      }
      // Bridge decision D3 / app decision 5-A: the shape-and-length
      // check at save. The real test happens at the first Add.
      const shape = checkKeyShape(key);
      if (!shape.ok) {
        return {
          ok: false,
          error: appErrorInfo('APP-003', `${WHERE}.setKey`, `the key was not saved: ${keyShapeWords(shape.reason)}`),
        };
      }
      return keyStore.set(key);
    },

    'ember:setSessionKey': (key) => {
      if (typeof key !== 'string') {
        return { ok: false, error: appErrorInfo('APP-003', `${WHERE}.setSessionKey`, 'the key text was not text') };
      }
      const shape = checkKeyShape(key);
      if (!shape.ok) {
        return {
          ok: false,
          error: appErrorInfo('APP-003', `${WHERE}.setSessionKey`, `the key was not kept: ${keyShapeWords(shape.reason)}`),
        };
      }
      return keyStore.setSessionOnly(key);
    },

    'ember:removeKey': () => keyStore.remove(),

    /* =================================================================
     * APP STEP 09 (Keep safe) — added at the END of the registration
     * list as this step's own bracketed block (ticket A38). New
     * channels are pinned by test/preload-allowlist.test.js and the
     * e2e smoke allowlist. Nothing above is moved or reformatted.
     * Backup / export spread no rules here (B3): the engine refuses
     * self-overwrite (BACKUP-003 / EXPORT-002); the app only checks
     * the SHAPE of a chosen path before starting any child (I9).
     * ================================================================= */

    /**
     * The "where should it go" dialog for backup and export.
     * payload {kind: 'backup'|'export', defaultName}. Cancelled ->
     * {ok:false, cancelled:true}; the screen then changes nothing.
     */
    'ember:pickSaveFile': (payload) => {
      const ask = typeof payload === 'object' && payload !== null ? payload : {};
      if (ask.kind !== 'backup' && ask.kind !== 'export') {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.pickSaveFile`, 'the save dialog was asked for an unknown kind of file') };
      }
      const chosen = saveChooser({ kind: ask.kind, defaultName: typeof ask.defaultName === 'string' ? ask.defaultName : '' });
      if (chosen === null || typeof chosen.path !== 'string' || chosen.path === '') return { ok: false, cancelled: true };
      return { ok: true, path: chosen.path };
    },

    /**
     * `ember backup TARGET --db <kb> --format json` (story 70). The
     * engine's report {path, schema_version, item_count, rotated} is
     * D3 data shown as-is. A refusal (BACKUP-001..004) comes back as
     * plain error info — the engine's words, story 72/77.
     */
    'ember:backupTo': async (payload) => {
      const targetPath = typeof payload === 'object' && payload !== null && typeof payload.targetPath === 'string' ? payload.targetPath.trim() : '';
      const shape = validateChosenPath(targetPath);
      if (!shape.ok) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.backupTo`, `the chosen backup location is not a usable file path (${shape.reason})`) };
      }
      onCommand('backup', [targetPath]);
      const result = await clientFor(dbPath()).runCommand('backup', [targetPath]);
      if (!result.ok) return result;
      const summary = result.data && typeof result.data === 'object' ? result.data.summary : null;
      if (
        summary === null ||
        typeof summary !== 'object' ||
        typeof summary.path !== 'string' ||
        !Number.isInteger(summary.schema_version) ||
        !Number.isInteger(summary.item_count)
      ) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.backupTo`, 'the backup did not report its verified copy') };
      }
      return { ok: true, data: { path: summary.path, schemaVersion: summary.schema_version, itemCount: summary.item_count, rotated: summary.rotated ?? null } };
    },

    /**
     * `ember export --out FILE --db <kb>` (stories 73-74). Exit-code
     * result only: the app reads NO export JSON (step §1) — the file
     * itself is the artifact, for any editor.
     */
    'ember:exportTo': async (payload) => {
      const outPath = typeof payload === 'object' && payload !== null && typeof payload.outPath === 'string' ? payload.outPath.trim() : '';
      const shape = validateChosenPath(outPath);
      if (!shape.ok) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.exportTo`, `the chosen export location is not a usable file path (${shape.reason})`) };
      }
      onCommand('export', ['--out', outPath]);
      const result = await clientFor(dbPath()).runCommand('export', ['--out', outPath]);
      if (!result.ok) return result;
      return { ok: true, data: { outPath } };
    },

    /**
     * `ember db-check --db <kb> --format json` (story 75). The report
     * (OK / DRIFT / UNREADABLE + lines) is data even on exit 1 — see
     * main/db-check-runner.js. NO knowledge-base guard: a broken or
     * missing file is exactly what the check reports.
     * payload {dbPath?}: an explicit path is allowed because the
     * open-a-different-file flow must check the CHOSEN file before the
     * setting changes (step §1, story 76).
     */
    'ember:dbCheck': async (payload) => {
      const asked = typeof payload === 'object' && payload !== null ? payload : {};
      const target = typeof asked.dbPath === 'string' && asked.dbPath.trim() !== '' ? asked.dbPath.trim() : dbPath();
      if (target === '') {
        return { ok: false, error: appErrorInfo('APP-006', `${WHERE}.dbCheck`, 'no knowledge base is chosen yet') };
      }
      onCommand('db-check', []);
      return runDbCheck({ emberCommand, errorPattern, dbPath: target });
    },

    /**
     * Open a DIFFERENT knowledge base file (story 76; restore is not a
     * command by design — GLOSSARY). The step §1 order, exactly:
     * the file must exist and be an Ember file (APP-006), then it must
     * pass `db-check` (UNREADABLE -> APP-006), and only THEN does the
     * setting change. An older (v12) file passes: db-check has no
     * floor for it, and the first write command migrates it with a
     * safety copy (Undo L2 §5.6). The confirmation naming the file is
     * the screen's work, BEFORE this handler runs.
     */
    'ember:switchKnowledgeBase': async (payload) => {
      const chosen = typeof payload === 'object' && payload !== null && typeof payload.path === 'string' ? payload.path.trim() : '';
      const kbCheck = validateKnowledgeBasePath(chosen);
      if (!kbCheck.ok) return kbCheck;
      onCommand('db-check', []);
      const report = await runDbCheck({ emberCommand, errorPattern, dbPath: chosen });
      if (!report.ok) return report;
      if (report.data.result === 'UNREADABLE') {
        return {
          ok: false,
          error: appErrorInfo('APP-006', `${WHERE}.switchKnowledgeBase`, 'the chosen file could not be read as an Ember knowledge base'),
        };
      }
      const saved = settingsStore.save({ knowledgeBasePath: chosen });
      if (!saved || saved.ok !== true) {
        return saved && saved.error
          ? saved
          : { ok: false, error: appErrorInfo('APP-004', `${WHERE}.switchKnowledgeBase`, 'the choice could not be saved to the settings file') };
      }
      return { ok: true, data: { path: chosen, check: { result: report.data.result, detail: report.data.detail, lines: report.data.lines } } };
    },
  };

  const names = Object.keys(handlers);
  for (const name of names) {
    ipcMain.handle(name, async (_event, payload) => {
      try {
        return await handlers[name](payload);
      } catch (err) {
        // Never leak a raw error (which could carry paths and values)
        // to the renderer: turn it into a named APP- error.
        return {
          ok: false,
          error: appErrorInfo('APP-002', `${WHERE}.${name}`, `the call failed unexpectedly: ${err instanceof Error ? err.message : 'unknown error'}`),
        };
      }
    });
  }

  return { names };
}

/** The plain words for a shape refusal (shared rule, one wording). */
function keyShapeWords(reason) {
  if (reason === 'empty') return 'the key box was empty';
  if (reason === 'whitespace') return 'a key is one unbroken line of characters; this one had a space or line break inside';
  return `this key is too short; a real key has at least 20 characters (no spaces)`;
}

module.exports = { registerIpcHandlers };

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
const { fixActionArgs, undoPlanArgs } = require('./fix-close-args');

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

    // --- app step 07 (Fix and close) — new channels appended at the
    // --- END of the registration list (additive; the allowlist test
    // --- pins the full list).

    /**
     * One Fix and close write or preview, exactly as the contract
     * table pins it: the action names the command; the argv comes
     * ONLY from main/fix-close-args.js (bad values never reach a child
     * process). Writes run with the same write-timeout/never-retry
     * rule as every other write (runCommand).
     */
    'ember:fixAction': async (payload) => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      const { action, args: payloadArgs = {} } = typeof payload === 'object' && payload !== null ? payload : {};
      let args;
      try {
        args = fixActionArgs(action, payloadArgs);
      } catch (err) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.fixAction`, err instanceof Error ? err.message : 'unknown error') };
      }
      onCommand(action, args);
      return clientFor(dbPath()).runCommand(action, args);
    },

    /**
     * The undo/redo LABEL derivation read (stories 113, 121): `undo
     * --dry-run --format json` (a read-shaped call: it writes zero
     * rows, D3). The parsed MAINTAIN refusals ride out as {ok:false,
     * error} so the screen can show its honest disabled words.
     */
    'ember:undoPlan': async (payload) => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      const command = typeof payload === 'object' && payload !== null ? payload.command : null;
      let args;
      try {
        args = undoPlanArgs(command);
      } catch (err) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.undoPlan`, err instanceof Error ? err.message : 'unknown error') };
      }
      onCommand(command, args);
      return clientFor(dbPath()).runCommand(command, args);
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

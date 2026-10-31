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
const { maintainDocumentFromMessage } = require('../shared/maintain-words.mjs');
const {
  listItemsArgs,
  topicSearchArgs,
  showItemArgs,
  historyArgs,
} = require('./command-args');
// App 05 (ticket A34): the Add session channels and the pasted-text
// temp file, registered in the bracketed block at the end of this list.
const { wireAddChannels } = require('./add-session');
const { writeTempText, removeTempFile, cleanStaleTempFiles } = require('./capture-temp');
// App step 09 (Keep safe) — added as its own line; see the end-of-file
// handler block below and test/preload-allowlist.test.js (channel count).
const { runDbCheck } = require('./db-check-runner');
const { validateChosenPath } = require('../shared/keep-safe-paths.mjs');
// App step 07 (Fix and close): the argv builders for its two channels.
const { fixActionArgs, undoPlanArgs } = require('./fix-close-args');
// App step 06 (Link items): its session channels, registered in the
// bracketed block at the end of the list (see the allowlist test).
const { wireRelateChannels, RELATE_SESSION_IDLE_MS } = require('./relate-session');

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
 * @param {((accelerator: string) => {ok: boolean, error?: object})|null}
 *   [options.shortcutRegistrar] the Settings pane's shortcut re-registration
 *   seam (app 10; null keeps the step-02/04 behaviour and the pane's honest
 *   "not available in this build" words)
 * @param {(() => string|null)} [options.keyHintProvider] the masked key hint
 *   (app 10; the key's LAST FOUR characters, never the key)
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
    // [app 10] Settings panes: the shortcut re-registration seam
    // (stories 85-86) and the masked key hint provider. Both default
    // to null so the step-02/04 wirings and tests stay untouched.
    shortcutRegistrar = null,
    keyHintProvider = null,
    bootNotice = null,
    kbChooser = () => null,
    saveChooser = () => null,
    onCommand = () => {},
    /* --- App 08 (Clean up): push stream for the sweep session (additive; ticket A37). --- */
    sweepNotify = () => {},
  } = options;

  let cachedClient = null;
  let cachedDbPath = null;
  /* App 06: the relate client lives beside the shared one (its longer
     session idle limit, story 45); both are one-child-per-call. */
  let cachedLinkClient = null;
  let cachedLinkDb = null;

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

    'ember:kbStatus': (payload) =>
      // [app 10] an optional path argument lets the knowledge-base
      // pane verify a TYPED path before any settings change; without
      // one it reads the chosen knowledge base as before.
      knowledgeBaseStatus(
        typeof payload === 'string' && payload.trim() !== '' ? payload : dbPath(),
      ),

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

    /* ------------- [app 10] Settings panes (stories 85-89) ------------- */

    /**
     * Re-register the quick-popup shortcut from Settings. On refusal the
     * registrar has already told the shell to build the tray fallback
     * (plan §5.5); the pane shows the APP-005 words.
     */
    'ember:registerShortcut': (accelerator) => {
      if (typeof accelerator !== 'string' || accelerator.trim() === '') {
        return { ok: false, error: appErrorInfo('APP-005', `${WHERE}.registerShortcut`, 'no quick-popup shortcut was given') };
      }
      if (shortcutRegistrar === null) {
        return { ok: false, error: appErrorInfo('APP-005', `${WHERE}.registerShortcut`, 'the shortcut manager is not available in this build') };
      }
      return shortcutRegistrar(accelerator);
    },

    /**
     * The masked key status for the AI connection pane: {hint} is the
     * key's LAST FOUR characters (main/key-hint.js) — never the key.
     */
    'ember:keyHint': () => {
      const hint = keyHintProvider === null ? null : keyHintProvider();
      if (hint === null || hint === undefined) {
        return { ok: true, noKey: true };
      }
      return { ok: true, hint: String(hint) };
    },
  };

  /* --- App 08 (Clean up): the sweep preview and the confirm session
     (additive channels, ticket A37; registered with the others below).
     Preview = `maintain --dry-run` and the FULL document the engine
     prints (D3: rows, counts, and the stale shortlist come from the
     command, never recomputed). Apply = a REAL `maintain --confirm
     json` run through runConfirmSession (plan §5.1): its validated
     events ride the sweepNotify push bridge; answers/stop come back as
     invokes. ONE session at a time. --- */

  let maintainSession = null; // the live apply session, or null

  Object.assign(handlers, {
    'ember:maintainPreview': async () => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      onCommand('maintain', ['--dry-run']);
      const session = clientFor(dbPath()).runConfirmSession('maintain', ['--dry-run']);
      return new Promise((resolve) => {
        let document = null;
        let failure = null;
        session.on('event', (event) => {
          if (event.event !== 'message' || typeof event.text !== 'string') return;
          const doc = maintainDocumentFromMessage(event.text);
          if (doc !== null && doc.dry_run) document = doc;
        });
        session.on('error', (info) => {
          failure = info;
        });
        session.on('exit', () => {
          if (document !== null) return resolve({ ok: true, document });
          if (failure !== null) return resolve({ ok: false, error: failure });
          resolve({
            ok: false,
            error: appErrorInfo('APP-002', `${WHERE}.maintainPreview`, 'the sweep preview ended without a report document'),
          });
        });
      });
    },

    'ember:maintainApply': async () => {
      const kbCheck = guardKnowledgeBase();
      if (!kbCheck.ok) return { ok: false, error: kbCheck.error };
      if (maintainSession !== null) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.maintainApply`, 'a sweep is already running; answer or stop it first') };
      }
      onCommand('maintain', []);
      const session = clientFor(dbPath()).runConfirmSession('maintain', []);
      maintainSession = session;
      session.on('event', (event) => sweepNotify({ kind: 'event', event }));
      session.on('error', (info) => sweepNotify({ kind: 'error', info }));
      session.on('exit', ({ exitCode }) => {
        maintainSession = null;
        sweepNotify({ kind: 'exit', exitCode });
      });
      return { ok: true };
    },

    'ember:maintainAnswer': async (payload) => {
      const answer = typeof payload === 'object' && payload !== null ? payload.answer : null;
      if (maintainSession === null || typeof answer !== 'string') {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.maintainAnswer`, 'no sweep question is waiting for an answer') };
      }
      maintainSession.answer(answer);
      return { ok: true };
    },

    'ember:maintainStop': async () => {
      if (maintainSession === null) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.maintainStop`, 'no sweep is running') };
      }
      maintainSession.stop();
      return { ok: true };
    },
  });

  /* --- App 08 block ends --- */

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

  /* ==== App 05 (ticket A34): the Add confirm-session channels =====
     Registered additively at the END of the IPC list. The session
     events and the exit ride two push channels (`ember:addEvent`,
     `ember:addExit`) sent to the invoking window; the temp pasted-text
     file lives in the user-data folder and is cleaned on every exit. */
  const addWiring = wireAddChannels(ipcMain, {
    startSession: (args) => clientFor(dbPath()).runConfirmSession('capture', args),
    validateAddTarget: () => {
      // Add may CREATE the knowledge base (capture opens and migrates
      // it): a not-yet-existing file is fine. An existing file must be
      // an Ember file (APP-006).
      const status = knowledgeBaseStatus(dbPath());
      if (status.exists && !status.looksValid) {
        return {
          ok: false,
          error: appErrorInfo('APP-006', `${WHERE}.addStart`, `the chosen file is not an Ember knowledge base: ${status.path}`),
        };
      }
      return { ok: true };
    },
    writeTempText: (text) => writeTempText(userDataPath, text),
    removeTempFile,
    cleanStaleTempFiles: () => cleanStaleTempFiles(userDataPath),
    onCommand,
  });
  /* ==== end App 05 block ==== */

  /* ==== App 06 (ticket A35): the Link items confirm-session ========
     Registered additively at the END of the IPC list, after the App 05
     block; nothing above is moved or reformatted. The events and the
     exit ride two push channels (`ember:relateEvent`,
     `ember:relateExit`) sent to the invoking window. relate owns ONE
     dedicated bridge client: the story-45 first run may sit silent for
     MINUTES while a language model downloads, so its inactivity limit
     is 10 min, not the default 120 s (I15 still holds — a frozen child
     is still killed). */
  const linkClientFor = (db) => {
    if (cachedLinkClient === null || cachedLinkDb !== db) {
      cachedLinkClient = createBridgeClient({
        emberCommand,
        dbPath: db,
        errorPattern,
        apiKeyProvider,
        sessionIdleMs: RELATE_SESSION_IDLE_MS,
      });
      cachedLinkDb = db;
    }
    return cachedLinkClient;
  };
  const relateWiring = wireRelateChannels(ipcMain, {
    startSession: (args) => linkClientFor(dbPath()).runConfirmSession('relate', args),
    validateRelateTarget: () => {
      // relate needs an EXISTING Ember file (RELATE-012 would otherwise
      // surface raw): the app gates before any child is started (I9).
      const status = knowledgeBaseStatus(dbPath());
      if (!status.exists) {
        return {
          ok: false,
          error: appErrorInfo('APP-006', `${WHERE}.relateStart`, `no knowledge base file exists yet: ${status.path}`),
        };
      }
      if (!status.looksValid) {
        return {
          ok: false,
          error: appErrorInfo('APP-006', `${WHERE}.relateStart`, `the chosen file is not an Ember knowledge base: ${status.path}`),
        };
      }
      return { ok: true };
    },
    onCommand,
  });
  /* ==== end App 06 block ==== */

  return { names: [...names, ...addWiring.channels, ...relateWiring.channels] };
}

/** The plain words for a shape refusal (shared rule, one wording). */
function keyShapeWords(reason) {
  if (reason === 'empty') return 'the key box was empty';
  if (reason === 'whitespace') return 'a key is one unbroken line of characters; this one had a space or line break inside';
  return `this key is too short; a real key has at least 20 characters (no spaces)`;
}

module.exports = { registerIpcHandlers };

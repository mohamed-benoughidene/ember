'use strict';

/**
 * The Electron main process: the app shell (L3 app step 02).
 *
 * Owns: app lifecycle, the one window, the stores, and the wiring of
 * the narrow IPC list (main/ipc.js). The renderer has no Node access;
 * it only talks to the preload allowlist (B5, T9).
 *
 * Boot order: resolve the ember command (APP-007 if the configured
 * path is missing), load settings once (APP-004 notice rides along,
 * I13), open the window, register the IPC handlers.
 *
 * `EMBER_APP_LAUNCH_CHECK=1` runs the S1 walking skeleton instead of
 * idling: open the window, run ONE read command (`list-items`) against
 * the knowledge base, print `items: N` on stdout, exit 0 — or print
 * `launch-check-error: CODE ...` and exit 1.
 */

const { app, BrowserWindow, safeStorage, ipcMain, dialog } = require('electron');
const path = require('node:path');
const {
  resolveEmberCommand,
  checkEmberCommand,
  validateKnowledgeBasePath,
} = require('./ember-command');
const { loadErrorPattern } = require('./error-pattern');
const { createBridgeClient } = require('./bridge-client');
const { createSettingsStore } = require('./settings-store');
const { createKeyStore } = require('./key-store');
const { registerIpcHandlers } = require('./ipc');

// App 11 (ticket A40): the quick popup manager + its pure parts, and
// the `--quick-add` launch route (plan §5.5).
const { createPopupManager, popupBoundsFor, quickAddRequested, shouldParkMainWindow } = require('./popup');

const LAUNCH_CHECK = process.env.EMBER_APP_LAUNCH_CHECK === '1';
const DB_OVERRIDE = process.env.EMBER_APP_DB ?? null;
// [app 11] `ember-app --quick-add`: boot straight into the popup; the
// main window is created but stays parked until something opens it.
const QUICK_ADD = quickAddRequested(process.argv);

let mainWindow = null;
// The popup's last "open the main window on setup" request, held when
// the main window's renderer is still loading (see openMainRequest).
let pendingOpenRequest = null;

function appVersion() {
  try {
    return app.getVersion();
  } catch {
    return '0.0.0';
  }
}

function createWindow({ showOnReady = true } = {}) {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 640,
    show: false,
    title: 'Ember',
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'preload.js'),
      contextIsolation: true, // the renderer cannot reach Node (B5)
      nodeIntegration: false, // doubled down; asserted by a node test
      sandbox: true,
    },
  });
  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
  // [app 11] with `--quick-add` the main window stays parked behind the
  // popup until the popup's "Open Ember" link (or a route) asks for it.
  mainWindow.once('ready-to-show', () => {
    if (showOnReady) mainWindow.show();
  });
  // The popup's held "open setup" request re-sends once the page can
  // hear it (the early-push race; see openMainRequest).
  mainWindow.webContents.on('did-finish-load', () => {
    if (pendingOpenRequest !== null && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('ember:openRequest', pendingOpenRequest);
      pendingOpenRequest = null;
    }
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  return mainWindow;
}

/** Build the adapters once at boot; Electron/OS effects only (T2). */
function buildServices(env = process.env) {
  const userData = app.getPath('userData');
  const appDir = path.join(__dirname, '..');
  return {
    settingsStore: createSettingsStore({ file: path.join(userData, 'settings.json') }),
    keyStore: createKeyStore({ file: path.join(userData, 'key.enc'), safeStorage }),
    errorPattern: loadErrorPattern(appDir),
    emberCommand: resolveEmberCommand(env),
    userDataPath: userData,
    iconPath: null, // step 03/11 pick the real icon; the tray menu works without one
  };
}

function bootNoticeFor(services) {
  // Boot notice: APP-007 when a path-shaped ember command is missing.
  const commandCheck = checkEmberCommand(services.emberCommand);
  return commandCheck.ok ? null : commandCheck.error;
}

function wireIpc(services) {
  // [app 10] Settings panes: the quick-popup shortcut re-registration
  // seam and the tray fallback (stories 85-86; app step 11 opens the
  // real popup through this same seam). The
  // Electron edge effects stay here, at the edge (T2).
  const { Tray, Menu } = require('electron');
  const { createShortcutManager, createTrayManager, registerSettingsShortcut, bootShortcutFor } = require('./shortcuts');

  const focusMainWindow = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  };

  /* =================================================================
     APP STEP 11 (ticket A40): the quick popup (stories 90-95; plan
     §5.5). Bracketed, additive: the window manager, the open/hide
     action every route shares (the global shortcut, the tray's Quick
     add, the `--quick-add` launch option, and from here step 12's
     File -> Add text menu item), and the popup's one route back into
     this window (stories 93/94).
     ================================================================= */
  const { screen } = require('electron');
  const { appErrorInfo } = require('../shared/errors'); // also the launch-check failure path's missing import (see build notes)
  const popup = createPopupManager({
    BrowserWindowCtor: BrowserWindow,
    screenApi: screen,
    pagePath: path.join(__dirname, '..', 'renderer', 'quick.html'),
    preloadPath: path.join(__dirname, '..', 'preload', 'preload.js'),
    positionFor: () => services.settingsStore.load().settings.quickPopup.position,
    alwaysOnTop: false, // the founder-review proposal (plan §5.5): default OFF, for the step gate to confirm
  });
  /**
   * One open/hide action for every quick-add route. `park` (the
   * shortcut, the tray, the launch option) tucks the main window away
   * ONLY when Ember itself was the focused window, so Esc returns to
   * the program the user came from (shouldParkMainWindow pins the rule).
   * The renderer-facing route (the e2e seam, step 12's menu item) never
   * parks. `action: 'hide'` is the popup page closing itself.
   */
  const openQuickPopup = ({ park = false, action = 'toggle' } = {}) => {
    if (action === 'hide' || popup.visible()) {
      popup.hide();
      return { ok: true, visible: false, parked: false };
    }
    let parked = false;
    if (
      park &&
      mainWindow &&
      !mainWindow.isDestroyed() &&
      shouldParkMainWindow({ focused: mainWindow.isFocused(), visible: mainWindow.isVisible() })
    ) {
      mainWindow.hide();
      parked = true;
    }
    const shown = popup.show();
    if (!shown.ok) process.stderr.write(`launch-note: ${shown.error.code} ${shown.error.name} | ${shown.error.detail}\n`);
    return { ok: shown.ok, visible: shown.ok, parked };
  };
  /**
   * The popup's route to the full window: story 93 ("Open Ember") and
   * story 94's path to fix a missing setup. Focus (and restore) the
   * main window, then tell its page which view was asked for.
   */
  const openMainRequest = ({ view = 'ember' } = {}) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return { ok: false, error: appErrorInfo('APP-007', 'main.main.quickOpenMain', 'the main window is not available') };
    }
    focusMainWindow();
    if (view === 'setup') {
      // Under load the main window's renderer may still be booting when
      // the popup asks (the same early-push race the Add session solved
      // with its buffered attach): hold the LAST request and re-send it
      // when the page finishes loading (main.js, the did-finish-load
      // hook), instead of losing it (ticket A39-merge, lead fix).
      if (mainWindow.webContents.isLoading()) {
        pendingOpenRequest = { view };
      } else {
        mainWindow.webContents.send('ember:openRequest', { view });
      }
    }
    return { ok: true, view };
  };
  /* === App 11 block ends === */

  /* =================================================================
     APP STEP 12 (ticket A41): the application menu (spec §9; plan
     §5.7) as ONE pure definition (shared/menu-template.mjs) built by
     the manager (main/app-menu.js) and consumed here. The dispatch
     maps the template's action ids onto the OS effects; the Edit
     menu's Undo/Redo labels re-derive from `undo --dry-run --format
     json` (the step-07 derivation in shared/undo-labels.mjs — the
     same words the Fix and close bar shows) whenever the knowledge
     base may have changed: after any bridge command or session
     settles (the ipc onBridgeActivity hook), after a settings save or
     a knowledge-base switch (onSettingsSaved), and once at boot. The
     requests reach the renderer over ONE new push channel
     (ember:menuRequest); navigation is always the renderer's own
     router (B4), and Undo/Redo land on the Fix and close screen's
     own controls — one code path, no forked undo.
     ================================================================= */
  const { createAppMenuManager } = require('./app-menu');
  const { deriveUndoMenuState, aboutCreditsText } = require('../shared/menu-template.mjs');
  const { validateKnowledgeBasePath: menuKbGuard } = require('./ember-command');

  /**
   * Commands that CANNOT change the ledger: no label re-derive after
   * them (the reads, and the file-producing backup/export). `maintain`
   * is deliberately NOT skipped: its apply run writes. The refresh runs
   * two short-lived child processes (one dry-run each way).
   */
  const MENU_ACTIVITY_SKIPS = new Set([
    'list-items',
    'show-item',
    'current-state',
    'topic-search',
    'why',
    'history',
    'capture-source',
    'db-check',
    'backup',
    'export',
  ]);

  /** The menu's own copy of the two labels' state (the pure derivation). */
  const menuState = {
    sidebarHidden: false,
    undo: deriveUndoMenuState(null, 'undo'),
    redo: deriveUndoMenuState(null, 'redo'),
  };

  let labelClient = null; // ONE client for the label dry-runs, per file
  let labelClientDb = null;
  function labelClientFor(db) {
    if (labelClient === null || labelClientDb !== db) {
      labelClient = createBridgeClient({
        emberCommand: services.emberCommand,
        dbPath: db,
        errorPattern: services.errorPattern,
        apiKeyProvider: () => services.keyStore.get(),
        // Deliberately NO onActivity here: the refresh must not re-arm itself.
      });
      labelClientDb = db;
    }
    return labelClient;
  }

  let labelTimer = null;
  let labelRefreshInFlight = false;
  function scheduleUndoLabelRefresh() {
    if (labelTimer) clearTimeout(labelTimer);
    labelTimer = setTimeout(() => {
      labelTimer = null;
      refreshUndoLabels();
    }, 250);
  }

  /** Re-derive both labels from the real engine (D3), then rebuild. */
  async function refreshUndoLabels() {
    if (labelRefreshInFlight) return; // one at a time; a queued timer follows up
    labelRefreshInFlight = true;
    try {
      const db = DB_OVERRIDE ?? services.settingsStore.load().settings.knowledgeBasePath;
      if (typeof db === 'string' && db !== '' && menuKbGuard(db).ok && undoLabelsSafeForFile(db)) {
        const client = labelClientFor(db);
        const [undoResult, redoResult] = await Promise.all([
          client.runCommand('undo', ['--dry-run']),
          client.runCommand('redo', ['--dry-run']),
        ]);
        menuState.undo = deriveUndoMenuState(undoResult, 'undo');
        menuState.redo = deriveUndoMenuState(redoResult, 'redo');
      } else {
        // No usable knowledge base, or a pre-undo file (schema < 13):
        // the undo dry-run opens through the WRITE path and would
        // silently migrate an older file (found by the keep-safe e2e).
        // The labels stay in their honest disabled state instead.
        menuState.undo = deriveUndoMenuState(null, 'undo');
        menuState.redo = deriveUndoMenuState(null, 'redo');
      }
    } catch (err) {
      process.stderr.write(`launch-note: APP-000 AppError | the Edit menu's Undo and Redo labels could not be re-derived (${err instanceof Error ? err.message : 'unknown error'})\n`);
    } finally {
      labelRefreshInFlight = false;
      menuManager.refresh();
    }
  }

  /**
   * Read-only schema-version probe for the undo-label gate: the undo
   * dry-run is a READ-shaped derivation but runs through the write
   * command path (which migrates), so on a schema < 13 file it must
   * never run (spec 12.8's one-way rule protects the founder's file).
   * Read-only open of user_version — no migration is possible here.
   */
  function undoLabelsSafeForFile(dbPath) {
    try {
      const { DatabaseSync } = require('node:sqlite');
      const db = new DatabaseSync(dbPath, { readOnly: true });
      try {
        // Ember stores its schema version in the schema_version TABLE
        // (ember/adapters/sqlite.py), not in PRAGMA user_version.
        const row = db.prepare('SELECT version FROM schema_version').get();
        return Number(row && row.version) >= 13;
      } finally {
        db.close();
      }
    } catch (err) {
      process.stderr.write(`launch-note: APP-000 AppError | the undo-label gate could not read the file's schema version (${err instanceof Error ? err.message : 'unknown error'})\n`);
      return false; // fail closed: an unreadable file is never migrated
    }
  }

  /** One menu request into the main window's renderer (B4: the
   * renderer owns its router; main only asks). */
  const sendMenuRequest = (payload) => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (payload.kind !== 'undo' && payload.kind !== 'redo') focusMainWindow();
    mainWindow.webContents.send('ember:menuRequest', payload);
  };

  /** Story 108: the About box carries the font/licence credits. */
  const showAbout = () => {
    const credits = aboutCreditsText({
      version: appVersion(),
      fontsPath: path.join(__dirname, '..', 'assets', 'fonts'),
    });
    if (process.platform === 'darwin') {
      app.setAboutPanelOptions({ credits });
      app.showAboutPanel();
      return;
    }
    const owner = mainWindow && !mainWindow.isDestroyed() ? mainWindow : null;
    dialog
      .showMessageBox(owner, {
        type: 'info',
        title: 'About Ember',
        message: `Ember ${appVersion()}`,
        detail: credits,
        buttons: ['OK'],
      })
      .catch(() => {}); // a closed window while showing is not an error
  };

  /** The action ids -> the OS effects (the only edge). */
  const dispatchMenuAction = (id) => {
    switch (id) {
      case 'about':
        showAbout();
        break;
      case 'settings':
        sendMenuRequest({ kind: 'navigate', pane: 'settings' });
        break;
      // The always-available add route (plan §5.5): the SAME open/hide
      // action the shortcut, the tray and `--quick-add` use. Never parks:
      // the caller is Ember's own menu.
      case 'file-add-text':
        openQuickPopup({ action: 'toggle', park: false });
        break;
      case 'file-open-kb':
      case 'file-backup':
      case 'file-export':
        // These jobs live on Keep safe (stories 70-76: the pickers, the
        // story-76 confirmation, the report lines). The menu takes the
        // user there; it never starts a write or a pick itself.
        sendMenuRequest({ kind: 'navigate', pane: 'keepsafe' });
        break;
      case 'edit-undo':
      case 'edit-redo':
        sendMenuRequest({ kind: id === 'edit-undo' ? 'undo' : 'redo' });
        break;
      case 'edit-find':
        sendMenuRequest({ kind: 'find' });
        break;
      case 'view-sidebar':
        menuState.sidebarHidden = !menuState.sidebarHidden;
        sendMenuRequest({ kind: 'toggle-sidebar', visible: !menuState.sidebarHidden });
        menuManager.refresh();
        break;
      default:
        if (typeof id === 'string' && id.startsWith('job-')) {
          sendMenuRequest({ kind: 'navigate', pane: id.slice(4) });
        }
    }
  };

  const menuManager = createAppMenuManager({
    MenuApi: Menu,
    platform: process.platform === 'darwin' ? 'darwin' : 'other',
    context: () => {
      const s = services.settingsStore.load().settings;
      const kbChosen =
        DB_OVERRIDE !== null ||
        (typeof s.knowledgeBasePath === 'string' && s.knowledgeBasePath.trim() !== '');
      return {
        kbChosen,
        sidebarVisible: !menuState.sidebarHidden,
        jobs: { order: s.menuOrder, hidden: s.menuHidden },
        undo: menuState.undo,
        redo: menuState.redo,
      };
    },
    dispatch: dispatchMenuAction,
  });
  menuManager.refresh(); // the menu exists from boot (about/quit/Help work pre-window)
  scheduleUndoLabelRefresh(); // the first real derivation, ~250 ms after boot
  /* === App 12 menu block ends === */


  let tray = null;
  const showTrayFallback = () => {
    if (tray !== null) return; // the fallback is built once per run
    tray = createTrayManager({ TrayCtor: Tray, MenuBuilder: Menu, iconPath: services.iconPath });
    const shown = tray.show({
      // [app 11] Quick add is the popup itself now (story 95); Open Ember stays the full window.
      onQuickAdd: () => openQuickPopup({ park: true }),
      onOpenEmber: focusMainWindow,
      onQuit: () => app.quit(),
    });
    if (!shown.ok) process.stderr.write(`launch-note: ${shown.error.code} ${shown.error.detail}\n`);
  };
  // [app 11] The e2e seam EMBER_APP_SHORTCUT_REFUSED=1 stands in for an
  // OS refusal (same family as EMBER_APP_PICK_PATH) using the SAME fake
  // shape the manager's unit tests already pin — no manager change.
  const globalShortcutApi =
    process.env.EMBER_APP_SHORTCUT_REFUSED === '1'
      ? { register: () => false, unregisterAll: () => {} }
      : require('electron').globalShortcut;
  const shortcutManager = createShortcutManager({
    globalShortcut: globalShortcutApi,
    // [app 11] the keys open the quick popup now (story 90).
    onQuickAdd: () => openQuickPopup({ park: true }),
    onFailure: () => showTrayFallback(),
  });
  const maskedKeyHint = require('./key-hint');

  const registered = registerIpcHandlers({
    ipcMain,
    settingsStore: services.settingsStore,
    keyStore: services.keyStore,
    apiKeyProvider: () => services.keyStore.get(),
    errorPattern: services.errorPattern,
    emberCommand: services.emberCommand,
    dbOverride: DB_OVERRIDE,
    appVersion: appVersion(),
    userDataPath: services.userDataPath,
    bootNotice: bootNoticeFor(services),
    kbChooser: () => {
      // E2E seam (step 09), same family as EMBER_APP_COMMAND/EMBER_APP_DB:
      // the native open dialog cannot be driven by Playwright, so a set
      // EMBER_APP_PICK_PATH stands in for the user's pick. Unset, it is
      // the real dialog.
      if (typeof process.env.EMBER_APP_PICK_PATH === 'string' && process.env.EMBER_APP_PICK_PATH !== '') {
        return { path: process.env.EMBER_APP_PICK_PATH };
      }
      const chosen = dialog.showOpenDialogSync({
        title: 'Open a knowledge base file',
        properties: ['openFile'],
        filters: [{ name: 'Ember knowledge base', extensions: ['db', 'sqlite', '*'] }],
      });
      if (!chosen || chosen.length === 0) return null;
      return { path: chosen[0] };
    },
    // Step 09: the `where to save` dialog for backup and export.
    saveChooser: (ask) => {
      // E2E seam: EMBER_APP_SAVE_PATH stands in for the user's save
      // pick (the native save dialog cannot be driven by Playwright).
      if (typeof process.env.EMBER_APP_SAVE_PATH === 'string' && process.env.EMBER_APP_SAVE_PATH !== '') {
        return { path: process.env.EMBER_APP_SAVE_PATH };
      }
      const isBackup = ask && ask.kind === 'backup';
      const chosen = dialog.showSaveDialogSync({
        title: isBackup ? 'Where should the backup go?' : 'Where should the export go?',
        defaultPath: ask && typeof ask.defaultName === 'string' && ask.defaultName !== '' ? ask.defaultName : undefined,
        properties: ['createDirectory', 'showOverwriteConfirmation'],
      });
      if (!chosen || chosen === '') return null;
      return { path: chosen };
    },
    /* --- App 08 (Clean up): the sweep-session event push (additive; ticket A37).
       The apply session streams its validated events to the one window over the
       named channel below. A closing window is not an error: the app is quitting. --- */
    sweepNotify: (payload) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('ember:maintainEvent', payload);
      }
    },
    // [app 10] the Settings seams (stories 85-89)
    shortcutRegistrar: (accelerator) => registerSettingsShortcut({ manager: shortcutManager, accelerator }),
    keyHintProvider: () => maskedKeyHint.maskKey(services.keyStore.get()),
    /* --- [app 11] the quick popup's two renderer-facing channels
       (stories 90-95): the renderer-safe route to the popup — the
       SAME action object the shortcut, the tray and `--quick-add`
       use (parking off; step 12's File -> Add text item will point
       at this handler too) — and the popup's one route back into
       the full window (93) with its path to fix a missing setup (94). --- */
    openQuickPopup: ({ action = 'toggle' } = {}) => openQuickPopup({ action, park: false }),
    openMainRequest,
    // [app 12] the menu's re-derive hooks (see the step-12 block above).
    onBridgeActivity: (name) => {
      if (!MENU_ACTIVITY_SKIPS.has(name)) scheduleUndoLabelRefresh();
    },
    onSettingsSaved: () => {
      menuManager.refresh();
      scheduleUndoLabelRefresh();
    },
  });

  // [app 11] The default global shortcut, registered at boot AFTER
  // first run is done (step file story 90: before that there is no
  // knowledge base to add into). A changed choice from Settings re-
  // registers through the step-10 seam. An OS refusal lands in the
  // shipped APP-005 path above: the tray fallback appears and the
  // launch-note goes to stderr — never a silent failure (I7).
  const bootAccelerator = bootShortcutFor(services.settingsStore.load().settings);
  if (bootAccelerator !== null) shortcutManager.register(bootAccelerator);

  return { registered, openQuickPopup };
}

/** The normal boot: window + IPC, then idle until the window closes. */
function boot() {
  const services = buildServices();
  services.settingsStore.load(); // I13: loaded once at boot, passed down
  const { openQuickPopup } = wireIpc(services);
  // [app 11] `--quick-add`: the main window is created but parked; the
  // popup is the app's front (the launch route that always works).
  createWindow({ showOnReady: !QUICK_ADD });
  if (QUICK_ADD) openQuickPopup({ park: false });
}

function onceReadyToShow(win) {
  return new Promise((resolve) => {
    if (win.isVisible()) resolve();
    else win.once('ready-to-show', () => resolve());
  });
}

function failLaunchCheck(error) {
  process.stderr.write(`launch-check-error: ${error.code} ${error.name} | ${error.detail}\n`);
  app.exit(1);
}

/** The S1 walking skeleton: window + one read command + honest exit. */
async function runLaunchCheck() {
  const services = buildServices();
  const commandCheck = checkEmberCommand(services.emberCommand);
  if (!commandCheck.ok) return failLaunchCheck(commandCheck.error);
  const db = DB_OVERRIDE ?? services.settingsStore.load().settings.knowledgeBasePath;
  const kbCheck = validateKnowledgeBasePath(db);
  if (!kbCheck.ok) return failLaunchCheck(kbCheck.error);

  const win = createWindow();
  await onceReadyToShow(win);
  const client = createBridgeClient({
    emberCommand: services.emberCommand,
    dbPath: db,
    errorPattern: services.errorPattern,
    apiKeyProvider: () => services.keyStore.get(),
  });
  const result = await client.runCommand('list-items', []);
  if (!result.ok) return failLaunchCheck(result.error);
  process.stdout.write(`items: ${result.data.total}\n`);
  app.exit(0);
}

app.whenReady().then(() => {
  if (LAUNCH_CHECK) {
    runLaunchCheck().catch((err) =>
      failLaunchCheck(appErrorInfo('APP-000', 'main.main.runLaunchCheck', err instanceof Error ? err.message : 'unknown launch failure')),
    );
  } else {
    boot();
  }
});

app.on('window-all-closed', () => {
  app.quit();
});

// NOTE: this module is Electron's main entry. The checks live in
// test/launch-check.js (`npm run check:launch`) and
// test/e2e/smoke.js (`npm run test:e2e`).

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

const LAUNCH_CHECK = process.env.EMBER_APP_LAUNCH_CHECK === '1';
const DB_OVERRIDE = process.env.EMBER_APP_DB ?? null;

let mainWindow = null;

function appVersion() {
  try {
    return app.getVersion();
  } catch {
    return '0.0.0';
  }
}

function createWindow() {
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
  mainWindow.once('ready-to-show', () => mainWindow.show());
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
  return registerIpcHandlers({
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
      const chosen = dialog.showOpenDialogSync({
        title: 'Open a knowledge base file',
        properties: ['openFile'],
        filters: [{ name: 'Ember knowledge base', extensions: ['db', 'sqlite', '*'] }],
      });
      if (!chosen || chosen.length === 0) return null;
      return { path: chosen[0] };
    },
    /* --- App 08 (Clean up): the sweep-session event push (additive; ticket A37).
       The apply session streams its validated events to the one window over the
       named channel below. A closing window is not an error: the app is quitting. --- */
    sweepNotify: (payload) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('ember:maintainEvent', payload);
      }
    },
  });
}

/** The normal boot: window + IPC, then idle until the window closes. */
function boot() {
  const services = buildServices();
  services.settingsStore.load(); // I13: loaded once at boot, passed down
  wireIpc(services);
  createWindow();
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

'use strict';

/**
 * The gallery window (dev-only, L3 app step 03 check command). A plain
 * BrowserWindow on the gallery page — no preload, no bridge, no stores:
 * the design layer is pure HTML/CSS/JS and needs none of the shell.
 * The e2e design check (test/e2e/design.js) launches THIS entry, so the
 * page the founder sees and the page the tests see are the same one.
 */

const { app, BrowserWindow } = require('electron');
const path = require('node:path');

function createWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 800,
    show: false,
    title: 'Ember design gallery',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.loadFile(path.join(__dirname, '..', 'renderer', 'gallery.html'));
  win.once('ready-to-show', () => win.show());
  return win;
}

app.whenReady().then(() => {
  createWindow();
});

app.on('window-all-closed', () => {
  app.quit();
});

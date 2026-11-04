'use strict';

/**
 * The app's raster icons (app step 13): the Linux tray needs a PNG
 * (step 11 shipped an honest placeholder — Electron's default icon),
 * and the window/taskbar deserve the same treatment. Both read ONLY
 * files that exist next to the app, so a tree without the assets keeps
 * the old default behaviour instead of a broken image path.
 */

const fs = require('node:fs');
const path = require('node:path');

const TRAY_ICON = path.join('assets', 'icons', 'ember-tray-32.png');
const WINDOW_ICON = path.join('assets', 'icons', 'ember-256.png');

/** @returns {string|null} the file path when it is a real file, else null. */
function existingFile(...parts) {
  const p = path.join(...parts);
  try {
    return fs.statSync(p).isFile() ? p : null;
  } catch {
    return null;
  }
}

/** The tray icon for the APP-005 fallback (plan §5.5). */
function trayIconPath(appDir) {
  return existingFile(appDir, TRAY_ICON);
}

/** The window/taskbar icon. */
function windowIconPath(appDir) {
  return existingFile(appDir, WINDOW_ICON);
}

module.exports = { trayIconPath, windowIconPath };

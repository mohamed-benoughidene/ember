'use strict';

/**
 * The shortcut manager (interface-app-plan.md §5.5), behind a small
 * interface so tests can fake the OS (T3).
 *
 * Registers the quick-popup global shortcut. When the OS refuses it
 * (some Wayland compositors do), it raises APP-005 and falls back to
 * the tray menu. The real popup, tray icon and defaults are step 11;
 * step 02 ships the seam and the failure rule.
 */

const { appErrorInfo } = require('../shared/errors');

const WHERE = 'main.shortcuts';

/**
 * @param {object} options
 * @param {object} options.globalShortcut Electron's globalShortcut (or a fake)
 * @param {(info: object) => void} options.onFailure called with the APP-005
 *   info when registration is refused (the shell then builds the tray)
 * @param {() => void} options.onQuickAdd what the key press does
 */
function createShortcutManager(options) {
  const { globalShortcut, onFailure, onQuickAdd } = options;

  /**
   * @param {string} accelerator e.g. "CommandOrControl+Alt+E"
   * @returns {{ok: true} | {ok: false, error: info}}
   */
  function register(accelerator) {
    if (typeof accelerator !== 'string' || accelerator.trim() === '') {
      const error = appErrorInfo('APP-005', `${WHERE}.register`, 'no quick-popup shortcut is configured');
      onFailure(error);
      return { ok: false, error };
    }
    let registered = false;
    try {
      registered = globalShortcut.register(accelerator, onQuickAdd);
    } catch (err) {
      const error = appErrorInfo('APP-005', `${WHERE}.register`, `the quick-popup shortcut was refused (${err instanceof Error ? err.message : 'unknown error'}); the tray menu and File -> Add text still work`);
      onFailure(error);
      return { ok: false, error };
    }
    if (!registered) {
      const error = appErrorInfo('APP-005', `${WHERE}.register`, 'the quick-popup shortcut was refused; the tray menu and File -> Add text still work');
      onFailure(error);
      return { ok: false, error };
    }
    return { ok: true };
  }

  function unregisterAll() {
    try {
      globalShortcut.unregisterAll();
    } catch {
      /* nothing registered / no OS support */
    }
  }

  return { register, unregisterAll };
}

/**
 * The tray manager, also behind a small interface. Builds the fallback
 * menu ("Quick add / Open Ember / Quit", plan §5.5) when the shortcut
 * fails. `TrayCtor` and `MenuBuilder` are injected so tests fake them.
 *
 * @param {object} options
 * @param {typeof Electron.Tray} options.TrayCtor
 * @param {{buildFromTemplate: (t: object[]) => object}} options.MenuBuilder
 * @param {string} [options.iconPath] may be null at step 02; Electron
 *   then shows an empty tray entry whose menu still works
 */
function createTrayManager(options) {
  const { TrayCtor, MenuBuilder, iconPath = null } = options;
  let tray = null;
  let built = 0;

  /**
   * @param {{onQuickAdd: () => void, onOpenEmber: () => void, onQuit: () => void}} actions
   * @returns {{ok: true} | {ok: false, error: info}}
   */
  function show(actions) {
    try {
      tray = new TrayCtor(iconPath);
      tray.setToolTip('Ember');
      tray.setContextMenu(
        MenuBuilder.buildFromTemplate([
          { label: 'Quick add', click: actions.onQuickAdd },
          { label: 'Open Ember', click: actions.onOpenEmber },
          { type: 'separator' },
          { label: 'Quit', click: actions.onQuit },
        ]),
      );
      built += 1;
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-005', 'main.tray.show', `the tray fallback could not start (${err instanceof Error ? err.message : 'unknown error'}); the File -> Add text menu item still works`),
      };
    }
  }

  function destroy() {
    if (tray) {
      try {
        tray.destroy();
      } catch {
        /* already gone */
      }
      tray = null;
    }
  }

  return { show, destroy, get builtCount() { return built; } };
}

module.exports = { createShortcutManager, createTrayManager };

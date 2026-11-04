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
  // [fix #41] the accelerator the OS last told us is live, or null.
  // The dedupe BELOW exists because every settings save used to
  // re-register the SAME key: on KDE Wayland the XDG GlobalShortcuts
  // portal refuses a reused session handle yet Electron answers true,
  // so each no-change save minted a stale KDE entry and could drop a
  // working bind (issue 41's 1,529 stale entries on the founder's
  // machine). One registration per real key change; the working bind
  // from boot stays untouched.
  let current = null;

  /**
   * @param {string} accelerator e.g. "CommandOrControl+Alt+E"
   * @returns {{ok: true, unchanged?: boolean} | {ok: false, error: info}}
   */
  function register(accelerator) {
    if (typeof accelerator !== 'string' || accelerator.trim() === '') {
      const error = appErrorInfo('APP-005', `${WHERE}.register`, 'no quick-popup shortcut is configured');
      onFailure(error);
      return { ok: false, error };
    }
    if (current === accelerator) return { ok: true, unchanged: true };
    let registered = false;
    try {
      registered = globalShortcut.register(accelerator, onQuickAdd);
    } catch (err) {
      current = null;
      const error = appErrorInfo('APP-005', `${WHERE}.register`, `the quick-popup shortcut was refused (${err instanceof Error ? err.message : 'unknown error'}); the tray menu and File -> Add text still work`);
      onFailure(error);
      return { ok: false, error };
    }
    if (!registered) {
      current = null;
      const error = appErrorInfo('APP-005', `${WHERE}.register`, 'the quick-popup shortcut was refused; the tray menu and File -> Add text still work');
      onFailure(error);
      return { ok: false, error };
    }
    current = accelerator;
    return { ok: true };
  }

  function unregisterAll() {
    try {
      globalShortcut.unregisterAll();
    } catch {
      /* nothing registered / no OS support */
    }
    current = null;
  }

  return { register, unregisterAll, current: () => current };
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

/* ---------- [app 10] the Settings re-registration flow ---------- */

/**
 * Re-register the quick-popup shortcut from the Settings pane
 * (story 85): forget every registered shortcut first (an old choice
 * must not keep working), then try the new one. On refusal the APP-005
 * error comes back to the pane AND the manager's onFailure ran, which
 * is where the shell builds the tray fallback (plan §5.5).
 * [fix #41] Except when nothing changed — then it is a no-op (see body).
 *
 * @param {object} args
 * @param {{register: (a: string, cb: () => void) => boolean, unregisterAll: () => void, current: () => string|null}} args.manager
 *   the createShortcutManager instance
 * @param {string} args.accelerator the new shortcut
 * @returns {{ok: true, unchanged?: true} | {ok: false, error: info}}
 */
function registerSettingsShortcut({ manager, accelerator }) {
  // [fix #41] An UNCHANGED accelerator is a no-op — no unregister, no
  // OS call — so saving a pane that never touched the shortcut can
  // neither mint a stale KDE portal entry nor drop the working bind
  // the boot registration holds. Changed keys keep the forget-then-try
  // flow below.
  if (manager.current() === accelerator) return { ok: true, unchanged: true };
  manager.unregisterAll();
  return manager.register(accelerator);
}

/* ---------- [app 11] the boot registration choice (stories 90/95) ---------- */

/**
 * The accelerator to register at boot, or null when registration must
 * wait: before first run is done there is no knowledge base to add
 * into, and first run owns the screen (step file: "registered at boot
 * after first run is done"). An unreadable quickPopup shape falls back
 * to the spec §10 default, never to silence. Pure (T1).
 *
 * @param {object} [settings] the settings-schema settings object
 * @returns {string|null}
 */
function bootShortcutFor(settings) {
  const s = settings && typeof settings === 'object' ? settings : {};
  const kb = typeof s.knowledgeBasePath === 'string' ? s.knowledgeBasePath.trim() : '';
  if (kb === '') return null;
  const chosen = s.quickPopup && typeof s.quickPopup === 'object' ? s.quickPopup.shortcut : null;
  return typeof chosen === 'string' && chosen.trim() !== '' ? chosen : 'CommandOrControl+Alt+E';
}

/**
 * [fix #40] The tray's boot gate, beside bootShortcutFor's: the tray
 * is a first-class citizen now, not an error-only artefact. Issue 40
 * on the founder's desktop — D-24's close-to-tray parked the window
 * with NO reachable icon whenever the shortcut registration reported
 * success (issue 41's portal lie: the XDG GlobalShortcuts portal refuses
 * a reused session handle yet Electron answers true). So the tray boots
 * whenever a knowledge base is set — the SAME gate as the boot shortcut
 * (story 90: before first run the wizard owns the screen and the
 * window's own Quit is reachable). Pure (T1).
 *
 * @param {object} [settings] the settings-schema settings object
 * @returns {boolean} true when the tray must exist at boot
 */
function bootTrayFor(settings) {
  const s = settings && typeof settings === 'object' ? settings : {};
  const kb = typeof s.knowledgeBasePath === 'string' ? s.knowledgeBasePath.trim() : '';
  return kb !== '';
}

module.exports = { createShortcutManager, createTrayManager, registerSettingsShortcut, bootShortcutFor, bootTrayFor };

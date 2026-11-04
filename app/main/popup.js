'use strict';

/**
 * The quick popup window (app step 11, ticket A40; plan §5.5, spec
 * stories 90-95).
 *
 * Behind a small interface (T2/T3): the Electron window and the OS
 * screen are injected fakes in the unit tests; the pure parts — the
 * bounds maths, the `--quick-add` launch detection, the parking rule —
 * live here too so tests can pin them exactly.
 *
 * Defaults landed by this step (the deferred settings of the step
 * file): the popup is a 440px frameless window (DESIGN.md Layout);
 * it shows on the display the mouse is on, at the saved position
 * setting (top-centre | bottom-right; the schema default is
 * bottom-right). It closes on Esc, or automatically after Stop; the
 * draft text survives a hide (the page stays alive until the next
 * open — richer persistence is step 12/13 work if asked).
 */

const { appErrorInfo } = require('../shared/errors');

const WHERE = 'main.popup';

/** DESIGN.md Layout: "The quick popup is a 440px window with only Add". */
const POPUP_WIDTH = 440;
const POPUP_HEIGHT = 560;
/** DESIGN.md spacing step 6 (20px): the window's gap to the screen edge. */
const POPUP_MARGIN = 20;
/** SPEC §10 default; kept here only as the boot fallback wording's friend —
 * the schema default in shared/settings-schema.js is the single source. */
const DEFAULT_POSITION = 'bottom-right';

/**
 * The popup's x/y on one display's work area. Pure (T1); clamps into
 * the work area so a small screen can never push the window off it.
 *
 * @param {{workArea: {x:number,y:number,width:number,height:number}, position: string, width?: number, height?: number, margin?: number}} args
 * @returns {{x:number,y:number,width:number,height:number}}
 */
function popupBoundsFor({ workArea, position, width = POPUP_WIDTH, height = POPUP_HEIGHT, margin = POPUP_MARGIN }) {
  const area = workArea && typeof workArea === 'object' ? workArea : { x: 0, y: 0, width: 1024, height: 768 };
  const maxX = Math.max(area.x, area.x + area.width - width);
  const maxY = Math.max(area.y, area.y + area.height - height);
  let x;
  let y;
  if (position === 'top-center') {
    x = area.x + Math.round((area.width - width) / 2);
    y = area.y + margin;
  } else {
    // 'bottom-right' and any unknown saved value: the schema default.
    x = area.x + area.width - width - margin;
    y = area.y + area.height - height - margin;
  }
  return {
    x: Math.min(Math.max(x, area.x), maxX),
    y: Math.min(Math.max(y, area.y), maxY),
    width,
    height,
  };
}

/**
 * The always-available launch route (plan §5.5): `ember-app --quick-add`
 * boots straight into the popup. Only the exact flag counts; anything
 * that merely starts with it (`--quick-addx`) does not.
 *
 * @param {string[]} argv process.argv
 * @returns {boolean}
 */
function quickAddRequested(argv) {
  return Array.isArray(argv) && argv.includes('--quick-add');
}

/**
 * The parking rule for the global shortcut (stories 90/95: the popup
 * opens from any program — pressing the keys while EMBER itself was
 * the focused window should not leave a second front window behind,
 * so Ember gets parked and the previous program regains focus after
 * Esc). Pure so the exact behaviour is pinned for the founder's
 * review at this step's gate.
 *
 * @param {{focused: boolean, visible: boolean}} mainWindowState
 * @returns {boolean}
 */
function shouldParkMainWindow({ focused, visible }) {
  return Boolean(focused && visible);
}

/**
 * The popup window manager. `BrowserWindowCtor` and `screenApi` are
 * injected so tests fake the OS (T3); nothing here touches stores.
 *
 * @param {object} options
 * @param {typeof Electron.BrowserWindow} options.BrowserWindowCtor
 * @param {{getCursorScreenPoint: () => {x:number,y:number}, getDisplayNearestPoint: (p: object) => {workArea: object}}} options.screenApi
 * @param {string} options.pagePath the popup's HTML file
 * @param {string} options.preloadPath the SAME preload allowlist (B5)
 * @param {() => string} [options.positionFor] the saved position setting
 * @param {boolean} [options.alwaysOnTop] the founder-review proposal
 *   (default OFF; plan §5.5: "a proposal the founder reviews at step 11")
 * @param {typeof popupBoundsFor} [options.boundsFor] pure bounds builder
 */
function createPopupManager({
  BrowserWindowCtor,
  screenApi,
  pagePath,
  preloadPath,
  positionFor = () => DEFAULT_POSITION,
  alwaysOnTop = false,
  boundsFor = popupBoundsFor,
}) {
  let win = null;
  let created = 0;
  let shown = 0;

  /**
   * Re-apply the saved position a few times: some X11 window managers
   * place a window that is just being mapped by their own policy and
   * ignore the position it was created/asked with. Each retry verifies
   * nothing (a destroyed window, for instance) — the loop lives for
   * under a second and only ever touches this one popup.
   */
  function place(target, attemptsLeft = 5) {
    if (attemptsLeft <= 0 || !win || win.isDestroyed()) return;
    try {
      win.setBounds({ x: target.x, y: target.y, width: target.width, height: target.height });
    } catch (err) {
      return; // a WM refusal only ends up moving the popup; nothing to recover
    }
    setTimeout(() => place(target, attemptsLeft - 1), 120);
  }

  /** Bounds per open: the display the mouse sits on + the saved position. */
  function computeBounds() {
    const position = typeof positionFor() === 'string' && positionFor() !== '' ? positionFor() : DEFAULT_POSITION;
    const fallbackArea = { x: 0, y: 0, width: 1024, height: 768 };
    try {
      const display = screenApi.getDisplayNearestPoint(screenApi.getCursorScreenPoint());
      return boundsFor({ workArea: display.workArea, position });
    } catch {
      // No readable screen (headless fallback): a defined rectangle, never a crash.
      return boundsFor({ workArea: fallbackArea, position });
    }
  }

  /**
   * Show (create on first use) and focus the popup. A second open
   * reuses the SAME page — the draft text state survives every hide,
   * the step file's "kept until the next open".
   * @returns {{ok: true, created: boolean} | {ok: false, error: object}}
   */
  function show() {
    try {
      const bounds = computeBounds();
      if (win && !win.isDestroyed()) {
        win.show();
        place(bounds);
        win.focus();
        shown += 1;
        return { ok: true, created: false };
      }
      win = new BrowserWindowCtor({
        width: bounds.width,
        height: bounds.height,
        x: bounds.x,
        y: bounds.y,
        show: false,
        title: 'Ember quick add',
        frame: false, // DESIGN.md: a small capture window; Esc closes it
        resizable: false,
        minimizable: false,
        maximizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        alwaysOnTop, // the founder-review proposal; default OFF
        webPreferences: {
          preload: preloadPath,
          contextIsolation: true, // the same isolation switches as the main window
          nodeIntegration: false,
          sandbox: true,
        },
      });
      created += 1;
      win.loadFile(pagePath);
      win.once('ready-to-show', () => {
        if (win && !win.isDestroyed()) {
          win.show();
          place(bounds); // defeats the WM's placement-on-map (see place above)
          win.focus();
        }
      });
      return { ok: true, created: true };
    } catch (err) {
      // I7: a refusal never crashes the app; the main window's Add
      // screen and (after APP-005) the tray routes still work.
      return {
        ok: false,
        error: appErrorInfo('APP-005', `${WHERE}.show`, `the quick popup could not open (${err instanceof Error ? err.message : 'unknown error'}); the main window's Add screen still works`),
      };
    }
  }

  /** Hide (never destroy): the page keeps its state for the next open. */
  function hide() {
    if (win && !win.isDestroyed() && win.isVisible()) win.hide();
    return { ok: true };
  }

  function visible() {
    return Boolean(win && !win.isDestroyed() && win.isVisible());
  }

  /** Used only at app teardown; ordinary use hides, never destroys. */
  function close() {
    if (win && !win.isDestroyed()) {
      try {
        win.destroy();
      } catch {
        /* already gone */
      }
    }
    win = null;
  }

  return { show, hide, visible, close, get createdCount() { return created; }, get showCount() { return shown; } };
}

module.exports = {
  POPUP_WIDTH,
  POPUP_HEIGHT,
  POPUP_MARGIN,
  DEFAULT_POSITION,
  popupBoundsFor,
  quickAddRequested,
  shouldParkMainWindow,
  createPopupManager,
};

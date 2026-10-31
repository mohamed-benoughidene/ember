'use strict';

/**
 * The quick popup's pure parts and its window manager on fakes
 * (app step 11, ticket A40; plan §5.5, T1/T2/T3).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DEFAULT_POSITION,
  POPUP_WIDTH,
  popupBoundsFor,
  quickAddRequested,
  shouldParkMainWindow,
  createPopupManager,
} = require('../main/popup');
const { bootShortcutFor } = require('../main/shortcuts');

const WORK_AREA = { x: 100, y: 40, width: 1920, height: 1040 };

test('popupBoundsFor bottom-right (the schema default) sits inside the work area', () => {
  const b = popupBoundsFor({ workArea: WORK_AREA, position: 'bottom-right' });
  assert.equal(b.width, POPUP_WIDTH);
  assert.equal(b.x + b.width, WORK_AREA.x + WORK_AREA.width - 20, '20px from the right edge');
  assert.equal(b.y + b.height, WORK_AREA.y + WORK_AREA.height - 20, '20px from the bottom edge');
});

test('popupBoundsFor top-centre centres horizontally and hugs the top', () => {
  const b = popupBoundsFor({ workArea: WORK_AREA, position: 'top-center' });
  assert.equal(b.x, WORK_AREA.x + Math.round((WORK_AREA.width - POPUP_WIDTH) / 2));
  assert.equal(b.y, WORK_AREA.y + 20);
});

test('popupBoundsFor: an unknown saved position falls back to the schema default, never off-screen', () => {
  const unknown = popupBoundsFor({ workArea: WORK_AREA, position: 'somewhere-else' });
  const fallback = popupBoundsFor({ workArea: WORK_AREA, position: DEFAULT_POSITION });
  assert.deepEqual(unknown, fallback);
});

test('popupBoundsFor clamps into a tiny work area (the window can never leave the screen)', () => {
  const tiny = { x: 0, y: 0, width: 300, height: 400 };
  const b = popupBoundsFor({ workArea: tiny, position: 'bottom-right' });
  assert.equal(b.x, 0, 'x clamped to the area origin');
  assert.equal(b.y, 0, 'y clamped to the area origin');
});

test('quickAddRequested: the exact --quick-add flag only', () => {
  assert.equal(quickAddRequested(['.', '--quick-add']), true);
  assert.equal(quickAddRequested(['.']), false);
  assert.equal(quickAddRequested(['.', '--quick-addx']), false);
  assert.equal(quickAddRequested(undefined), false);
});

test('shouldParkMainWindow parks only a visible, focused main window', () => {
  assert.equal(shouldParkMainWindow({ focused: true, visible: true }), true);
  assert.equal(shouldParkMainWindow({ focused: false, visible: true }), false, 'another program owns the focus: nothing to park');
  assert.equal(shouldParkMainWindow({ focused: true, visible: false }), false, 'a hidden window is already parked');
  assert.equal(shouldParkMainWindow({}), false);
});

/** A fake BrowserWindow: captures its options, counts creation. */
function fakeBrowserWindowFactory() {
  const windows = [];
  class FakeWindow {
    constructor(opts) {
      this.opts = opts;
      this.bounds = { x: opts.x, y: opts.y, width: opts.width, height: opts.height };
      this.visible = false;
      this.focused = 0;
      this.loaded = null;
      this.listeners = {};
      windows.push(this);
    }
    loadFile(p) {
      this.loaded = p;
    }
    once(ev, cb) {
      this.listeners[ev] = cb;
    }
    fireReadyToShow() {
      if (this.listeners['ready-to-show']) this.listeners['ready-to-show']();
    }
    setBounds(b) {
      this.bounds = { ...this.bounds, ...b };
    }
    show() {
      this.visible = true;
    }
    focus() {
      this.focused += 1;
    }
    hide() {
      this.visible = false;
    }
    isVisible() {
      return this.visible;
    }
    isDestroyed() {
      return false;
    }
    destroy() {}
  }
  return { Ctor: FakeWindow, windows };
}

function fakeScreen() {
  const display = { workArea: WORK_AREA };
  return {
    display,
    getCursorScreenPoint: () => ({ x: 500, y: 500 }),
    getDisplayNearestPoint: () => display,
  };
}

function makeManager({ position = 'bottom-right', screenApi = fakeScreen(), alwaysOnTop = false } = {}) {
  const { Ctor, windows } = fakeBrowserWindowFactory();
  const manager = createPopupManager({
    BrowserWindowCtor: Ctor,
    screenApi,
    pagePath: '/app/renderer/quick.html',
    preloadPath: '/app/preload/preload.js',
    positionFor: () => position,
    alwaysOnTop,
  });
  return { manager, windows };
}

test('the first open creates ONE frameless popup on the display nearest the cursor', () => {
  const { manager, windows } = makeManager();
  const result = manager.show();
  assert.deepEqual(result, { ok: true, created: true });
  assert.equal(windows.length, 1);
  const w = windows[0];
  assert.equal(w.opts.frame, false, 'frameless: Esc is the close affordance');
  assert.equal(w.opts.skipTaskbar, true);
  assert.equal(w.opts.resizable, false);
  assert.equal(w.opts.alwaysOnTop, false, 'the founder-review proposal ships OFF');
  assert.equal(w.opts.webPreferences.contextIsolation, true, 'the same isolation switches as the main window');
  assert.equal(w.opts.webPreferences.nodeIntegration, false);
  assert.equal(w.opts.webPreferences.sandbox, true);
  assert.equal(w.opts.webPreferences.preload, '/app/preload/preload.js', 'the SAME preload allowlist (B5)');
  assert.equal(w.loaded, '/app/renderer/quick.html');
  assert.ok(w.bounds.x >= WORK_AREA.x && w.bounds.y >= WORK_AREA.y, 'inside the work area');
  assert.equal(manager.visible(), false, 'still hidden until ready-to-show');
  assert.equal(manager.createdCount, 1);
});

test('a second open REUSES the window (the draft state survives every hide)', () => {
  const { manager, windows } = makeManager();
  manager.show();
  windows[0].fireReadyToShow(); // the first real display
  manager.hide();
  assert.equal(manager.visible(), false);
  const result = manager.show();
  assert.deepEqual(result, { ok: true, created: false });
  assert.equal(windows.length, 1, 'no second window was ever created');
  assert.equal(windows[0].focused, 2, 'the reused popup is focused again');
  assert.equal(manager.createdCount, 1);
});

test('the position SETTING moves the open (top-centre opens high, then bottom-right low again)', () => {
  const { manager, windows } = makeManager({ position: 'top-center' });
  manager.show();
  windows[0].visible = true;
  const top = { ...windows[0].bounds };
  assert.ok(top.y <= WORK_AREA.y + 20, 'top-centre opens near the top');
  // The manager reads the saved position per open: a settings change
  // applies at the NEXT open, not the current one.
  const { manager: low, windows: lowWin } = makeManager({ position: 'bottom-right' });
  low.show();
  assert.ok(lowWin[0].bounds.y + 560 >= WORK_AREA.y + WORK_AREA.height - 20, 'bottom-right opens near the bottom');
});

test('an unreadable screen falls back to a defined rectangle (never a crash)', () => {
  const { manager } = makeManager({ screenApi: { getCursorScreenPoint: () => { throw new Error('no screen'); }, getDisplayNearestPoint: () => { throw new Error('no screen'); } } });
  const result = manager.show();
  assert.equal(result.ok, true);
});

test('alwaysOnTop: true is passed through (the proposal can be switched after the review)', () => {
  const { manager, windows } = makeManager({ alwaysOnTop: true });
  manager.show();
  assert.equal(windows[0].opts.alwaysOnTop, true);
});

test('bootShortcutFor: nothing registers before first run is done; the saved keys win', () => {
  assert.equal(bootShortcutFor({ knowledgeBasePath: '', quickPopup: { shortcut: 'CommandOrControl+Alt+E' } }), null, 'no knowledge base chosen yet: no boot registration');
  assert.equal(bootShortcutFor({}), null);
  assert.equal(bootShortcutFor(undefined), null);
  assert.equal(bootShortcutFor({ knowledgeBasePath: '/x/ember.db', quickPopup: { shortcut: 'CommandOrControl+Alt+K' } }), 'CommandOrControl+Alt+K', 'the founder\u2019s saved choice is what boots');
  assert.equal(bootShortcutFor({ knowledgeBasePath: '/x/ember.db' }), 'CommandOrControl+Alt+E', 'an unreadable quickPopup shape falls back to the spec \u00a710 default');
  assert.equal(bootShortcutFor({ knowledgeBasePath: '/x/ember.db', quickPopup: { shortcut: '   ' } }), 'CommandOrControl+Alt+E');
});

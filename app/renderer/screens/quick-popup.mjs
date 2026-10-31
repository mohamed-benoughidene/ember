/**
 * The quick popup's page (app step 11, ticket A40; plan §5.5, spec
 * stories 90-95).
 *
 * The popup is Add ONLY (story 91) and reuses the SAME Add screen —
 * the step-05 `createAddScreen(ctx)`, the step-03 components and the
 * step-05 confirm-session pipeline (`ember:addStart/Answer/Stop`)
 * through the SAME preload allowlist (B5) — in a smaller window
 * (DESIGN.md: "a 440px window with only Add and a path to the full
 * window"). No Add logic lives here; this page only decides:
 *  - the header's "Open Ember" link (story 93);
 *  - the setup-needed state when Ember itself is not set up yet, and
 *    the path to fix it (story 94; the no-key case is the Add screen's
 *    own state, its button lands on the same path);
 *  - Esc closes the popup (form/error/done phases) or stops the
 *    session (the Add screen's own Esc, story 92 — same keys as the
 *    full window), the step file's close default "on Esc or after
 *    Stop";
 *  - after the stopped end state the popup closes by itself; the rest
 *    of the close/draft rules ride the window manager's hide (the page
 *    keeps its state until the next open, so an accidental Esc keeps
 *    the draft).
 */

import { buttonHtml } from '../components/button.mjs';
import { textScale } from '../design/text-scale.mjs';
import { addStage } from '../../shared/confirm-view.mjs';
import { createAddScreen } from './add.mjs';

const paneEl = document.getElementById('pane');

let screen = null; // the Add screen instance, or null until the gate passes
let stopWatcher = null; // the MutationObserver that closes the popup after Stop

/** Appearance follows the same settings rules as the main window (81-84). */
function applyAppearance(settings) {
  const { textSize, colourTheme } = settings;
  const px = textScale(textSize.charAt(0).toUpperCase() + textSize.slice(1));
  document.documentElement.style.fontSize = `${px}px`;
  document.documentElement.classList.toggle('big', px >= 22);
  if (colourTheme === 'system') {
    const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  } else {
    document.documentElement.dataset.theme = colourTheme;
  }
}

function renderFrame(html, wire) {
  paneEl.innerHTML = html;
  if (typeof wire === 'function') wire(paneEl);
}

/** The "Ember is not set up yet" state (story 94), with its one fix path. */
function renderSetupNeeded() {
  screen = null;
  renderFrame(
    `<div class="panel tone"><div class="pad" data-testid="quick-setup-needed">
      <p class="lbl">Ember is not set up yet</p>
      <p class="help">The quick add needs your knowledge base file. Open Ember once, finish the setup, and this little window will add straight into it.</p>
    </div></div>
    <div class="actions">${buttonHtml({ label: 'Open Ember', action: 'quick-open-main-setup', variant: 'primary', testid: 'quick-open-main-setup' })}</div>`,
    (root) => {
      root.querySelector('[data-action="quick-open-main-setup"]')?.addEventListener('click', () => void openMain('ember'));
    },
  );
}

/** Story 93/94: go to the full window (optionally its setup) and close the popup. */
async function openMain(view) {
  const res = await window.ember.quickOpenMain({ view });
  if (res && res.ok) await window.ember.openQuickPopup({ action: 'hide' });
}

/** Esc closes the popup, EXCEPT mid-session where it stops the add (story 92). */
function installEscClose() {
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    if (screen && screen.state.phase === 'session') return; // the Add screen's Esc: stop
    ev.preventDefault();
    void window.ember.openQuickPopup({ action: 'hide' });
  });
}

/** The step file's other close default: the popup closes after Stop. */
function watchForStopped() {
  if (stopWatcher) return;
  stopWatcher = new MutationObserver(() => {
    if (!screen) return;
    if (document.querySelector('[data-testid="add-stopped-line"]')) {
      void window.ember.openQuickPopup({ action: 'hide' });
    }
  });
  stopWatcher.observe(paneEl, { childList: true, subtree: true });
}

/**
 * The gate: the same kbStatus read the main window's Add gate uses.
 * A knowledge base that does not EXIST yet is fine for Add (the first
 * add creates it) — only a not-CHOSEN one (first run pending) stops
 * the popup, with story 94's words and path.
 */
async function kbGate() {
  const status = await window.ember.kbStatus();
  if (status.exists) return status.looksValid ? 'ok' : 'invalid';
  const chosen = await window.ember.getState();
  return typeof chosen.effectiveKbPath === 'string' && chosen.effectiveKbPath !== '' ? 'nosuch-create' : 'nosuch';
}

const ctx = {
  api: window.ember,
  state: null,
  params: null,
  paneEl: () => paneEl,
  renderFrame,
  navigate: () => void openMain('ember'),
  openSetup: () => void openMain('setup'),
  gate: kbGate,
};

/** The full (re)build: boot snapshot, appearance, gate, Add screen. */
async function refresh() {
  const state = await window.ember.getState();
  ctx.state = state;
  applyAppearance(state.settings);
  const gate = await kbGate();
  if (gate === 'nosuch') {
    renderSetupNeeded();
    return;
  }
  if (!screen) {
    screen = createAddScreen(ctx);
  }
  screen.render(); // draft-safe: the Add screen keeps state.text across renders
}

/**
 * Re-check what can change while the popup was hidden: the founder may
 * have finished first run or set the key in the main window. Only a
 * not-yet-built page or a form/error state rebuilds — never a running
 * session, never the Saved so far list (the Add screen keeps its own
 * draft text across renders, state.text).
 */
function rebuildIfSafe() {
  if (!screen) return refresh();
  if (screen.state.phase !== 'form' && screen.state.phase !== 'error') return;
  return screen.render();
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  void rebuildIfSafe().catch(() => {
    /* the seam is not up (boot not finished); the next open retries */
  });
});

/** The real end states come from the events alone (D3); 'stopped' hides. */
function stageNow() {
  return screen ? addStage(screen.state.view) : null;
}

void (async () => {
  document.querySelector('[data-testid="quick-open-main"]').addEventListener('click', () => void openMain('ember'));
  installEscClose();
  await refresh();
  watchForStopped();
  // The stage guard covers the exit that lands after the stopped line
  // renders (the MutationObserver catches the DOM; this catches a
  // re-render that reuses the same node).
  setInterval(() => {
    if (stageNow() === 'stopped' && screen && screen.state.phase === 'done') {
      void window.ember.openQuickPopup({ action: 'hide' });
    }
  }, 300);
})();

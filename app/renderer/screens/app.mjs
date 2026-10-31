/**
 * The app entry (L3 app step 04): boot, the sidebar, and the pane
 * router. Uses ONLY the window.ember preload allowlist — no Node, no
 * Electron (asserted by test/preload-allowlist.test.js).
 *
 * Boot: getState once (I13) -> apply the text size and colours from
 * the settings -> show the boot/settings notices as a banner with the
 * code behind "Details" (no bare code on screen) -> first run if no
 * knowledge base is chosen, else the remembered pane.
 */

import { textScale } from '../design/text-scale.mjs';
// [app 10] the real Settings screen replaces the interim placeholder
import { createSettingsScreen } from './settings.mjs';
import { bannerHtml } from '../components/banner.mjs';
import { sentenceFor } from '../../shared/plain-sentences.mjs';
import { createFirstRunScreen } from './first-run.mjs';
import { createHomeScreen } from './home.mjs';
import { createLookupScreen } from './lookup.mjs';
// App step 09 (Keep safe) — added as its own import line (ticket A38).
import { createKeepSafeScreen } from './keepsafe.mjs';
import { createPlaceholderScreen, paneNames } from './placeholder.mjs';
// app step 07 (Fix and close) — registered additively; nothing above moved.
import { createFixCloseScreen } from './fix-close.mjs';
// --- App 08 (Clean up): screen registration import (additive; ticket A37) ---
import { createCleanupScreen } from './cleanup.mjs';
// --- App 08 import ends ---
import { createAddScreen } from './add.mjs'; /* App 05 (ticket A34) */
// app step 06 (Link items) — registered additively; nothing above moved.
import { createLinkScreen } from './link.mjs'; /* App 06 (ticket A35) */

const JOBS = [
  { id: 'home', name: 'Home', hint: 'What needs attention', fixed: true },
  { id: 'add', name: 'Add', hint: 'Turn text into items' },
  { id: 'lookup', name: 'Look up', hint: 'Search items and the ledger' },
  { id: 'link', name: 'Link items', hint: 'Connect related items' },
  { id: 'fix', name: 'Fix and close', hint: 'Change status, edit, undo' },
  { id: 'cleanup', name: 'Clean up', hint: 'Update statuses (sweep)' },
  { id: 'keepsafe', name: 'Keep safe', hint: 'Backup, export, health check' },
  { id: 'settings', name: 'Settings', hint: 'Text size, colours, shortcut', fixed: true },
];

const screens = {}; // id -> screen instance (created lazily, state kept per pane)
let bootState = null;
let firstRunActive = false;
let kbGatePromise = null;

const navEl = document.getElementById('nav');
const paneEl = document.getElementById('pane');
const bannerEl = document.getElementById('top-banner');

const ctx = {
  api: window.ember,
  state: null,
  params: null,
  paneEl: () => paneEl,
  renderFrame(html, wire) {
    paneEl.innerHTML = html;
    if (typeof wire === 'function') wire(paneEl);
    paneEl.focus({ preventScroll: true });
  },
  navigate(id, params = null) {
    ctx.params = params;
    // [app 10] the settings screen retitles the window to name its
    // open pane (story 80); every other pane carries the plain title.
    document.title = 'Ember';
    if (!firstRunActive) {
      navEl.querySelectorAll('button').forEach((b) => b.setAttribute('aria-current', b.dataset.job === id ? 'true' : 'false'));
      window.ember.saveSettings({ lastPane: id }).catch(() => {});
    }
    renderPane(id);
  },
  firstRunDone() {
    firstRunActive = false;
    document.body.classList.remove('first-run');
    navEl.hidden = false;
  },
  openSetup() {
    firstRunActive = true;
    document.body.classList.add('first-run');
    navEl.hidden = true;
    firstRun().refresh();
  },
  /** The knowledge-base gate, computed once per boot ('ok'|'nosuch'|'invalid'). */
  async gate() {
    if (kbGatePromise === null) {
      kbGatePromise = (async () => {
        const status = await window.ember.kbStatus();
        if (!status.exists) return 'nosuch';
        return status.looksValid ? 'ok' : 'invalid';
      })();
    }
    return kbGatePromise;
  },
};

// [app 10] the re-appliers the Settings screen drives after it saves
// (its changes must apply at once: stories 82-88) and the Comma
// shortcut that opens Settings from any pane (story 79).
ctx.applySettingsNow = () => applySettings();
ctx.rebuildNav = () => buildNav();
document.addEventListener('keydown', (event) => {
  if (event.key !== ',' || !(event.metaKey || event.ctrlKey)) return;
  if (firstRunActive) return;
  event.preventDefault();
  ctx.navigate('settings');
});

/* --- App 08 (Clean up): the pending-count badge on the sidebar job
   (story 68; plan §1: shown only when the last preview count > 0,
   refreshed after any write; the number is a real `maintain --dry-run`
   count handed up by the Clean up screen — never recomputed here). --- */
function mountCleanupBadge() {
  const button = navEl.querySelector('button[data-job="cleanup"]');
  if (!button || button.querySelector('[data-testid="cleanup-badge"]')) return;
  const badge = document.createElement('span');
  badge.className = 'count';
  badge.setAttribute('data-testid', 'cleanup-badge');
  badge.setAttribute('aria-label', '0 changes pending');
  badge.hidden = true;
  button.appendChild(badge);
}

ctx.setCleanupBadge = (count) => {
  mountCleanupBadge();
  const badge = navEl.querySelector('[data-testid="cleanup-badge"]');
  if (!badge) return;
  const n = typeof count === 'number' && Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
  badge.hidden = n === 0;
  badge.textContent = String(n);
  badge.setAttribute('aria-label', `${n} ${n === 1 ? 'change' : 'changes'} pending`);
};
/* --- App 08 badge block ends --- */

/* --- App 08 (Clean up) registration: renderCleanupPane is a named
   function so the router branch stays one line. The branch must sit
   BEFORE the placeholder router below, because the interim pane list
   still carries 'cleanup' (placeholder.mjs is untouched). --- */
function renderCleanupPane() {
  screens.cleanup = createCleanupScreen(ctx);
  screens.cleanup.render();
}
// --- App 08 registration ends ---

function renderPane(id) {
  // [app 10] Settings is a real screen now; the other interim panes
  // keep their honest placeholders until their build steps.
  if (id === 'settings') {
    screens.settings = createSettingsScreen(ctx);
    screens.settings.refresh();
    return;
  }
  if (id === 'home') {
    screens.home = createHomeScreen(ctx);
    screens.home.render();
    return;
  }
  if (id === 'lookup') {
    screens.lookup = createLookupScreen(ctx);
    screens.lookup.render();
    return;
  }
  /* ==== App 05 (ticket A34): the real Add screen ================ */
  if (id === 'add') {
    screens.add = createAddScreen(ctx);
    screens.add.render();
    return;
  }
  /* ==== end App 05 block ==== */
  /* =================================================================
   * APP STEP 09 (Keep safe) — this step's own clearly-bracketed
   * block (ticket A38). It sits DIRECTLY ABOVE the placeholder
   * catch-all because that catch-all answers for `keepsafe` too;
   * placed after it, the real screen would be unreachable.
   * ================================================================= */
  if (id === 'keepsafe') {
    screens.keepsafe = createKeepSafeScreen(ctx);
    screens.keepsafe.render();
    return;
  }
  // app step 07 (Fix and close): the real screen replaces the interim pane.
  if (id === 'fix') {
    screens.fix = createFixCloseScreen(ctx);
    screens.fix.render();
    return;
  }
  // --- App 08 (Clean up): the real screen replaces the interim pane
  // (additive branch; ticket A37). This branch sits BEFORE the
  // placeholder router below.
  if (id === 'cleanup') {
    renderCleanupPane();
    return;
  }
  // --- App 08 branch ends ---
  /* =================================================================
   * APP STEP 06 (Link items) — this step's own clearly-bracketed
   * block (ticket A35), directly above the placeholder catch-all
   * (which would otherwise answer for `link` first).
   * ================================================================= */
  if (id === 'link') {
    screens.link = createLinkScreen(ctx);
    screens.link.render();
    return;
  }
  // -------------------------------------------------------------------
  if (paneNames().includes(id)) {
    createPlaceholderScreen(ctx, id).render();
    return;
  }
  createPlaceholderScreen(ctx, 'add').render(); // an unknown id never blanks the pane
}

function buildNav() {
  const order = [];
  for (const job of JOBS) if (job.fixed) order.push(job);
  const menuOrder = bootState.settings.menuOrder ?? [];
  for (const id of menuOrder) {
    const job = JOBS.find((j) => j.id === id);
    if (job && !order.includes(job)) order.push(job);
  }
  for (const job of JOBS) if (!order.includes(job)) order.push(job);
  const hidden = new Set(bootState.settings.menuHidden ?? []);
  navEl.innerHTML = order
    .filter((job) => job.fixed || !hidden.has(job.id))
    .map(
      (job) =>
        `<button type="button" data-job="${job.id}">
          <span class="t">${job.name}<small>${job.hint}</small></span>
        </button>`,
    )
    .join('');
  navEl.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => ctx.navigate(button.dataset.job));
  });
}

function applySettings() {
  const { textSize, colourTheme } = bootState.settings;
  const px = textScale(textSize.charAt(0).toUpperCase() + textSize.slice(1));
  document.documentElement.style.fontSize = `${px}px`;
  // The Text Size Rule (DESIGN.md): at Larger/Largest the sidebar
  // narrows to 11rem, hides its hints, and rows and notices wrap —
  // the prototype's :root.big state.
  document.documentElement.classList.toggle('big', px >= 22);
  if (colourTheme === 'system') {
    const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  } else {
    document.documentElement.dataset.theme = colourTheme;
  }
}

function showNotices() {
  const notices = [bootState.settingsNotice, bootState.bootNotice].filter(Boolean);
  if (notices.length === 0) {
    bannerEl.innerHTML = '';
    return;
  }
  const error = notices[0];
  const sentence = sentenceFor(error.code);
  bannerEl.innerHTML = `${bannerHtml({
    text: `${sentence.what} ${sentence.next}`,
    actionLabel: 'Details',
    action: 'notice-details',
  })}<p class="help mono" data-testid="notice-code" hidden style="padding:0 var(--s6)">${`${error.code} ${error.name} | ${error.detail}`}</p>`;
  bannerEl.querySelector('[data-action="notice-details"]')?.addEventListener('click', () => {
    const code = bannerEl.querySelector('[data-testid="notice-code"]');
    if (code) code.hidden = !code.hidden;
  });
}

/** First run opens when no knowledge-base path is chosen (story 1). */
function firstRun() {
  screens.firstRun = createFirstRunScreen(ctx);
  firstRunActive = true;
  document.body.classList.add('first-run');
  navEl.hidden = true;
  return screens.firstRun;
}

async function boot() {
  bootState = await window.ember.getState();
  ctx.state = bootState;
  applySettings();
  showNotices();
  buildNav();
  const kbChosen = typeof bootState.effectiveKbPath === 'string' && bootState.effectiveKbPath !== '';
  if (kbChosen) {
    navEl.hidden = false;
    ctx.navigate(bootState.settings.lastPane ?? 'home');
  } else {
    firstRun().refresh();
  }
}

boot().catch(() => {
  // Never a blank screen: the boot path itself failing is the last
  // resort message (the seam answered in step 02's smoke; this is the
  // renderer-side guard).
  paneEl.innerHTML = `<div class="errbox" role="alert"><strong>Ember could not start.</strong>
    <span class="detail">The window could not reach the app core. Close and reopen Ember.</span></div>`;
});

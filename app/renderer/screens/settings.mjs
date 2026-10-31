/**
 * The Settings screen (app step 10, spec stories 78-89, DESIGN.md
 * "Settings"). Five tabs in one tab row: the four decision-8 panes —
 * Appearance, Quick popup, Menu, AI connection — plus the knowledge
 * base file pane (the route step 09 refers to: "switch back in
 * Settings or the menu"; see archive/interface-deviations.md).
 *
 * Rules this screen lives by:
 *  - every change saves itself and shows a quiet "Saved." (81); there
 *    is no Save button, except where a story needs one explicit
 *    action (the key save, the captured shortcut);
 *  - a change applies AT ONCE: text size and colours re-apply to the
 *    running window, the sidebar rebuilds from the menu settings;
 *  - the window title names the open pane, and the shell remembers
 *    the last pane (80);
 *  - the key is shown only MASKED — how it ends, never the whole key —
 *    and remove is previewed and named before it acts (89, No Modal
 *    First Rule);
 *  - the APP-003 weak-keyring offer ("use for this session only") and
 *    the APP-005 shortcut refusal with the tray fallback come through
 *    unchanged from the stores and the shortcut seam;
 *  - everything reachable by keyboard, buttons only, with the global
 *    focus ring (96-101).
 *
 * Uses ONLY the window.ember preload list (B5/T9) — no Node, no
 * Electron.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { loadingHtml } from '../components/state-block.mjs';
import { checkKeyShape } from '../../shared/key-shape.mjs';
import { acceleratorWarnings, parseAccelerator, displayKeys } from '../../shared/shortcut-warnings.mjs';

const IS_MAC = /Mac/i.test(navigator.platform ?? '');

/** The four decision-8 panes + the knowledge-base file pane. */
export const SETTING_PANES = [
  { id: 'appearance', name: 'Appearance' },
  { id: 'popup', name: 'Quick popup' },
  { id: 'menu', name: 'Menu' },
  { id: 'ai', name: 'AI connection' },
  { id: 'kbfile', name: 'Knowledge base file' },
];

/** The movable jobs of the Menu pane (Home and Settings are fixed, 88). */
export const MENU_JOBS = [
  { id: 'add', name: 'Add' },
  { id: 'lookup', name: 'Look up' },
  { id: 'link', name: 'Link items' },
  { id: 'fix', name: 'Fix and close' },
  { id: 'cleanup', name: 'Clean up' },
  { id: 'keepsafe', name: 'Keep safe' },
];

const TEXT_CHOICES = [
  { value: 'small', name: 'Small' },
  { value: 'default', name: 'Default' },
  { value: 'large', name: 'Large' },
  { value: 'larger', name: 'Larger' },
  { value: 'largest', name: 'Largest' },
];

const THEME_CHOICES = [
  { value: 'system', name: 'System' },
  { value: 'light', name: 'Light' },
  { value: 'dark', name: 'Dark' },
];

const POSITION_CHOICES = [
  { value: 'top-center', name: 'Top centre' },
  { value: 'bottom-right', name: 'Bottom right' },
];

const DEFAULT_SHORTCUT = 'CommandOrControl+Alt+E';

/** The shown name of a pane id; an unknown id falls back (never blank). */
function paneName(id) {
  return (SETTING_PANES.find((p) => p.id === id) ?? SETTING_PANES[0]).name;
}

/** The job list in shown order, menuOrder first, unknown ids dropped. */
export function menuOrderForDisplay(menuOrder) {
  const order = [];
  for (const id of Array.isArray(menuOrder) ? menuOrder : []) {
    const job = MENU_JOBS.find((j) => j.id === id);
    if (job && !order.includes(job)) order.push(job);
  }
  for (const job of MENU_JOBS) if (!order.includes(job)) order.push(job);
  return order;
}

/** One job moved up or down; the ends clamp without changing the rest. */
export function moveJob(order, id, direction) {
  const list = order.map((j) => j.id);
  const index = list.indexOf(id);
  const target = index + (direction === 'up' ? -1 : 1);
  if (index === -1 || target < 0 || target >= list.length) return order;
  [list[index], list[target]] = [list[target], list[index]];
  return menuOrderForDisplay(list);
}

/** The hidden set gains or loses one job. */
export function toggleJobHidden(hidden, id) {
  return hidden.includes(id) ? hidden.filter((h) => h !== id) : [...hidden, id];
}

export function createSettingsScreen(ctx) {
  const state = {
    pane: 'appearance',
    saved: false, // the quiet "Saved." marker (81)
    error: null, // {title, detail} shown where it happened
    aiStatus: null, // {stored, sessionOnly, backend} once read
    aiHint: null, // the key's last four characters, or null
    aiLoading: true,
    aiStatusError: false,
    replaceOpen: false,
    showKey: false,
    key: '',
    offerSession: false, // the APP-003 offer, until used or dismissed
    removeConfirm: false,
    capturing: false, // capturing the new popup keys
    candidate: null, // the captured accelerator, before saving
    kbPath: '',
    kbStatus: null, // {path, exists, looksValid} for the shown path
    kbLoading: true,
  };
  // The shell's live settings object (bootState); save() mutates it in
  // place, so the HTML always reads the current values through it.
  state.settings = ctx.state.settings;

  let refreshToken = 0; // a render invalidates in-flight state loads
  let captureAbort = null; // the capture key listener lives one render

  const refresh = () => {
    if (captureAbort) captureAbort.abort();
    ctx.renderFrame(settingsHtml(state), wire);
    document.title = `Ember — Settings — ${paneName(state.pane)}`;
  };

  function clearQuiet() {
    state.saved = false;
    state.error = null;
  }

  function showSaved() {
    state.saved = true;
    state.error = null;
  }

  function showError(title, detail) {
    state.saved = false;
    state.error = { title, detail };
  }

  /** Save through the store; returns the new settings or null (shown inline). */
  async function save(patch) {
    const result = await ctx.api.saveSettings(patch);
    if (!result || !result.ok) {
      showError('Your settings could not be saved.', result && result.error ? result.error.detail : 'Try again.');
      refresh();
      return null;
    }
    // The shell reads the same object (bootState === ctx.state), so the
    // re-appliers below see the new values.
    Object.assign(ctx.state.settings, result.settings);
    return result.settings;
  }

  async function loadAiStatus() {
    const token = ++refreshToken;
    state.aiLoading = true;
    state.aiStatusError = false;
    refresh();
    try {
      const [status, hint] = await Promise.all([ctx.api.keyStatus(), ctx.api.keyHint()]);
      if (token !== refreshToken) return; // the user moved on; drop it
      state.aiStatus = status;
      state.aiHint = hint && hint.ok ? hint.hint : null;
    } catch {
      if (token !== refreshToken) return;
      state.aiStatus = null;
      state.aiHint = null;
      state.aiStatusError = true;
    }
    state.aiLoading = false;
    refresh();
  }

  async function loadKbStatus() {
    const token = ++refreshToken;
    state.kbLoading = true;
    refresh();
    state.kbPath = ctx.state.effectiveKbPath || ctx.state.settings.knowledgeBasePath || '';
    const status = await ctx.api.kbStatus();
    if (token !== refreshToken) return;
    state.kbStatus = status;
    state.kbLoading = false;
    refresh();
  }

  async function wire(root) {
    // The popup-key capture: a window listener that lives until the
    // next render or Esc (story 85).
    if (captureAbort) captureAbort.abort();
    captureAbort = new AbortController();
    window.addEventListener('keydown', (event) => {
      if (!state.capturing) return;
      const key = eventKey(event);
      if (event.key === 'Escape') {
        event.preventDefault();
        state.capturing = false;
        state.candidate = null;
        refresh();
        return;
      }
      if (key === null) return; // a lone modifier: keep waiting
      event.preventDefault();
      state.capturing = false;
      state.candidate = acceleratorFromEvent(event, key);
      refresh();
    }, { signal: captureAbort.signal, capture: true });

    const on = (action, fn) => {
      root.querySelector(`[data-action="${action}"]`)?.addEventListener('click', fn);
    };

    // Tab switching: click, or ArrowLeft/ArrowRight walked by keyboard.
    root.querySelectorAll('[role="tab"]').forEach((tab) => {
      tab.addEventListener('click', () => switchPane(tab.dataset.pane));
    });
    root.querySelector('[role="tablist"]')?.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const tabs = [...root.querySelectorAll('[role="tab"]')];
      const index = tabs.findIndex((t) => t.dataset.pane === state.pane);
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
      tabs[next].click();
      tabs[next].focus();
    });

    /* ---- Appearance (82-84) ---- */
    root.querySelectorAll('[data-set="textSize"], [data-set="colourTheme"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const settings = await save({ [button.dataset.set]: button.dataset.value });
        if (settings === null) return;
        showSaved();
        ctx.applySettingsNow?.();
        refresh();
      });
    });

    /* ---- Quick popup (85-86) ---- */
    on('popup-capture', () => {
      state.capturing = true;
      state.candidate = null;
      clearQuiet();
      refresh();
    });
    on('popup-reset', () => saveShortcut(DEFAULT_SHORTCUT));
    on('popup-save-candidate', () => { saveShortcut(state.candidate); });
    root.querySelectorAll('select[data-set="quickPopupPosition"]').forEach((select) => {
      select.addEventListener('change', async () => {
        const current = ctx.state.settings.quickPopup;
        const settings = await save({ quickPopup: { shortcut: current.shortcut, position: select.value } });
        if (settings === null) return;
        showSaved();
        refresh();
      });
    });

    /* ---- Menu (87-88) ---- */
    root.querySelectorAll('input[data-menu="toggle"]').forEach((box) => {
      box.addEventListener('change', async () => {
        const settings = ctx.state.settings;
        const menuHidden = toggleJobHidden([...settings.menuHidden], box.dataset.id);
        const saved = await save({ menuOrder: menuOrderForDisplay(settings.menuOrder).map((j) => j.id), menuHidden });
        if (saved === null) return;
        showSaved();
        ctx.rebuildNav?.();
        refresh();
      });
    });
    root.querySelectorAll('button[data-menu="move"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const settings = ctx.state.settings;
        const order = moveJob(menuOrderForDisplay(settings.menuOrder), button.dataset.id, button.dataset.dir);
        const saved = await save({ menuOrder: order.map((j) => j.id), menuHidden: [...settings.menuHidden] });
        if (saved === null) return;
        showSaved();
        ctx.rebuildNav?.();
        refresh();
      });
    });

    /* ---- AI connection (89) ---- */
    on('ai-retry-status', loadAiStatus);
    on('ai-replace', () => {
      state.replaceOpen = true;
      state.removeConfirm = false;
      state.offerSession = false;
      state.key = '';
      state.showKey = false;
      clearQuiet();
      refresh();
    });
    on('ai-replace-cancel', () => {
      state.replaceOpen = false;
      state.offerSession = false;
      state.key = '';
      refresh();
    });
    const keyInput = root.querySelector('[data-testid="settings-key-input"]');
    if (keyInput) {
      keyInput.value = state.key;
      keyInput.addEventListener('input', () => {
        state.key = keyInput.value;
      });
    }
    on('ai-show-key', () => {
      state.showKey = !state.showKey;
      refresh();
    });
    on('ai-save-key', async () => {
      const shape = checkKeyShape(state.key);
      if (!shape.ok) {
        showError('The key was not saved.', keyShapeWords(shape.reason));
        refresh();
        return;
      }
      const saved = await ctx.api.setKey(state.key);
      if (saved && saved.ok) {
        state.replaceOpen = false;
        state.offerSession = false;
        state.key = '';
        showSaved();
        loadAiStatus();
        return;
      }
      if (saved && saved.error && saved.error.code === 'APP-003') {
        // Decision 4-A: no keyring, never a plain file — the
        // session-only offer is the only way forward (plan §5.4).
        state.offerSession = true;
        showError('The key was NOT saved on disk.', `${saved.error.detail} You can keep the key for this session only: it stays in memory and is gone when you close Ember.`);
        refresh();
        return;
      }
      showError('The key could not be saved.', saved && saved.error ? saved.error.detail : 'Try again.');
      refresh();
    });
    on('ai-session-key', async () => {
      const kept = await ctx.api.setSessionKey(state.key);
      if (kept && kept.ok) {
        state.replaceOpen = false;
        state.offerSession = false;
        state.key = '';
        showSaved();
        loadAiStatus();
      } else {
        showError('The key could not be kept.', kept && kept.error ? kept.error.detail : 'Try pasting it again.');
        refresh();
      }
    });
    on('ai-remove', () => {
      // Careful action (89): preview first, name the object, offer Cancel.
      state.removeConfirm = true;
      state.replaceOpen = false;
      clearQuiet();
      refresh();
    });
    on('ai-remove-cancel', () => {
      state.removeConfirm = false;
      refresh();
    });
    on('ai-remove-confirm', async () => {
      const removed = await ctx.api.removeKey();
      if (removed && removed.ok) {
        state.removeConfirm = false;
        showSaved();
        loadAiStatus();
      } else {
        showError('The key could not be removed.', removed && removed.error ? removed.error.detail : 'Try again.');
        refresh();
      }
    });

    /* ---- Knowledge base file ---- */
    on('kb-retry', loadKbStatus);
    on('kb-open-setup', () => ctx.openSetup());
    on('kb-browse', async () => {
      // The picker refuses a non-Ember file itself (APP-006 at the edge).
      const chosen = await ctx.api.pickKnowledgeBaseFile();
      if (chosen && chosen.ok && typeof chosen.path === 'string') {
        state.kbPath = chosen.path;
        await saveKnowledgeBasePath(await ctx.api.kbStatus(chosen.path));
      } else if (chosen && chosen.error) {
        showError('That file is not a knowledge base.', `${chosen.error.detail} (code ${chosen.error.code})`);
        refresh();
      }
    });
    const kbInput = root.querySelector('[data-testid="settings-kb-input"]');
    if (kbInput) {
      kbInput.value = state.kbPath;
      kbInput.addEventListener('input', () => {
        state.kbPath = kbInput.value;
      });
    }
    on('kb-use', async () => {
      const path = (state.kbPath ?? '').trim();
      if (path === '') {
        showError('Choose where the knowledge base file goes.', 'Type the full location of the file, or use the file picker.');
        refresh();
        return;
      }
      // Verify BEFORE the settings change: an existing file must be an
      // Ember knowledge base (APP-006); a file that does not exist yet
      // is allowed — it is created at the first Add.
      const status = await ctx.api.kbStatus(path);
      if (status.exists && !status.looksValid) {
        showError('That file is not an Ember knowledge base.', 'The file exists but does not read as one. Choose a different file; your settings were left unchanged. (code APP-006)');
        refresh();
        return;
      }
      state.kbPath = path;
      await saveKnowledgeBasePath(status);
    });

    async function saveKnowledgeBasePath(status) {
      const settings = await save({ knowledgeBasePath: state.kbPath });
      if (settings === null) return;
      state.kbStatus = status ?? (await ctx.api.kbStatus(state.kbPath));
      showSaved();
      refresh();
    }

    async function saveShortcut(accelerator) {
      const parsed = parseAccelerator(accelerator ?? '');
      if (!parsed.ok) {
        showError('The keys were not read as a shortcut.', 'Set the keys again.');
        refresh();
        return;
      }
      const settings = await save({ quickPopup: { shortcut: accelerator, position: ctx.state.settings.quickPopup.position } });
      if (settings === null) return;
      // The choice persists first; the OS may still refuse it (APP-005;
      // the shell has built the tray fallback). Both outcomes are
      // honest words on the pane.
      const registered = await ctx.api.registerShortcut(accelerator);
      state.capturing = false;
      state.candidate = null;
      if (registered && registered.ok) {
        showSaved();
      } else {
        showError('The keyboard shortcut was refused.', 'Another program may already use it. The tray icon and the Add screen still work. Your choice was saved and is tried again next time Ember starts.');
      }
      refresh();
    }
  }

  function switchPane(pane) {
    if (pane === state.pane || !SETTING_PANES.some((p) => p.id === pane)) return;
    state.pane = pane;
    clearQuiet();
    state.replaceOpen = false;
    state.removeConfirm = false;
    state.capturing = false;
    state.candidate = null;
    state.offerSession = false;
    state.key = '';
    refresh();
    // Keyboard tab switching (roving focus): the selected tab keeps the
    // focus after the re-render, so Arrow keys keep walking.
    document.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    if (pane === 'ai') loadAiStatus();
    if (pane === 'kbfile') loadKbStatus();
  }

  return { state, refresh };
}

/* ---------- pure pieces (unit-tested without a DOM) ---------- */

/** The non-modifier key of a keyboard event; null while only modifiers
 *  are held (the capture keeps waiting). */
export function eventKey(event) {
  if (['Control', 'Alt', 'AltGraph', 'Shift', 'Meta', 'CapsLock'].includes(event.key)) return null;
  if (event.key.length === 1) return event.key;
  return event.key;
}

/** An Electron accelerator string from a captured keydown. On a Mac a
 *  pressed Control stays Control (the pane then warns); elsewhere it
 *  is CommandOrControl, so the choice works the same on every system. */
export function acceleratorFromEvent(event, key, isMac) {
  const mac = isMac ?? /Mac/i.test(navigator.platform ?? '');
  const mods = [];
  if (event.ctrlKey) mods.push(mac ? 'Control' : 'CommandOrControl');
  if (event.altKey) mods.push('Alt');
  if (event.shiftKey) mods.push('Shift');
  if (event.metaKey) mods.push('Command');
  const normalized = key.length === 1 ? key.toUpperCase() : key;
  if (mods.length === 0) return normalized;
  return `${mods.join('+')}+${normalized}`;
}

function keyShapeWords(reason) {
  if (reason === 'empty') return 'The key box is empty. Paste your key, then save it.';
  if (reason === 'whitespace') return 'A key is one unbroken line of characters. This one has a space or a line break inside; copy it again completely.';
  return 'This key is too short. A real key has at least 20 characters with no spaces; copy it again completely.';
}

/* ---------- HTML ---------- */

function settingsHtml(state) {
  const modal = IS_MAC ? 'Command' : 'Ctrl';
  const tabs = SETTING_PANES.map(
    (pane) =>
      `<button type="button" role="tab" data-pane="${pane.id}" aria-selected="${pane.id === state.pane}" aria-controls="settings-panel">${esc(pane.name)}</button>`,
  ).join('');
  const savedHtml = `<p class="saved" role="status" data-testid="settings-saved">${state.saved ? 'Saved.' : ''}</p>`;
  const errorHtmlBlock = state.error
    ? `<div class="errbox" role="alert" data-testid="settings-error"><strong>${esc(state.error.title)}</strong><span class="detail">${esc(state.error.detail)}</span></div>`
    : '';
  let body = '';
  if (state.pane === 'appearance') body = appearanceHtml(state);
  else if (state.pane === 'popup') body = popupHtml(state);
  else if (state.pane === 'menu') body = menuHtml(state);
  else if (state.pane === 'ai') body = aiHtml(state);
  else body = kbfileHtml(state);
  return `<div data-testid="pane-settings">
    <div class="titlerow"><div class="grow"><h1>Settings</h1>
      <p class="sub">Opens with ${modal}+Comma. Every change saves itself.</p></div></div>
    ${savedHtml}
    <div class="tabs settings-tabs" role="tablist" aria-label="Settings panes">${tabs}</div>
    <div id="settings-panel" role="tabpanel" aria-label="${esc(paneName(state.pane))}" data-testid="settings-${state.pane}">${body}${errorHtmlBlock}</div>
  </div>`;
}

function paneRow(title, description, controlHtml) {
  return `<div class="setrow"><div class="l"><b>${esc(title)}</b><span>${esc(description)}</span></div><div class="r">${controlHtml}</div></div>`;
}

function segmented(name, choices, current, setKey) {
  return `<div class="seg" role="group" aria-label="${esc(name)}">${choices
    .map(
      (choice) =>
        `<button type="button" data-set="${setKey}" data-value="${choice.value}" aria-pressed="${choice.value === current ? 'true' : 'false'}">${esc(choice.name)}</button>`,
    )
    .join('')}</div>`;
}

function appearanceHtml(state) {
  const settings = state.settings;
  return `${paneRow(
    'Text size',
    'Makes writing smaller or larger everywhere. Largest is 200% of Default.',
    `${segmented('Text size', TEXT_CHOICES, settings.textSize, 'textSize')}
      <p class="help">The whole window follows this choice, including the spacing.</p>`,
  )}${paneRow(
    'Colours',
    'Light is warm paper. Dark is soot. System follows how your computer is set.',
    segmented('Colours', THEME_CHOICES, settings.colourTheme, 'colourTheme'),
  )}`;
}

function popupHtml(state) {
  const settings = state.settings;
  const current = state.candidate ?? settings.quickPopup.shortcut;
  const keys = displayKeys(current, IS_MAC ? 'mac' : 'other');
  const warnings = acceleratorWarnings(current, IS_MAC ? 'mac' : 'other');
  const keysHtml = state.capturing
    ? `<span class="kbdkey" data-testid="popup-capturing">Press the new keys… (Esc cancels)</span>`
    : (keys ?? ['not readable']).map((k) => `<span class="kbdkey">${esc(k)}</span>`).join('');
  const warningHtml = warnings
    .map((warning) => `<p class="help" data-testid="popup-warning"><strong>Check:</strong> ${esc(warning)}</p>`)
    .join('');
  const control = `${keysHtml}
    <div class="actions" style="margin-top:var(--s3)">
      ${state.capturing ? '' : buttonHtml({ label: 'Change keys', action: 'popup-capture', variant: 'secondary', testid: 'popup-capture' })}
      ${state.candidate && !state.capturing ? buttonHtml({ label: 'Use these keys', action: 'popup-save-candidate', variant: 'primary', testid: 'popup-keep' }) : ''}
      ${!state.capturing && current !== DEFAULT_SHORTCUT ? buttonHtml({ label: 'Use the default', action: 'popup-reset', variant: 'text', testid: 'popup-reset' }) : ''}
    </div>
    ${warningHtml}
    <p class="help">If another program already uses these keys, the popup will not open. Ember cannot check other programs: the shortcut is untested on this system. The tray icon and the Add screen always work.</p>`;
  const position = settings.quickPopup.position;
  return `${paneRow(
    'Shortcut',
    'The keys that open the small window for adding text from anywhere.',
    control,
  )}${paneRow(
    'Position',
    'Where the quick popup appears on the screen.',
    `<select data-set="quickPopupPosition" aria-label="Where the quick popup appears">
      ${POSITION_CHOICES.map((c) => `<option value="${c.value}" ${c.value === position ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
    </select>`,
  )}`;
}

function menuHtml(state) {
  const settings = state.settings;
  const order = menuOrderForDisplay(settings.menuOrder);
  const hidden = settings.menuHidden ?? [];
  const textButton = (label, dir, job, disabled) =>
    `<button type="button" class="btn btn--text" data-menu="move" data-id="${job.id}" data-dir="${dir}"
      data-testid="menu-${dir}-${job.id}"
      aria-label="Move ${esc(job.name)} ${dir}" ${disabled ? 'disabled' : ''}>${label}</button>`;
  const rows = order
    .map((job, i) => {
      const shown = !hidden.includes(job.id);
      return `<li data-testid="menu-row-${job.id}">
        <label><input type="checkbox" data-menu="toggle" data-id="${job.id}" data-testid="menu-check-${job.id}" aria-label="Show ${esc(job.name)} in the sidebar" ${shown ? 'checked' : ''}> ${esc(job.name)}</label>
        ${textButton('Up', 'up', job, i === 0)}
        ${textButton('Down', 'down', job, i === order.length - 1)}
      </li>`;
    })
    .join('');
  return paneRow(
    'Jobs in the menu',
    'Choose which jobs show in the sidebar and in what order. Home and Settings always show.',
    `<ul class="menu-list" data-testid="menu-list">${rows}</ul>`,
  );
}

function aiHtml(state) {
  if (state.aiLoading) {
    return loadingHtml({ hint: 'Checking the AI connection. Nothing is changed.' });
  }
  if (state.aiStatusError) {
    return `<div class="errbox" role="alert" data-testid="settings-error"><strong>The AI connection status could not be read.</strong>
      <span class="detail">The key storage did not answer. Nothing was changed.</span>
      <div class="actions">${buttonHtml({ label: 'Try again', action: 'ai-retry-status', variant: 'secondary' })}</div></div>`;
  }
  let statusHtml;
  if (state.aiStatus?.stored) {
    statusHtml = `<p data-testid="ai-status" style="margin:0">Connected.<span class="help">The key is in this computer's keyring${
      state.aiHint ? `, and ends in <span class="kbdkey" data-testid="ai-hint">${esc(state.aiHint)}</span>` : ''
    }. Ember never shows the whole key.</span></p>`;
  } else if (state.aiStatus?.sessionOnly) {
    statusHtml = `<p data-testid="ai-status" style="margin:0">Connected for this session only.<span class="help">The keyring here could not store the key, so it lives in memory. It is gone when you close Ember.</span></p>`;
  } else {
    statusHtml = `<p data-testid="ai-status" style="margin:0">Not connected.<span class="help">Add and Link items wait for a key. Everything else works.</span></p>`;
  }
  const replaceForm = state.replaceOpen
    ? `<div class="panel tone" style="margin-top:var(--s4)"><div class="pad">
        <label for="settings-key">Your AI key</label>
        <div class="filters">
          <input type="${state.showKey ? 'text' : 'password'}" id="settings-key" data-testid="settings-key-input" autocomplete="off" aria-label="Your AI key">
          ${buttonHtml({ label: state.showKey ? 'Hide' : 'Show', action: 'ai-show-key', variant: 'secondary' })}
        </div>
        <p class="help">A key is a long password that lets Ember use the AI service. Ember stores it on this computer only — in the operating system keyring, never in a plain file. Your text goes to that service when you use Add or Link items.</p>
        <p class="help">Ember checks the key's shape now. The real test happens at your first Add: if the service refuses the key, you will see a clear message there.</p>
        <div class="actions">
          ${buttonHtml({ label: 'Save the key', action: 'ai-save-key', variant: 'primary', testid: 'ai-save-key' })}
          ${state.offerSession ? buttonHtml({ label: 'Use for this session only', action: 'ai-session-key', variant: 'secondary', testid: 'ai-session-key' }) : ''}
          ${buttonHtml({ label: 'Cancel', action: 'ai-replace-cancel', variant: 'text' })}
        </div>
      </div></div>`
    : '';
  const removeConfirm = state.removeConfirm
    ? `<div class="errbox" role="alert" data-testid="ai-remove-confirm-box" style="margin-top:var(--s4)">
        <strong>Remove this AI key?</strong>
        <span class="detail">Add and Link items wait for a new key afterwards. The key is removed from this computer's keyring; it cannot be brought back. Nothing in your knowledge base changes.</span>
        <div class="actions">
          ${buttonHtml({ label: 'Remove the key', action: 'ai-remove-confirm', variant: 'danger', testid: 'ai-remove-confirm' })}
          ${buttonHtml({ label: 'Cancel', action: 'ai-remove-cancel', variant: 'text' })}
        </div>
      </div>`
    : '';
  const actions = `<div class="actions">
    ${buttonHtml({ label: 'Replace key', action: 'ai-replace', variant: 'secondary', testid: 'ai-replace' })}
    ${buttonHtml({ label: 'Remove key…', action: 'ai-remove', variant: 'danger', testid: 'ai-remove', title: 'Careful: this asks first, then removes the key from the keyring' })}
  </div>`;
  const connected = state.aiStatus?.stored || state.aiStatus?.sessionOnly;
  // Not connected: the pane's own path to fix it (the no-key state
  // never dead-ends; stories 48/89).
  const controls = `${connected ? actions : buttonHtml({ label: 'Set up the connection', action: 'ai-replace', variant: 'primary', testid: 'ai-set-up' })}${replaceForm}${removeConfirm}`;
  return paneRow('AI connection', 'Adding text and linking items need it.', `${statusHtml}${controls}`);
}

function kbfileHtml(state) {
  if (state.kbLoading) {
    return loadingHtml({ hint: 'Checking the knowledge base file. Nothing is changed.' });
  }
  const status = state.kbStatus;
  let statusHtml = '';
  if (status && status.exists && status.looksValid) {
    statusHtml = `<p class="help" data-testid="kb-state" style="margin-top:var(--s2)">The file is there and reads as an Ember knowledge base.</p>`;
  } else if (status && status.exists) {
    statusHtml = `<div class="errbox" role="alert" data-testid="kb-state" style="margin-top:var(--s2)"><strong>That file is not a knowledge base.</strong><span class="detail">The chosen file exists but does not read as an Ember file. It is not used. (code APP-006)</span></div>`;
  } else {
    statusHtml = `<p class="help" data-testid="kb-state" style="margin-top:var(--s2)">The file does not exist yet. It is created the first time you add text.</p>`;
  }
  return paneRow(
    'Knowledge base file',
    'One file holds everything: your items, their links and the ledger.',
    `<p class="mono" data-testid="kb-path" style="margin:0 0 var(--s2);overflow-wrap:anywhere">${esc(state.kbPath || '(no file chosen)')}</p>
      ${statusHtml}
      <label for="settings-kb">Knowledge base file location</label>
      <input type="text" id="settings-kb" data-testid="settings-kb-input" aria-label="Knowledge base file location" aria-describedby="settings-kb-help">
      <p class="help" id="settings-kb-help">Type the full location, or pick an existing file. A new name is fine: the file is created at the first Add.</p>
      <div class="actions">
        ${buttonHtml({ label: 'Use this file', action: 'kb-use', variant: 'primary', testid: 'kb-use' })}
        ${buttonHtml({ label: 'Choose with the file picker…', action: 'kb-browse', variant: 'secondary', testid: 'kb-browse' })}
      </div>`,
  );
}

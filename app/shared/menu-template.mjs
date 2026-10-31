/**
 * The application menu's PURE definition (app step 12, plan §5.7,
 * spec §9): one menu definition built from the spec §9 table — Ember
 * (Mac app menu), File, Edit, View, Jobs, Window, Help — the same
 * items always, DISABLED never hidden (spec §9 rule), with the
 * Undo/Redo labels naming the action from the undo plan's dry-run
 * (`shared/undo-labels.mjs` is the source, the step-07 derivation the
 * Fix and close bar already uses, so the menu and the bar cannot
 * drift).
 *
 * Pure module (T1): context in, plain objects out. NO Electron, NO
 * click handlers — every actionable item carries an `id`; the
 * main-process manager (main/app-menu.js) attaches the one dispatch
 * call per item, which is the only OS effect. On Windows/Linux the
 * same menus sit in the window and Command becomes Ctrl, which
 * Electron's `CmdOrCtrl` accelerator spells exactly.
 * Unit-tested in app/test/menu-template.test.js (the output equals
 * the spec §9 table: labels, shortcuts, enabled state by context).
 */

import { undoRedoLabel, undoDisabledReason } from './undo-labels.mjs';

/** The seven menus, in the spec §9 table's order (Apple's standard order). */
export const MENU_TITLES = Object.freeze(['Ember', 'File', 'Edit', 'View', 'Jobs', 'Window', 'Help']);

/** Menu order/hide/reorder shape for the buildMenuTemplate doc. */
export const JOBS = Object.freeze({
  order: Object.freeze([]),
  hidden: Object.freeze([]),
});

/** The Jobs menu's items with the spec table's names (the same names
 * the sidebar shows — pinned against app.mjs by the unit tests).
 * Home and Settings are the two fixed sidebar entries (story 88), so
 * the movable six come from the settings schema's DEFAULT_MENU_ORDER. */
export const JOB_NAMES = Object.freeze({
  home: 'Home',
  add: 'Add',
  lookup: 'Look up',
  link: 'Link items',
  fix: 'Fix and close',
  cleanup: 'Clean up',
  keepsafe: 'Keep safe',
});

/** 'other' reads as Windows/Linux: same menus in the window, Ctrl keys. */
const IS_MAC = (platform) => platform === 'darwin';

const FALLBACK_LABEL = { undo: 'Undo', redo: 'Redo' };

/**
 * One `undo`/`redo --dry-run` result -> that Edit-menu item's state.
 * The plan present: the label names the action ("Undo Close item 3",
 * Apple's rule, stories 113). MAINTAIN-023/024 (nothing to undo/redo):
 * the item stays VISIBLE and DISABLED (spec §9 rule), with the honest
 * reason for anyone who asks the pane. Any other failure (a transport
 * refusal, APP-008...): the item stays plain and ENABLED — the click
 * routes to Fix and close, which re-derives honestly and shows the
 * plain refusal words with Try again (story 118). No dry-run answer
 * yet (boot): plain and disabled — an unknown state must not invite a
 * click. Pure (T1), unit-tested.
 *
 * @param {{ok: true, data: {summary: object}} |
 *          {ok: false, error: {code: string, detail?: string}} | null} result
 * @param {'undo'|'redo'} direction
 * @returns {{label: string, enabled: boolean, reason: string|null}}
 */
export function deriveUndoMenuState(result, direction) {
  const fallback = FALLBACK_LABEL[direction] ?? direction;
  if (result === null || result === undefined) {
    return { label: fallback, enabled: false, reason: null };
  }
  if (result.ok) {
    const summary = result.data && typeof result.data === 'object' ? result.data.summary : null;
    if (summary && typeof summary === 'object') {
      try {
        return { label: undoRedoLabel(summary), enabled: true, reason: null };
      } catch {
        // An unknown source_action would make the menu LIE — never label
        // wrongly; the pane derives the same document and throws loudly.
        return {
          label: fallback,
          enabled: false,
          reason: 'The undo label could not be read right now; open Fix and close for the exact words.',
        };
      }
    }
    return { label: fallback, enabled: false, reason: null };
  }
  const reason = undoDisabledReason(result.error ?? null);
  if (reason) return { label: fallback, enabled: false, reason };
  return { label: fallback, enabled: true, reason: null };
}

/**
 * The one menu definition (spec §9 table -> Electron template shape).
 * The output is JSON-serialisable except that it is plain data ONLY:
 * no functions. Context knobs:
 *
 * - platform: 'darwin' shows the macOS window commands (Hide role);
 *   anything else keeps the same menus with the window's Minimize in
 *   Hide's place (see the deviation note in the build notes).
 * - kbChosen: false (first run pending) disables Settings and every
 *   job — first run owns the screen; About/Help/Quit stay.
 * - sidebarVisible: the View item's Show/Hide wording.
 * - jobs: {order, hidden} from the settings schema (step 10's
 *   hide/reorder): every job always listed; hidden ones disabled; the
 *   accelerators are positional (1-7 in the shown order), so they
 *   equal the spec table's Command+1..7 at the default order.
 * - undo/redo: deriveUndoMenuState outputs.
 *
 * @param {object} ctx
 * @returns {{label: string, submenu: object[]}[]}
 */
export function buildMenuTemplate(ctx) {
  const {
    platform = 'other',
    kbChosen = true,
    sidebarVisible = true,
    jobs = JOBS,
    undo = deriveUndoMenuState(null, 'undo'),
    redo = deriveUndoMenuState(null, 'redo'),
  } = ctx ?? {};
  const mac = IS_MAC(platform);

  const jobItems = jobsInShownOrder(jobs).map((id, index) => ({
    id: `job-${id}`,
    label: JOB_NAMES[id],
    accelerator: `CmdOrCtrl+${index + 1}`,
    enabled: Boolean(kbChosen) && !(jobs.hidden ?? []).includes(id),
  }));

  return [
    {
      label: 'Ember',
      submenu: [
        { id: 'about', label: 'About Ember' },
        { type: 'separator' },
        { id: 'settings', label: 'Settings…', accelerator: 'CmdOrCtrl+,', enabled: Boolean(kbChosen) },
        { type: 'separator' },
        mac ? { label: 'Hide Ember', role: 'hide' } : { label: 'Hide', role: 'minimize' },
        { type: 'separator' },
        { label: 'Quit', role: 'quit' },
      ],
    },
    {
      label: 'File',
      submenu: [
        { id: 'file-add-text', label: 'Add text…' },
        { id: 'file-open-kb', label: 'Open a knowledge base file…', accelerator: 'CmdOrCtrl+O' },
        { id: 'file-backup', label: 'Back up…' },
        { id: 'file-export', label: 'Export…' },
        { type: 'separator' },
        { label: 'Close window', role: 'close' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { id: 'edit-undo', label: undo.label, accelerator: 'CmdOrCtrl+Z', enabled: Boolean(undo.enabled) },
        { id: 'edit-redo', label: redo.label, accelerator: 'Shift+CmdOrCtrl+Z', enabled: Boolean(redo.enabled) },
        { type: 'separator' },
        { label: 'Cut', role: 'cut' },
        { label: 'Copy', role: 'copy' },
        { label: 'Paste', role: 'paste' },
        { label: 'Select All', role: 'selectAll' },
        { type: 'separator' },
        { id: 'edit-find', label: 'Find', accelerator: 'CmdOrCtrl+F' },
      ],
    },
    {
      label: 'View',
      submenu: [
        {
          id: 'view-sidebar',
          label: sidebarVisible ? 'Hide Sidebar' : 'Show Sidebar',
          enabled: Boolean(kbChosen),
        },
      ],
    },
    { label: 'Jobs', submenu: jobItems },
    {
      label: 'Window',
      submenu: [{ label: 'Minimize', role: 'minimize' }, { label: 'Zoom', role: 'zoom' }],
    },
    {
      label: 'Help',
      submenu: [{ label: 'Ember Help', enabled: false }],
    },
  ];
}

/** Home first, the saved (reordered) movable jobs next, strays last. */
function jobsInShownOrder(jobs) {
  const movable = ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'];
  const order = [];
  order.push('home');
  for (const id of jobs.order ?? []) if (movable.includes(id) && !order.includes(id)) order.push(id);
  for (const id of movable) if (!order.includes(id)) order.push(id);
  return order;
}

/**
 * Story 108's About-box credits: the fonts' licence facts, the ONE
 * place the step-03 font work points at. Pure: strings in, string out.
 *
 * @param {{version: string, fontsPath: string}} args
 * @returns {string}
 */
export function aboutCreditsText({ version, fontsPath }) {
  return (
    `Ember ${version}\n\n` +
    'Typefaces: Atkinson Hyperlegible Next (the text face) and\n' +
    'Atkinson Hyperlegible Mono (the figures). They are bundled with\n' +
    'this app; no font is loaded from the internet (story 107).\n\n' +
    'Licence: the SIL Open Font Licence, version 1.1. The full licence\n' +
    'text and the copyright notice for each face sit next to the font\n' +
    'files, in the folder:\n' +
    `${fontsPath}\n` +
    '(the files whose names end in -OFL.txt).'
  );
}

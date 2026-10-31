'use strict';

/**
 * The preload seam (interface-app-plan.md §4 rule, B5).
 *
 * THE ONE narrow, named call list the renderer may use. It exposes no
 * Node primitive, no raw ipcRenderer, no fs, no child_process — only
 * these functions over `contextBridge`. The full list is pinned
 * by a node test (test/preload-allowlist.test.js) so nothing can be
 * added quietly.
 *
 * App 05 (ticket A34) adds the Add confirm-session: the three invoke
 * channels (addStart/addAnswer/addStop) and two main-to-renderer push
 * channels (ember:addEvent carries the validated session events,
 * ember:addExit the one exit message) subscribed through
 * onAddEvent/onAddExit — one add session at a time, in the main
 * process, one child per session.
 */

const { contextBridge, ipcRenderer } = require('electron');

/** The allowlist, exported for the pinning test (not used at runtime). */
const EMBER_PRELOAD_API = Object.freeze([
  'ember:ping',
  'ember:getState',
  'ember:saveSettings',
  'ember:kbStatus',
  'ember:pickKnowledgeBaseFile',
  'ember:listItems',
  'ember:topicSearch',
  'ember:showItem',
  'ember:history',
  'ember:currentState',
  'ember:maintainDryRun',
  'ember:keyStatus',
  'ember:setKey',
  'ember:setSessionKey',
  'ember:removeKey',
  'ember:addStart',
  'ember:addAnswer',
  'ember:addStop',
  'ember:addAttach',
  'ember:pickSaveFile',
  'ember:backupTo',
  'ember:exportTo',
  'ember:dbCheck',
  'ember:switchKnowledgeBase',
  'ember:fixAction',
  'ember:undoPlan',
  'ember:registerShortcut',
  'ember:keyHint',
  'ember:maintainPreview',
  'ember:maintainApply',
  'ember:maintainAnswer',
  'ember:maintainStop',
  'ember:openQuickPopup',
  'ember:quickOpenMain',
]);
// The names after the base 15: Add (App 05), Keep safe (step 09),
// Fix and close (step 07), Settings (app 10), Clean up (App 08),
// Quick popup (app 11) — each appended at the END of the allowlist
// as its own bracketed block.

contextBridge.exposeInMainWorld('ember', {
  /** Smallest proof the seam is alive: string in, string out. */
  ping: () => ipcRenderer.invoke('ember:ping'),

  /** Boot snapshot: app version, settings, notices, the KB paths. */
  getState: () => ipcRenderer.invoke('ember:getState'),

  /** Merge a settings patch (validated again in the main process). */
  saveSettings: (patch) => ipcRenderer.invoke('ember:saveSettings', patch),

  /** Knowledge-base status: {path, exists, looksValid} — no command runs. */
  kbStatus: (path) => ipcRenderer.invoke('ember:kbStatus', path ?? null),

  /** Open an existing knowledge-base file through the OS file picker. */
  pickKnowledgeBaseFile: () => ipcRenderer.invoke('ember:pickKnowledgeBaseFile'),

  /** The browse page: `ember list-items` with the pinned filters. */
  listItems: (page) => ipcRenderer.invoke('ember:listItems', page ?? null),

  /** `ember topic-search --query ...` with the pinned filters. */
  topicSearch: (page) => ipcRenderer.invoke('ember:topicSearch', page ?? null),

  /** `ember show-item --item N`: statement, verbatim source, all links. */
  showItem: (item) => ipcRenderer.invoke('ember:showItem', { item }),

  /** `ember history` with the pinned pacing flags (--item/--limit/--offset/--since). */
  history: (page) => ipcRenderer.invoke('ember:history', page ?? null),

  /** `ember current-state`: Active and Challenged items, Closed omitted. */
  currentState: () => ipcRenderer.invoke('ember:currentState'),

  /** `ember maintain --dry-run` pending count for the Home attention block. */
  maintainDryRun: () => ipcRenderer.invoke('ember:maintainDryRun'),

  /** Key status: {stored, sessionOnly, backend} — never the key itself. */
  keyStatus: () => ipcRenderer.invoke('ember:keyStatus'),

  /** Save the AI key encrypted in the OS keyring (APP-003 on refusal). */
  setKey: (key) => ipcRenderer.invoke('ember:setKey', key),

  /** The APP-003 offer: keep the key for this session only. */
  setSessionKey: (key) => ipcRenderer.invoke('ember:setSessionKey', key),

  /** Remove the saved key (careful action, story 89). */
  removeKey: () => ipcRenderer.invoke('ember:removeKey'),

  /* ==== App 05 (ticket A34): the Add confirm-session ================
     One add session at a time, in the main process: the pasted text in,
     the validated session events back out, answers one at a time. */
  /** Start `capture --file <temp> --confirm json --db <kb>`. */
  startAdd: (text) => ipcRenderer.invoke('ember:addStart', { text }),

  /** One answer: written to the child as exactly {"answer": "<text>"}. */
  answerAdd: (text) => ipcRenderer.invoke('ember:addAnswer', text),

  /** Stop: closes the session's stdin — a quiet quit, nothing half-written. */
  stopAdd: () => ipcRenderer.invoke('ember:addStop'),

  /** Flush any session pushes that arrived before the renderer subscribed. */
  attachAdd: () => ipcRenderer.invoke('ember:addAttach'),

  /** Subscribe to validated session events; returns an unsubscribe. */
  onAddEvent: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('ember:addEvent', handler);
    return () => ipcRenderer.removeListener('ember:addEvent', handler);
  },

  /** Subscribe to the one exit message {exitCode, error}; returns an unsubscribe. */
  onAddExit: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('ember:addExit', handler);
    return () => ipcRenderer.removeListener('ember:addExit', handler);
  },

  /* =================================================================
   * App step 09 (Keep safe) — added at the END of the exposure object
   * as this step's own bracketed block (ticket A38).
   * ================================================================= */

  /** The "where to save" OS dialog (backup target / export out). */
  pickSaveFile: (ask) => ipcRenderer.invoke('ember:pickSaveFile', ask ?? null),

  /** `ember backup TARGET --format json`: the verified copy's report. */
  backupTo: (targetPath) => ipcRenderer.invoke('ember:backupTo', { targetPath }),

  /** `ember export --out FILE`: exit-code result; the app reads no export JSON. */
  exportTo: (outPath) => ipcRenderer.invoke('ember:exportTo', { outPath }),

  /** `ember db-check --format json`: OK / DRIFT / UNREADABLE report. */
  dbCheck: (dbPath) => ipcRenderer.invoke('ember:dbCheck', dbPath ? { dbPath } : null),

  /** Story 76: open a DIFFERENT knowledge base file (db-check gate, then the setting). */
  switchKnowledgeBase: (path) => ipcRenderer.invoke('ember:switchKnowledgeBase', { path }),

  // --- app step 07 (Fix and close) — appended at the END of the named
  // --- call list; nothing else is exposed.

  /** One Fix and close action: {action, args} runs the pinned command. */
  fixAction: (payload) => ipcRenderer.invoke('ember:fixAction', payload ?? null),

  /** The undo/redo dry-run plan ({command: 'undo'|'redo'}) for the label. */
  undoPlan: (command) => ipcRenderer.invoke('ember:undoPlan', { command }),

  // [app 10] Settings panes (stories 85-89).

  /** Re-register the quick-popup shortcut from the Settings pane. */
  registerShortcut: (accelerator) => ipcRenderer.invoke('ember:registerShortcut', { accelerator }),

  /** The masked key hint (last four characters), for the AI pane's status. */
  keyHint: () => ipcRenderer.invoke('ember:keyHint'),

  /* --- App 08 (Clean up): the sweep preview and the stepwise apply
     session (additive; ticket A37). maintainApply returns its own small
     handle — { answer, stop, done } — so the loop's two controls never
     land on the window-level allowlist: answer(text) sends exactly
     `{"answer": "<text>"}` through main, stop() closes the session's
     input (the engine reads that as a quit), and done settles when main
     has started (or refused) the run; the EVENTS themselves arrive on
     the 'ember:maintainEvent' push channel, forwarded to onEvent. --- */
  maintainPreview: () => ipcRenderer.invoke('ember:maintainPreview'),
  maintainApply: (onEvent) => {
    if (typeof onEvent !== 'function') throw new Error('maintainApply needs an event handler (onEvent)');
    const listener = (_event, payload) => {
      try {
        onEvent(payload);
      } catch (err) {
        // A screen bug in the event handler must not silently break the
        // pipe: report it back through the same channel shape.
        onEvent({
          kind: 'error',
          info: {
            code: 'APP-000',
            name: 'AppError',
            where: 'preload.maintainApply',
            detail: err instanceof Error ? err.message : 'the screen could not handle a sweep event',
          },
        });
      }
      if (payload && payload.kind === 'exit') {
        // The session ended: the pipe listener goes with it. (The
        // invoke resolves EARLY — when main starts (or refuses) the
        // run — so the exit event, not the invoke, ends the listen.)
        ipcRenderer.removeListener('ember:maintainEvent', listener);
      }
    };
    ipcRenderer.on('ember:maintainEvent', listener);
    const done = ipcRenderer.invoke('ember:maintainApply').then((result) => {
      if (!result || !result.ok) {
        // The run never started, so no exit event will come.
        ipcRenderer.removeListener('ember:maintainEvent', listener);
      }
      return result;
    });
    return {
      answer: (text) => ipcRenderer.invoke('ember:maintainAnswer', { answer: text }),
      stop: () => ipcRenderer.invoke('ember:maintainStop'),
      done,
    };
  },

  /* ==== App 11 (ticket A40): the quick popup's channels (additive;
     the allowlist test and the smoke pin the list). The popup page
     uses the SAME preload allowlist as the main window (B5). ==== */

  /**
   * Open (or hide) the quick popup — the route that always works
   * (plan §5.5): step 12's File -> Add text menu item lands on the
   * same handler, as does the e2e. From the popup page itself the
   * popup calls this with {action: 'hide'} to close.
   */
  openQuickPopup: (ask) => ipcRenderer.invoke('ember:openQuickPopup', ask ?? null),

  /** Popup -> main: open the full window (93) or its setup path (94). */
  quickOpenMain: (ask) => ipcRenderer.invoke('ember:quickOpenMain', ask ?? null),

  /** Main window: the popup asked for the setup view (story 94). */
  onOpenRequest: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('ember:openRequest', handler);
    return () => ipcRenderer.removeListener('ember:openRequest', handler);
  },
});

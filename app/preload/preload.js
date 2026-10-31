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
]);
// The five names above are app step 09 (Keep safe), appended at the
// END of the allowlist as this step's own bracketed block (ticket A38).

contextBridge.exposeInMainWorld('ember', {
  /** Smallest proof the seam is alive: string in, string out. */
  ping: () => ipcRenderer.invoke('ember:ping'),

  /** Boot snapshot: app version, settings, notices, the KB paths. */
  getState: () => ipcRenderer.invoke('ember:getState'),

  /** Merge a settings patch (validated again in the main process). */
  saveSettings: (patch) => ipcRenderer.invoke('ember:saveSettings', patch),

  /** Knowledge-base status: {path, exists, looksValid} — no command runs. */
  kbStatus: () => ipcRenderer.invoke('ember:kbStatus'),

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
});

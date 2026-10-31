'use strict';

/**
 * The preload seam (interface-app-plan.md §4 rule, B5).
 *
 * THE ONE narrow, named call list the renderer may use. It exposes no
 * Node primitive, no raw ipcRenderer, no fs, no child_process — only
 * these fifteen functions over `contextBridge`. The full list is pinned
 * by a node test (test/preload-allowlist.test.js) so nothing can be
 * added quietly.
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
  'ember:fixAction',
  'ember:undoPlan',
]);

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

  // --- app step 07 (Fix and close) — appended at the END of the named
  // --- call list; nothing else is exposed.

  /** One Fix and close action: {action, args} runs the pinned command. */
  fixAction: (payload) => ipcRenderer.invoke('ember:fixAction', payload ?? null),

  /** The undo/redo dry-run plan ({command: 'undo'|'redo'}) for the label. */
  undoPlan: (command) => ipcRenderer.invoke('ember:undoPlan', { command }),
});

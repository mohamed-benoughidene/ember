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
  'ember:maintainPreview',
  'ember:maintainApply',
  'ember:maintainAnswer',
  'ember:maintainStop',
]);
/* --- App 08 (Clean up, ticket A37): the last four names are the sweep
   preview + the confirm session (additive). The pinning test splits this
   array textually, so the array itself stays comment-free. The session's
   events ride a fixed push channel the preload owns — that channel is
   deliberately NOT a renderer-callable name. --- */

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
});

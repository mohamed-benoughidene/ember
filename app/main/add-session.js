'use strict';

/**
 * The Add confirm-session channels (app step 05, ticket A34).
 *
 * Registers the THREE session ipc handlers at the end of the ipc list
 * (called once from main/ipc.js's App 05 block). ONE add session at a
 * time; one child process per session (bridge client, plan §5.1).
 *
 * - `ember:addStart {text}`: validates, writes the pasted text to the
 *   user-data temp file (capture-temp.js), starts
 *   `capture --file <temp> --confirm json --db <kb>` and forwards the
 *   VALIDATED session events to the invoking sender as `ember:addEvent`
 *   messages. The knowledge base may be created by the add (until the
 *   first Add the file does not exist, app step file §1); an existing
 *   file must be an Ember file (APP-006).
 * - `ember:addAnswer <text>`: one answer; the bridge client writes
 *   exactly one `{"answer": "<text>"}` stdin line, so BRIDGE-001 (a
 *   refused answer line) can never be triggered by the app — a unit
 *   test pins the non-string refusal at this edge.
 * - `ember:addStop`: closes stdin — the engine reads it as a quiet
 *   user quit (exit 2, nothing half-written; engines write only after
 *   a confirm, I7).
 *
 * The session's end always cleans the temp file, and the final
 * `ember:addExit` message carries {exitCode, error}: the parsed engine
 * error when the child exited 1, APP-002 when it ended without a
 * summary (a crash: nothing was half-written, but the UI must say so).
 */

const { appErrorInfo } = require('../shared/errors');

const WHERE = 'main.add-session';

const ADD_CHANNELS = Object.freeze(['ember:addStart', 'ember:addAnswer', 'ember:addStop', 'ember:addAttach']);
const EVENT_CHANNEL = 'ember:addEvent';
const EXIT_CHANNEL = 'ember:addExit';

/**
 * @param {object} ipcMain Electron's ipcMain (or a fake with .handle)
 * @param {object} options
 * @param {(args: string[]) => object} options.startSession bridge client
 *   factory: (args) => runConfirmSession('capture', args)
 * @param {() => {ok: true} | {ok: false, error: object}} options.validateAddTarget
 * @param {(text: string) => {ok: true, path: string} | {ok: false, error: object}} options.writeTempText
 * @param {(path: string|null) => void} options.removeTempFile
 * @param {() => number} options.cleanStaleTempFiles crash cleanup at registration
 * @param {(name: string, args: string[]) => void} [options.onCommand] test seam
 */
function wireAddChannels(ipcMain, { startSession, validateAddTarget, writeTempText, removeTempFile, cleanStaleTempFiles, onCommand = () => {} }) {
  cleanStaleTempFiles();

  /** The ONE active session, or null: {session, tempPath, sender}. */
  let active = null;

  /**
   * The child can be faster than the renderer's subscription (a dying
   * child, an instant refusal): every push is BUFFERED until the
   * renderer calls `ember:addAttach` (it subscribes right after
   * startAdd resolves), then the buffer flushes in order. No event and
   * no exit message can ever be lost.
   */
  let attached = false;
  let buffer = [];

  function sendTo(sender, channel, data) {
    if (sender && typeof sender.send === 'function' && !sender.isDestroyed()) {
      sender.send(channel, data);
    }
  }

  function pushOut(sender, channel, data) {
    if (!attached) {
      buffer.push([sender, channel, data]);
      return;
    }
    sendTo(sender, channel, data);
  }

  function sendToActive(channel, data) {
    pushOut(active ? active.sender : null, channel, data);
  }

  ipcMain.handle('ember:addStart', (event, payload) => {
    try {
      if (active) {
        return { ok: false, error: appErrorInfo('APP-000', `${WHERE}.addStart`, 'an add is already running in this window') };
      }
      const text = payload && typeof payload === 'object' && typeof payload.text === 'string' ? payload.text : null;
      if (text === null || text.trim() === '') {
        return { ok: false, error: appErrorInfo('APP-000', `${WHERE}.addStart`, 'the text box was empty; paste or type some text first') };
      }
      const target = validateAddTarget();
      if (!target.ok) return { ok: false, error: target.error };
      const temp = writeTempText(text);
      if (!temp.ok) return { ok: false, error: temp.error };

      // Real flags only (contract table): the bridge client appends
      // `--confirm json` and the `--db`; stdin stays free for answers.
      const args = ['--file', temp.path];
      onCommand('capture', args);
      const session = startSession(args);
      active = { session, tempPath: temp.path, sender: event && event.sender ? event.sender : null };
      attached = false;
      buffer = [];

      let sessionError = null;
      let sawSummary = false;
      session.on('event', (ev) => {
        if (ev && ev.event === 'summary') sawSummary = true;
        sendToActive(EVENT_CHANNEL, ev);
      });
      session.on('error', (info) => {
        sessionError = info;
      });
      session.on('exit', ({ exitCode }) => {
        const finishing = active;
        active = null;
        removeTempFile(finishing ? finishing.tempPath : null);
        let finalError = sessionError;
        if (!finalError && !sawSummary) {
          finalError = appErrorInfo(
            'APP-002',
            `${WHERE}.exit`,
            `the add ended early (exit ${exitCode ?? 'unknown'}); nothing was half-written`,
          );
        }
        pushOut(finishing ? finishing.sender : null, EXIT_CHANNEL, {
          exitCode: typeof exitCode === 'number' ? exitCode : null,
          error: finalError,
        });
      });
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-000', `${WHERE}.addStart`, `the add could not start: ${err instanceof Error ? err.message : 'unknown error'}`),
      };
    }
  });

  ipcMain.handle('ember:addAttach', () => {
    // The renderer subscribes right after startAdd resolves; only now
    // may pushes go live (the buffer keeps every missed one, in order).
    attached = true;
    const pending = buffer;
    buffer = [];
    for (const [sender, channel, data] of pending) sendTo(sender, channel, data);
    return { ok: true };
  });

  ipcMain.handle('ember:addAnswer', (_event, text) => {
    try {
      if (!active) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.answer`, 'no add is running') };
      }
      if (typeof text !== 'string') {
        // The BRIDGE-001 pin: the app never writes a malformed answer
        // line (the engine would re-ask once and abort on a second).
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.answer`, 'an answer must be text') };
      }
      active.session.answer(text);
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-000', `${WHERE}.answer`, `the answer could not be sent: ${err instanceof Error ? err.message : 'unknown error'}`),
      };
    }
  });

  ipcMain.handle('ember:addStop', () => {
    try {
      if (!active) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.stop`, 'no add is running') };
      }
      active.session.stop();
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-000', `${WHERE}.stop`, `the stop could not be sent: ${err instanceof Error ? err.message : 'unknown error'}`),
      };
    }
  });

  return { channels: ADD_CHANNELS, eventChannel: EVENT_CHANNEL, exitChannel: EXIT_CHANNEL };
}

module.exports = { wireAddChannels, ADD_CHANNELS, EVENT_CHANNEL, EXIT_CHANNEL };

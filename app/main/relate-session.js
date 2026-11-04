'use strict';

/**
 * The Link items confirm-session channels (app step 06, ticket A35).
 *
 * Registers the session ipc handlers at the end of the ipc list
 * (called once from main/ipc.js's App 06 block). ONE link session at
 * a time; one child process per session (bridge client, plan §5.1).
 *
 * - `ember:relateStart {item?, latest?}`: validates the KB (relate
 *   needs an EXISTING Ember file; APP-006 otherwise), builds the argv
 *   ONLY through main/relate-args.js (`--item N` or `--latest`; a bad
 *   value never reaches a child), starts
 *   `relate ... --confirm json --db <kb>` via the step-02
 *   `runConfirmSession` and forwards the VALIDATED session events to
 *   the invoking sender as `ember:relateEvent` messages, buffered
 *   until `ember:relateAttach` (the App 05 pattern: a child that dies
 *   before the renderer subscribes loses nothing).
 * - `ember:relateAnswer <text>`: one answer (`y` / `n` / `s` / `q`);
 *   the bridge client writes exactly one `{"answer": "<text>"}` stdin
 *   line, so BRIDGE-001 can never be triggered by the app.
 * - `ember:relateStop`: closes stdin — the engine reads it as a quiet
 *   user quit (exit 2, nothing half-written, I7).
 *
 * The final `ember:relateExit` message carries {exitCode, error}: the
 * parsed engine error when the child exited 1, APP-001/008 on spawn
 * or idle failure, else null — the screen reads its own event view
 * (summary event, empty-pool signal) for the honest final state. The
 * first run may sit silent for MINUTES while the language model
 * downloads (story 45), so the link session runs on its own bridge
 * client with a longer inactivity limit than the default 120 s (I15:
 * still a limit; a frozen child is still killed).
 */

const { appErrorInfo } = require('../shared/errors');
const { relateArgs } = require('./relate-args');

const WHERE = 'main.relate-session';

const RELATE_CHANNELS = Object.freeze([
  'ember:relateStart',
  'ember:relateAnswer',
  'ember:relateStop',
  'ember:relateAttach',
]);
const EVENT_CHANNEL = 'ember:relateEvent';
const EXIT_CHANNEL = 'ember:relateExit';

/** Story 45: the first relate may download a language model (minutes). */
const RELATE_SESSION_IDLE_MS = 10 * 60_000;

/**
 * @param {object} ipcMain Electron's ipcMain (or a fake with .handle)
 * @param {object} options
 * @param {(args: string[]) => object} options.startSession bridge client
 *   factory: (args) => runConfirmSession('relate', args)
 * @param {() => {ok: true} | {ok: false, error: object}} options.validateRelateTarget
 * @param {(name: string, args: string[]) => void} [options.onCommand] test seam
 */
function wireRelateChannels(ipcMain, { startSession, validateRelateTarget, onCommand = () => {} }) {
  /** The ONE active session, or null: {session, sender}. */
  let active = null;
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

  ipcMain.handle('ember:relateStart', (event, payload) => {
    try {
      if (active) {
        return { ok: false, error: appErrorInfo('APP-000', `${WHERE}.relateStart`, 'a link run is already going in this window') };
      }
      const ask = typeof payload === 'object' && payload !== null ? payload : {};
      let args;
      try {
        args = relateArgs({ item: ask.item ?? null, latest: ask.latest === true });
      } catch (err) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.relateStart`, err instanceof Error ? err.message : 'unknown error') };
      }
      const target = validateRelateTarget();
      if (!target.ok) return { ok: false, error: target.error };

      onCommand('relate', args);
      const session = startSession(args);
      active = { session, sender: event && event.sender ? event.sender : null };
      attached = false;
      buffer = [];

      let sessionError = null;
      session.on('event', (ev) => {
        pushOut(active ? active.sender : null, EVENT_CHANNEL, ev);
      });
      session.on('error', (info) => {
        sessionError = info;
      });
      session.on('exit', ({ exitCode }) => {
        const finishing = active;
        active = null;
        pushOut(finishing ? finishing.sender : null, EXIT_CHANNEL, {
          exitCode: typeof exitCode === 'number' ? exitCode : null,
          error: sessionError,
        });
      });
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-000', `${WHERE}.relateStart`, `the link run could not start: ${err instanceof Error ? err.message : 'unknown error'}`),
      };
    }
  });

  ipcMain.handle('ember:relateAttach', () => {
    attached = true;
    const pending = buffer;
    buffer = [];
    for (const [sender, channel, data] of pending) sendTo(sender, channel, data);
    return { ok: true };
  });

  ipcMain.handle('ember:relateAnswer', (_event, text) => {
    try {
      if (!active) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.relateAnswer`, 'no link run is open') };
      }
      if (typeof text !== 'string') {
        // The BRIDGE-001 pin: the app never writes a malformed answer
        // line (the engine would re-ask once and abort on a second).
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.relateAnswer`, 'an answer must be text') };
      }
      active.session.answer(text);
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-000', `${WHERE}.relateAnswer`, `the answer could not be sent: ${err instanceof Error ? err.message : 'unknown error'}`),
      };
    }
  });

  ipcMain.handle('ember:relateStop', () => {
    try {
      if (!active) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.relateStop`, 'no link run is open') };
      }
      active.session.stop();
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: appErrorInfo('APP-000', `${WHERE}.relateStop`, `the stop could not be sent: ${err instanceof Error ? err.message : 'unknown error'}`),
      };
    }
  });

  return { channels: RELATE_CHANNELS, eventChannel: EVENT_CHANNEL, exitChannel: EXIT_CHANNEL };
}

module.exports = { wireRelateChannels, RELATE_CHANNELS, EVENT_CHANNEL, EXIT_CHANNEL, RELATE_SESSION_IDLE_MS };

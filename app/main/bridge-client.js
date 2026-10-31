'use strict';

/**
 * The bridge client (interface-app-plan.md §5.1, L2 plan §5.1).
 *
 * ONE child process per call; no shared state. The knowledge-base path
 * is ALWAYS passed as `--db`. Output format is JSON. Every child line
 * is untrusted and validated exactly once, here (D4).
 *
 * - runCommand(name, args): one-shot commands. Reads get a timeout and
 *   ONE automatic retry; writes get a timeout and NO retry (a repeated
 *   `undo` or `close-item` could run twice), and report APP-008 so the
 *   app can re-read state before offering Retry.
 * - runConfirmSession(name, args): `capture`, `relate`, `maintain`
 *   under `--confirm json`: emits validated block/prompt/message/
 *   summary events; accepts answer(text); stop() closes stdin.
 *
 * Pure Node (no Electron import), so the node test suite runs it
 * directly against a fake `ember` executable.
 */

const { spawn } = require('node:child_process');
const { appErrorInfo } = require('../shared/errors');
const { parseErrorLine } = require('../shared/parse-error-line');
const { parseEventLine, answerLine } = require('../shared/parse-event-line');

const WHERE = 'main.bridge-client';

/** Reads: timeout + at most one automatic retry (plan §5.1). */
const READ_COMMANDS = new Set([
  'list-items',
  'show-item',
  'current-state',
  'topic-search',
  'why',
  'history',
  'capture-source',
  'db-check',
]);

/** One-shot commands that print the step-01 JSON document under `--format json`. */
const FORMAT_JSON_COMMANDS = new Set([
  'maintain',
  'close-item',
  'set-status',
  'reverse-supersedes',
  'edit-item',
  'remove-link',
  'undo',
  'redo',
  'backup',
  'db-check',
]);

/** Always-JSON commands: their stdout IS the document (no `--format` flag). */
const ALWAYS_JSON_COMMANDS = new Set([
  'current-state',
  'topic-search',
  'why',
  'history',
  'list-items',
  'show-item',
  'capture-source',
]);

/** One-shot commands with no app-facing JSON document (data comes back null). */
const NO_DOC_COMMANDS = new Set(['export', 'set-validated', 'clear-validated']);

/** The interactive commands that must go through runConfirmSession. */
const SESSION_COMMANDS = new Set(['capture', 'relate', 'maintain']);

const MAX_OUTPUT_BYTES = 32 * 1024 * 1024;

/**
 * @param {object} options
 * @param {string[]} options.emberCommand the resolved command, e.g.
 *   ["/path/ember"] or ["node", "/path/fake-ember.js"]
 * @param {string} options.dbPath the knowledge base path, passed as `--db`
 * @param {string|null} options.errorPattern the shared error-line regex
 *   source (loaded from tests/fixtures/bridge/error_parsing_rule.txt)
 * @param {() => string|null} [options.apiKeyProvider] the AI key, sent ONLY
 *   as the child's EMBER_AI_API_KEY environment variable; never logged
 * @param {number} [options.timeoutReadMs] default 30000
 * @param {number} [options.timeoutWriteMs] default 120000
 * @param {number} [options.sessionIdleMs] confirm-session inactivity
 *   limit, default 120000 (I15: a time limit on every call)
 * @param {typeof import('node:child_process').spawn} [options.spawnFn] test seam
 * @param {((name: string) => void) | null} [options.onActivity] app step
 *   12: called with the command name after every one-shot command
 *   settles and after every confirm-session ends — the ONE hook the
 *   shell uses to know the knowledge base may have changed (the
 *   Edit-menu Undo/Redo labels re-derive from it). The hook never
 *   blocks or changes the result; a throwing hook is the caller's bug.
 */
function createBridgeClient(options) {
  const {
    emberCommand,
    dbPath,
    errorPattern,
    apiKeyProvider = () => null,
    timeoutReadMs = 30_000,
    timeoutWriteMs = 120_000,
    sessionIdleMs = 120_000,
    spawnFn = spawn,
    onActivity = null,
  } = options;

  function childEnv() {
    const key = apiKeyProvider();
    const env = { ...process.env };
    if (key !== null) {
      // The ONLY place the key leaves the main process (plan §2).
      env.EMBER_AI_API_KEY = key;
    }
    return env;
  }

  function spawnOnce(argv, timeoutMs, stdinMode) {
    return new Promise((resolve) => {
      let child;
      try {
        child = spawnFn(argv[0], argv.slice(1), {
          env: childEnv(),
          stdio: [stdinMode, 'pipe', 'pipe'],
        });
      } catch (err) {
        resolve({ failed: true, error: appErrorInfo('APP-001', `${WHERE}.runCommand`, safeText(err)) });
        return;
      }
      const stdoutChunks = [];
      const stderrLines = [];
      let stdoutBytes = 0;
      let tooLarge = false;
      let timedOut = false;
      let settled = false;

      const timer = setTimeout(() => {
        timedOut = true;
        try {
          child.kill('SIGTERM');
        } catch {
          /* already gone */
        }
        setTimeout(() => {
          try {
            child.kill('SIGKILL');
          } catch {
            /* already gone */
          }
        }, 1000);
      }, timeoutMs);

      child.stdout.on('data', (chunk) => {
        stdoutBytes += chunk.length;
        if (stdoutBytes > MAX_OUTPUT_BYTES) {
          tooLarge = true;
          try {
            child.kill('SIGTERM');
          } catch {
            /* already gone */
          }
          return;
        }
        stdoutChunks.push(chunk);
      });
      child.stderr.on('data', (chunk) => {
        for (const line of String(chunk).split('\n')) {
          if (line !== '') stderrLines.push(line);
        }
      });

      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({
          failed: false,
          timedOut,
          tooLarge,
          exitCode: typeof child.exitCode === 'number' ? child.exitCode : child.signalCode,
          stdout: Buffer.concat(stdoutChunks).toString('utf8'),
          stderrLines,
        });
      };
      child.on('error', (err) => {
        // Spawn failures (ENOENT and friends) surface here, not in throw.
        settled = true;
        clearTimeout(timer);
        resolve({ failed: true, error: appErrorInfo('APP-001', `${WHERE}.runCommand`, safeText(err)) });
      });
      child.on('close', finish);
    });
  }

  function buildArgv(name, args, extraFlags) {
    const argv = [...emberCommand, name, '--db', dbPath, ...args];
    if (FORMAT_JSON_COMMANDS.has(name) && !ALWAYS_JSON_COMMANDS.has(name)) {
      argv.push('--format', 'json');
    }
    for (const flag of extraFlags) argv.push(flag);
    return argv;
  }

  function interpret(name, run) {
    if (run.tooLarge) {
      return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} printed more than ${MAX_OUTPUT_BYTES} bytes`) };
    }
    if (run.exitCode === 0) {
      if (ALWAYS_JSON_COMMANDS.has(name) || FORMAT_JSON_COMMANDS.has(name)) {
        const text = run.stdout.trim();
        if (text === '') {
          return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} printed no document`) };
        }
        try {
          const data = JSON.parse(text);
          if (typeof data !== 'object' || data === null || Array.isArray(data)) {
            return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} did not print a JSON object`) };
          }
          return { ok: true, data };
        } catch {
          return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} printed stdout that was not one JSON document`) };
        }
      }
      // NO_DOC commands: the app uses only the exit code (D3: never recompute).
      return { ok: true, data: null };
    }
    // Non-zero exit: the house error line on stderr is THE result.
    const first = run.stderrLines[0] ?? '';
    const parsed = errorPattern ? parseErrorLine(first, errorPattern, run.stderrLines.slice(1)) : null;
    if (parsed) return { ok: false, error: parsed };
    if (run.exitCode === 2) {
      return {
        ok: false,
        error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} exited 2 (usage error or user abort)${first ? `: ${clip(first)}` : ''}`),
      };
    }
    return {
      ok: false,
      error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} failed with an unparsable error line${first ? `: ${clip(first)}` : ' (no stderr)'}`),
    };
  }

  /**
   * One-shot command. See module docstring for the retry rule.
   *
   * @param {string} name a registered one-shot command (NOT capture/relate)
   * @param {string[]} args flags after `--db <path>` (e.g. ['--item','1'])
   * @returns {Promise<{ok: true, data: object|null} |
   *           {ok: false, error: {code: string, name: string, where: string, detail: string}}>}
   */
  async function runCommand(name, args = []) {
    if (SESSION_COMMANDS.has(name)) {
      throw new TypeError(`${name} is interactive: use runConfirmSession`);
    }
    if (
      !READ_COMMANDS.has(name) &&
      !FORMAT_JSON_COMMANDS.has(name) &&
      !ALWAYS_JSON_COMMANDS.has(name) &&
      !NO_DOC_COMMANDS.has(name)
    ) {
      throw new TypeError(`unknown one-shot command: ${name}`);
    }
    const isRead = READ_COMMANDS.has(name);
    const timeoutMs = isRead ? timeoutReadMs : timeoutWriteMs;
    const attempts = isRead ? 2 : 1; // reads retry once, writes never (I15)
    const argv = buildArgv(name, args, []);
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const run = await spawnOnce(argv, timeoutMs, 'ignore');
      if (run.failed) {
        if (onActivity) onActivity(name);
        return { ok: false, error: run.error };
      }
      if (!run.timedOut) {
        const result = interpret(name, run);
        if (onActivity) onActivity(name);
        return result;
      }
    }
    const detail = isRead
      ? `ember ${name} timed out after ${timeoutMs} ms, and the one allowed retry timed out too`
      : `ember ${name} (a write) timed out after ${timeoutMs} ms; it was NOT retried; re-read state before offering Retry`;
    if (onActivity) onActivity(name);
    return { ok: false, error: appErrorInfo('APP-008', `${WHERE}.runCommand`, detail) };
  }

  /**
   * Interactive command under `--confirm json`.
   *
   * @returns {object} session with on('event'|'error'|'exit', cb),
   *   answer(text) and stop() (closing stdin, per plan §5.1).
   */
  function runConfirmSession(name, args = []) {
    if (!SESSION_COMMANDS.has(name)) {
      throw new TypeError(`${name} is not a confirm-session command`);
    }
    const argv = buildArgv(name, args, ['--confirm', 'json']);
    let child;
    try {
      child = spawnFn(argv[0], argv.slice(1), { env: childEnv(), stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (err) {
      child = null;
      return deadSession(appErrorInfo('APP-001', `${WHERE}.runConfirmSession`, safeText(err)));
    }

    const listeners = { event: [], error: [], exit: [] };
    const stderrLines = [];
    let idleTimer = setTimeout(() => finish(new Error('idle')), sessionIdleMs);
    let finished = false;
    let exitCode = null;

    function bumpIdle() {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => finish(new Error('idle')), sessionIdleMs);
    }

    function emitError(info) {
      for (const cb of listeners.error) cb(info);
    }

    function finish(cause) {
      if (finished) return;
      finished = true;
      clearTimeout(idleTimer);
      try {
        child.kill('SIGKILL');
      } catch {
        /* already gone */
      }
      if (cause && cause.message === 'idle') {
        emitError(appErrorInfo('APP-008', `${WHERE}.runConfirmSession`, `ember ${name} produced no output for ${sessionIdleMs} ms and was stopped`));
      }
      const first = stderrLines[0] ?? '';
      const parsed = exitCode === 1 && errorPattern ? parseErrorLine(first, errorPattern, stderrLines.slice(1)) : null;
      if (parsed) emitError(parsed);
      // [app 12] the session is over: the knowledge base may have changed.
      if (onActivity) onActivity(name);
      for (const cb of listeners.exit) cb({ exitCode });
    }

    child.stdout.setEncoding('utf8');
    let lineBuffer = '';
    child.stdout.on('data', (chunk) => {
      bumpIdle();
      lineBuffer += chunk;
      let newlineAt = lineBuffer.indexOf('\n');
      while (newlineAt !== -1) {
        const line = lineBuffer.slice(0, newlineAt);
        lineBuffer = lineBuffer.slice(newlineAt + 1);
        const result = parseEventLine(line);
        if (!result.ok) {
          emitError(result.error); // garbage line -> APP-002, D4
          finish(null);
          return;
        }
        for (const cb of listeners.event) cb(result.event);
        newlineAt = lineBuffer.indexOf('\n');
      }
    });
    child.stderr.on('data', (chunk) => {
      for (const line of String(chunk).split('\n')) {
        if (line !== '') stderrLines.push(line);
      }
    });
    child.on('error', (err) => {
      exitCode = null;
      emitError(appErrorInfo('APP-001', `${WHERE}.runConfirmSession`, safeText(err)));
      finish(null);
    });
    child.on('close', (code) => {
      exitCode = code;
      finish(null);
    });

    return {
      /** A validated session event: {event: 'block'|'prompt'|'message'|'summary', ...}. */
      on(channel, cb) {
        if (!(channel in listeners)) throw new TypeError(`unknown session channel: ${channel}`);
        listeners[channel].push(cb);
        return this;
      },
      /** Write one answer line: exactly `{"answer": "<text>"}` (L2 §5.4). */
      answer(text) {
        const line = answerLine(text);
        if (line === null) {
          emitError(appErrorInfo('APP-002', `${WHERE}.runConfirmSession.answer`, 'answer(text) refused: text is not a string'));
          return;
        }
        if (finished || child.stdin.destroyed) {
          emitError(appErrorInfo('APP-002', `${WHERE}.runConfirmSession.answer`, 'answer refused: the session is closed'));
          return;
        }
        child.stdin.write(line);
      },
      /** Stop: close stdin (the engine reads it as a quit, exit 2); a
       * backstop kill fires only if the child ignores the closed pipe. */
      stop() {
        try {
          child.stdin.end();
        } catch {
          /* already closed */
        }
        setTimeout(() => {
          try {
            child.kill('SIGKILL');
          } catch {
            /* already gone */
          }
        }, 2000);
      },
    };
  }

  function deadSession(error) {
    return {
      on(channel, cb) {
        if (channel === 'error') cb(error);
        if (channel === 'exit') cb({ exitCode: null });
        return this;
      },
      answer() {},
      stop() {},
    };
  }

  return { runCommand, runConfirmSession };
}

function safeText(err) {
  const text = err instanceof Error ? err.message : String(err);
  return `could not start the ember command: ${clip(text)}`;
}

function clip(text, max = 300) {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

module.exports = {
  createBridgeClient,
  READ_COMMANDS,
  FORMAT_JSON_COMMANDS,
  ALWAYS_JSON_COMMANDS,
  NO_DOC_COMMANDS,
  SESSION_COMMANDS,
};

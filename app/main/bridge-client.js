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

/**
 * The house error line may NOT be the first stderr line: `ember relate`
 * prints a model-change warning first (click.echo(..., err=True) in
 * ember/cli.py), and a later line carries the real `error: ...` shape.
 * Scan every line and parse the FIRST one matching the house pattern;
 * the lines after it become its detail. Without errorPattern or with
 * no matching line this returns null and the caller keeps its own
 * last-non-empty-line fallback (never guessed). Pure (T1).
 *
 * @param {string[]} stderrLines
 * @param {string | undefined} errorPattern
 * @returns {{code: string, name: string, where: string, detail: string} | null}
 */
function findHouseError(stderrLines, errorPattern) {
  if (!errorPattern) return null;
  for (let i = 0; i < stderrLines.length; i++) {
    const parsed = parseErrorLine(stderrLines[i], errorPattern, stderrLines.slice(i + 1));
    if (parsed) return parsed;
  }
  return null;
}

/**
 * Batch 5 chunk 3 (4.4 #1, #11; stories 18, 19, 30): a streaming line
 * reader for one untrusted child stream.
 *
 * WHY: a real pipe does not care where lines end. A house error line
 * can arrive in two piecewise writes (the first carries NO newline),
 * and a multi-byte character can be cut at a chunk boundary. Decoding
 * each chunk on its own (`String(chunk)`) splits such a line into
 * broken halves and mangles the half characters into U+FFFD; a reader
 * that only commits on '\n' drops the final unterminated line.
 *
 * This reader decodes with a STREAMING TextDecoder (a multi-byte
 * character cut at a chunk boundary survives), keeps the tail in a
 * carry buffer, commits a line only on '\n', and `flush()` (called
 * once, on child close) commits the final partial line (story 30).
 *
 * @param {(line: string) => void} [onLine] called for every complete line
 * @returns {{push: (chunk: Buffer) => void, flush: () => void}}
 */
function lineCollector(onLine) {
  const decoder = new TextDecoder();
  let carry = '';
  function commit(text) {
    // NOTE: empty lines are passed through — the stderr caller filters
    // them (as before); the stdout caller parses them like any line.
    if (onLine) onLine(text);
  }
  return {
    push(chunk) {
      carry += decoder.decode(chunk, { stream: true });
      let newlineAt = carry.indexOf('\n');
      while (newlineAt !== -1) {
        commit(carry.slice(0, newlineAt));
        carry = carry.slice(newlineAt + 1);
        newlineAt = carry.indexOf('\n');
      }
    },
    flush() {
      carry += decoder.decode(); // ends any pending multi-byte sequence
      if (carry !== '') commit(carry);
      carry = '';
    },
  };
}

/** Reads: timeout + at most one automatic retry (plan §5.1). */
const READ_COMMANDS = new Set([
  'list-items',
  'show-item',
  'current-state',
  'topic-search',
  'why',
  'history',
  'db-check',
]);

/**
 * Write-shaped one-shot commands: the write rule (timeout, NEVER
 * retried) wins over the read list. Fix F7: `capture-source` stores
 * the source text in the knowledge base, so a timeout retry could
 * store it twice.
 */
const WRITE_COMMANDS = new Set(['capture-source']);

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
 * @param {number} [options.sessionPromptWaitMs] how long the app waits
 *   for the USER while a prompt sits unanswered, default 1800000
 *   (30 minutes) — fix F4: a person may take longer than the output
 *   limit to decide; the child is still bounded (I15) and killed if
 *   the prompt is forgotten. Any child OUTPUT restarts the normal
 *   reading the answer.
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
    sessionPromptWaitMs = 30 * 60_000,
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
      const stderrLines = [];
      // Batch 5 chunk 3 (4.4 #1, #11): whole streamed lines.
      const stdoutDecoder = new TextDecoder();
      const stderrReader = lineCollector((line) => {
        if (line !== '') stderrLines.push(line);
      });
      let stdoutText = '';
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
        // Streamed decode (chunk 3): a multi-byte character cut at a
        // chunk boundary survives; the pieces join into the document.
        stdoutText += stdoutDecoder.decode(chunk, { stream: true });
      });
      child.stderr.on('data', (chunk) => {
        stderrReader.push(chunk); // whole streamed lines, chunk 3
      });

      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        // Chunk 3: flush on close — the final partial lines (no
        // trailing newline, and any pending multi-byte bytes) commit
        // here, which is the ONLY place that can see them.
        stdoutText += stdoutDecoder.decode();
        stderrReader.flush();
        resolve({
          failed: false,
          timedOut,
          tooLarge,
          exitCode: typeof child.exitCode === 'number' ? child.exitCode : child.signalCode,
          stdout: stdoutText,
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
    // Non-zero exit: the house error line on stderr is THE result
    // (wherever among the stderr lines it sits — F2).
    const first = run.stderrLines[0] ?? '';
    const parsed = findHouseError(run.stderrLines, errorPattern);
    if (parsed) return { ok: false, error: parsed };
    if (run.exitCode === 2) {
      return {
        ok: false,
        error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} exited 2 (usage error or user abort)${first ? `: ${clip(first)}` : ''}`),
      };
    }
    // No house line anywhere (e.g. a raw Python traceback): the REAL
    // cause is the LAST non-empty stderr line — a traceback ends with
    // the exception itself (`sqlite3.OperationalError: ...`), its
    // first line is only the `Traceback (most recent call last):`
    // header.
    // No house line anywhere (e.g. a raw Python traceback): the REAL
    // cause is the LAST non-empty stderr line — a traceback ends with
    // the exception itself (`sqlite3.OperationalError: ...`), its
    // first line is only the `Traceback (most recent call last):`
    // header.
    const causeLines = run.stderrLines.filter((l) => l.trim() !== '');
    const cause = causeLines[causeLines.length - 1] ?? '';
    return {
      ok: false,
      error: appErrorInfo('APP-002', `${WHERE}.runCommand`, `ember ${name} failed with an unparsable error line${cause ? `: ${clip(cause)}` : ' (no stderr)'}`),
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
    const isRead = READ_COMMANDS.has(name) && !WRITE_COMMANDS.has(name);
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
    // Batch 5 chunk 3 (4.4 #1, #11): whole streamed lines.
    const stderrReader = lineCollector((line) => {
      if (line !== '') stderrLines.push(line);
    });
    // Fix F4: two limits (I15 bounds both). `idle` = no child output
    // for sessionIdleMs. `prompt-wait` = the child asked a question
    // and the USER has not answered for sessionPromptWaitMs (default
    // 30 minutes — a person may read and think longer than the output
    // limit; a forgotten prompt still ends). Writing an answer hands
    // control back to the engine: the normal output limit applies
    // again. The SIGKILL backstop in finish() covers both.
    let idleTimer = null;
    let awaitingAnswer = false;
    let finished = false;
    let exitCode = null;

    function armOutputIdle() {
      idleTimer = setTimeout(() => finish(new Error('idle')), sessionIdleMs);
    }

    function armPromptWait() {
      idleTimer = setTimeout(() => finish(new Error('prompt-wait')), sessionPromptWaitMs);
    }

    function bumpIdle() {
      clearTimeout(idleTimer);
      if (awaitingAnswer) armPromptWait();
      else armOutputIdle();
    }
    armOutputIdle();

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
      } else if (cause && cause.message === 'prompt-wait') {
        emitError(appErrorInfo('APP-008', `${WHERE}.runConfirmSession`, `ember ${name} has been waiting for an answer for ${sessionPromptWaitMs} ms and was stopped`));
      }
      const first = stderrLines[0] ?? '';
      const parsed = exitCode === 1 ? findHouseError(stderrLines, errorPattern) : null;
      if (parsed) emitError(parsed);
      // [app 12] the session is over: the knowledge base may have changed.
      if (onActivity) onActivity(name);
      for (const cb of listeners.exit) cb({ exitCode });
    }

    function handleEventLine(line) {
      const result = parseEventLine(line);
      if (!result.ok) {
        emitError(result.error); // garbage line -> APP-002, D4
        finish(null);
        return;
      }
      for (const cb of listeners.event) cb(result.event);
      // F4: a prompt means the engine waits for the USER now, not
      // for output — arm the long prompt-wait limit.
      if (result.event.event === 'prompt') {
        awaitingAnswer = true;
        bumpIdle();
      }
    }
    // Chunk 3: the stream is decoded with a streaming TextDecoder and
    // lines commit only on '\n' — an event line split across two pipe
    // writes (even mid multi-byte character) still parses.
    const stdoutReader = lineCollector(handleEventLine);
    child.stdout.on('data', (chunk) => {
      bumpIdle();
      stdoutReader.push(chunk);
    });
    child.stderr.on('data', (chunk) => {
      stderrReader.push(chunk);
    });
    child.on('error', (err) => {
      exitCode = null;
      emitError(appErrorInfo('APP-001', `${WHERE}.runConfirmSession`, safeText(err)));
      finish(null);
    });
    child.on('close', (code) => {
      exitCode = code;
      if (!finished) {
        // Chunk 3 (story 30): flush on close — the final partial line
        // (NO trailing newline, story 30) and any pending multi-byte
        // bytes commit here, BEFORE the exit callbacks fire.
        stdoutReader.flush();
        stderrReader.flush();
      }
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
        // F4: the answer hands control back to the engine — the
        // normal output limit applies from here.
        awaitingAnswer = false;
        bumpIdle();
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

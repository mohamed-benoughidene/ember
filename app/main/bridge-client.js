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
 * Batch 5 chunk 6 (4.4 #6; spec bullet "the engine is started in its
 * own process group… a short hard bound for pipe close"): after the
 * ENGINE process is gone, its pipes may still be held open by a stray
 * helper process (a grandchild that inherited them). A settle that
 * waits on pipe close alone would wait for that helper's lifetime, so
 * the settle gives the pipes ONE short hard bound after process exit
 * and then finishes with whatever arrived.
 */
const PIPE_CLOSE_BOUND_MS = 3_000;

/**
 * Kill the engine's WHOLE process group (4.4 #6): children spawn
 * `detached`, so the child leads its own group and a negative-pid
 * signal reaches every member — a stuck grandchild included.
 * `child.kill` alone only ever hit the immediate child and left the
 * helper holding the pipes. Errors mean the target is already gone.
 */
function killProcessGroup(child, signal) {
  try {
    process.kill(-child.pid, signal);
  } catch {
    /* the process group is already gone */
  }
  try {
    child.kill(signal);
  } catch {
    /* already gone */
  }
}

/** TERM first (a polite chance to exit), KILL as the backstop. */
function stopEngineTree(child) {
  killProcessGroup(child, 'SIGTERM');
  setTimeout(() => killProcessGroup(child, 'SIGKILL'), 1000);
}

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
          // Batch 5 chunk 6 (4.4 #6): the engine leads its OWN process
          // group, so the timeout kill below reaches grandchildren too.
          detached: true,
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
      // Batch 5 chunk 6: armed on process 'exit' — the short hard
      // bound after which the run settles even if the pipes are still
      // held open by a stray grandchild.
      let pipeBoundTimer = null;

      const timer = setTimeout(() => {
        timedOut = true;
        stopEngineTree(child); // chunk 6: the WHOLE group, not just the child
      }, timeoutMs);

      child.stdout.on('data', (chunk) => {
        stdoutBytes += chunk.length;
        if (stdoutBytes > MAX_OUTPUT_BYTES) {
          tooLarge = true;
          stopEngineTree(child);
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
        clearTimeout(pipeBoundTimer);
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
      child.on('exit', () => {
        // Batch 5 chunk 6: the process is gone — settle is no longer
        // chained to pipe close (a grandchild may hold the pipes
        // forever). Give the readers ONE short hard bound to catch the
        // last bytes, then settle with what arrived. Normal runs never
        // wait this long: 'close' below fires first.
        if (settled) return;
        pipeBoundTimer = setTimeout(finish, PIPE_CLOSE_BOUND_MS);
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
      child = spawnFn(argv[0], argv.slice(1), {
        env: childEnv(),
        stdio: ['pipe', 'pipe', 'pipe'],
        // Batch 5 chunk 6 (4.4 #6): the session engine leads its OWN
        // process group, so every kill below reaches grandchildren too.
        detached: true,
      });
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
    // Batch 5 chunk 6: armed on process 'exit' — the short hard bound
    // after which the session settles even when a stray grandchild
    // still holds the pipes open.
    let pipeBoundTimer = null;
    // Batch 5 chunk 5 (4.2 #14, story 33): the session's stdout is
    // untrusted output too — track its bytes against the SAME cap the
    // one-shot path has and end the session with the named cap error.
    let stdoutBytes = 0;

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
      clearTimeout(pipeBoundTimer);
      // Chunk 6: the whole process group — a grandchild holding the
      // pipes would otherwise outlive the session.
      stopEngineTree(child);
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
    // Chunk 5 (4.4 #5): bumpIdle is fed by the LINE reader, so the
    // idle timer resets only when a COMPLETE line arrives — a chatty
    // child that never finishes a line still times out on idle, even
    // though its raw chunks keep arriving.
    const stdoutReader = lineCollector((line) => {
      bumpIdle();
      handleEventLine(line);
    });
    child.stdout.on('data', (chunk) => {
      stdoutBytes += chunk.length;
      if (stdoutBytes > MAX_OUTPUT_BYTES) {
        // 4.2 #14: end the session with the same named cap error the
        // one-shot interpret() step returns, then finish() SIGKILLs
        // the flooding child.
        if (!finished) {
          emitError(appErrorInfo('APP-002', `${WHERE}.runConfirmSession`, `ember ${name} printed more than ${MAX_OUTPUT_BYTES} bytes`));
          finish(null);
        }
        return;
      }
      stdoutReader.push(chunk);
    });
    child.stderr.on('data', (chunk) => {
      stderrReader.push(chunk);
    });
    // Batch 5 chunk 5 (4.4 #2): an answer written after the engine
    // stopped reading its stdin raises `write EPIPE` as an 'error'
    // event on this stdin stream. UNHANDLED, that error would take
    // down the whole app process (the reproduced exit-crash class of
    // finding 4.4 #2). With the handler it surfaces as the session's
    // named error and the session ends quietly.
    child.stdin.on('error', (err) => {
      if (finished) return;
      emitError(appErrorInfo('APP-002', `${WHERE}.runConfirmSession`, `the engine stopped reading its stdin; the answer could not be delivered: ${clip(err instanceof Error ? err.message : String(err))}`));
      finish(null);
    });
    child.on('error', (err) => {
      exitCode = null;
      emitError(appErrorInfo('APP-001', `${WHERE}.runConfirmSession`, safeText(err)));
      finish(null);
    });
    child.on('exit', (code) => {
      // Batch 5 chunk 6 (4.4 #6): the engine exited — remember its
      // real exit even if the pipes never close (a grandchild holds
      // them), and give the readers ONE short hard bound before the
      // session settles anyway. The 'close' handler below settles
      // sooner when the pipes close normally.
      exitCode = typeof code === 'number' ? code : (child.signalCode ?? null);
      if (finished) return;
      pipeBoundTimer = setTimeout(() => {
        // Pipe close never came (4.4 #6): flush the partial lines the
        // same way the 'close' handler does, then settle.
        stdoutReader.flush();
        stderrReader.flush();
        finish(null);
      }, PIPE_CLOSE_BOUND_MS);
    });
    child.on('close', (code) => {
      exitCode = typeof code === 'number' ? code : (child.signalCode ?? exitCode);
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
       * backstop kill fires only if the child ignores the closed pipe —
       * and since chunk 6 it reaches the WHOLE process group, so a
       * grandchild holding the pipes cannot survive the session. */
      stop() {
        try {
          child.stdin.end();
        } catch {
          /* already closed */
        }
        setTimeout(() => {
          killProcessGroup(child, 'SIGKILL');
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

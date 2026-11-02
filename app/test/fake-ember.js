#!/usr/bin/env node
'use strict';

/**
 * A tiny STAND-IN for the real `ember` executable, used ONLY by the
 * app's node tests and the e2e smoke (the real contract lives with the
 * Python suite; this stub just speaks its shapes).
 *
 * Modes come from the FAKE_MODE environment variable or, for the
 * one-shot cases, from argv. Parent processes find out how often they
 * spawned us by counting rows in the file named by FAKE_SPAWN_LOG (one
 * line per spawn), which lets tests pin the retry rule (reads: one
 * retry; writes: none).
 *
 * Shapes come straight from the pinned contract:
 * - list-items -> {"total": <N>, "items": [...]} on stdout, exit 0
 * - error      -> one stderr house line, exit 1
 * - garbage    -> non-JSON stdout, exit 0
 * - hang       -> writes nothing on purpose; killed by the client's
 *                 timeout (APP-008)
 * - session    -> `--confirm json` event lines on stdout, answers read
 *                 from stdin
 * - app        -> the step-04 read commands (list-items with its real
 *                 filter semantics plus the `--counts` form (Batch 5
 *                 chunk 11: one document, summary carries the four
 *                 Home counts), current-state, topic-search,
 *                 show-item, history, maintain --dry-run) answered from
 *                 the JSON fixture file named by FAKE_FIXTURE, with the
 *                 same envelopes the contract table pins. Unknown item
 *                 ids get the real house line (QUERY-001). Batch 3 F4:
 *                 FAKE_APP_FAIL (e2e-only, same style as
 *                 FAKE_ERROR_DETAIL) names a comma list of
 *                 `command:CODE` pairs; a matching command answers with
 *                 the one house line carrying that code and exits 1.
 * - crash      -> the REAL shape of an unexpected engine death (Batch 2
 *                 Chunk 14): a crash file named by FAKE_CRASH_ID into
 *                 $XDG_STATE_HOME/ember/crashes/, a raw traceback then
 *                 the house line `error: EMBER-000 InternalError |
 *                 fake-ember | crash=<id>`, exit 1.
 *
 * Batch 5 chunk 3 (4.4 #1, #11) adds two SPLIT modes so the JS readers
 * are pinned against the way a real pipe actually delivers bytes:
 * - FAKE_STDERR_SPLIT=1 (with FAKE_MODE=error): the house error line
 *   arrives in piecewise writes — one cut inside the name (the first
 *   piece is not a house line) and one inside a multi-byte character
 *   — so the reader must re-decode across a boundary AND rejoin the
 *   line.
 * - FAKE_STDOUT_SPLIT=1 (with FAKE_MODE=session): a JSON event line
 *   arrives in two writes with a multi-byte character cut at the
 *   boundary, and the LAST line arrives WITHOUT its newline (story
 *   30) — the reader must flush that final partial line when the
 *   child closes.
 * - FAKE_FLOOD=1 (Batch 5 chunk 5, 4.2 #14; any mode): stream ~40 MB
 *   to stdout in drain-aware chunks and end by CLOSING stdout — every
 *   byte really reaches the parent's reader, so the 32 MB cap is
 *   really hit.
 * - FAKE_SESSION_CLOSE_STDIN=1 (with FAKE_MODE=session, Batch 5 chunk
 *   5, 4.4 #2): the engine stops reading its stdin while the process
 *   stays alive — the app's next answer() hits a broken pipe (EPIPE).
 * - FAKE_EXIT_EARLY=1 (Batch 5 chunk 6, 4.4 #6 / story 20; any mode):
 *   the engine dies right after spawn, with NO output on either
 *   stream — the app must settle on the process exit, never hang.
 * - FAKE_GRANDCHILD=1 (with FAKE_MODE=session, Batch 5 chunk 6, 4.4 #6
 *   / story 21): the fake spawns a grandchild that INHERITS its
 *   stdout/stderr pipes and then exits itself. The parent's stdio can
 *   then only close when the grandchild dies — and the grandchild
 *   never dies on its own (a bare setInterval). The grandchild's pid
 *   is logged to FAKE_GRANDCHILD_LOG so a test can pin that the app's
 *   process-group kill really ended the stuck helper.
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

function noteSpawn() {
  if (process.env.FAKE_SPAWN_LOG) {
    fs.appendFileSync(process.env.FAKE_SPAWN_LOG, `${JSON.stringify(process.argv.slice(2))}\n`);
  }
}

/* ==== Batch 5 chunk 3 (4.4 #1, #11) ================================
   Write ONE line in TWO piecewise writes to the given stream. The cut
   lands INSIDE a multi-byte character when the line carries an
   ellipsis (U+2026, three UTF-8 bytes), so the reader must decode
   across the boundary; otherwise it cuts mid-line. The delay between
   the two writes makes the parent really receive two chunks (two
   reads) — the shape a per-chunk `String(chunk).split('\n')` cannot
   handle, because the first chunk carries no newline. ================ */
function splitWrite(stream, lineBuffer, done) {
  const mark = Buffer.from('…', 'utf8');
  const at = lineBuffer.indexOf(mark);
  const cut = at === -1 ? Math.floor(lineBuffer.length / 2) : at + 1;
  stream.write(lineBuffer.subarray(0, cut));
  setTimeout(() => {
    stream.write(lineBuffer.subarray(cut));
    done();
  }, 25);
}

/* ==== Batch 5 chunk 5 (4.2 #14, story 33; the db-check F8 pattern) ==
   FAKE_FLOOD=1: stream ~40 MB (640 event lines of 64 KB) to
   stdout in DRAIN-AWARE writes (wait for 'drain', so no byte sits in
   the child's own buffer) and end by CLOSING stdout. Deliberately
   NOT `process.exit()` (4.2 #2): exit would drop still-pending bytes
   and the parent could settle under its output cap without ever
   seeing them. `process.exitCode` + the natural end after stdout
   closes guarantees every byte really reaches the parent's reader.
   For the SESSION half (story 33) the chunks are VALID confirm event
   lines: a chatty engine floods with event lines, and line-shaped
   chunks keep the parent's carry reader at its normal cost — a
   newline-free megabyte flood would grind the reader's carry buffer
   long before the cap (see the chunk-5 report note). The stream still
   really exceeds the 32 MB cap, which is what the tests pin. ====== */
function runFlood() {
  // ~640 lines of 64 KB = ~40 MB. Small lines keep the parent's per-
  // line parse cheap (a 1 MB JSON text per line made the same test
  // take 7.7 s in GC); the byte total still really exceeds the cap.
  const big = Buffer.from(`${JSON.stringify({ event: 'message', text: 'x'.repeat(64 * 1024 - 64) })}\n`);
  let n = 0;
  function writeChunk() {
    if (n >= 640) {
      process.exitCode = 0;
      process.stdout.end();
      return;
    }
    n += 1;
    if (process.stdout.write(big)) writeChunk();
    else process.stdout.once('drain', writeChunk);
  }
  writeChunk();
}

const mode = process.env.FAKE_MODE ?? 'list';
const argv = process.argv.slice(2);

if (!argv.includes('--db')) {
  process.stderr.write('error: QUERY-003 DbOpenFailed | fake-ember | db file missing | db_path=\n');
  process.exit(1);
}

noteSpawn();

/* `ember init --db <path>` — the stub's minimum for the create-on-purpose
   command the engine has had since Batch 4 chunk 5. A missing file is
   created (a real init writes the full migrated schema; the stub-driven
   scenarios never read the file's contents), an existing file is left
   untouched and still succeeds (N8 idempotence). The FAKE_MODE env vars
   do NOT apply here: a crash or a mid-session death is a capture-session
   story, and the app's first-Add seed (B4-07) must run like the real
   engine's init does. */
if (argv[0] === 'init') {
  const target = argv[argv.indexOf('--db') + 1] ?? null;
  if (!fs.existsSync(target)) fs.writeFileSync(target, '');
  process.exit(0);
}

/* Batch 5 chunk 6 (4.4 #6, story 20): FAKE_EXIT_EARLY=1 — the engine
   dies right after spawn, with NO output on either stream. The app
   must settle the session (or call) on the process exit itself, never
   hang waiting for a summary that will not come. */
if (process.env.FAKE_EXIT_EARLY === '1') {
  process.exit(0);
}

/* Batch 2 Chunk 14 (see the crash mode above). Mirrors the real edge
   handler's leave-behind loosely: the crash file keeps a raw traceback
   shape; the last stderr line is the one house line naming the id. */
function runCrashMode() {
  const crashId = process.env.FAKE_CRASH_ID ?? '00000000T000000Z-e2ecr0';
  const stateHome = process.env.XDG_STATE_HOME;
  if (typeof stateHome !== 'string' || stateHome.trim() === '') {
    process.stderr.write('error: EMBER-000 InternalError | fake-ember | crash mode needs XDG_STATE_HOME (the stub never touches the real state folder)\n');
    process.exit(1);
  }
  const dir = path.join(stateHome, 'ember', 'crashes');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, `${crashId}.txt`),
    [
      'engine version: 0.0.0-fake-ember',
      'command: capture',
      'time: 2026-11-01T12:00:00Z',
      'Traceback (most recent call last):',
      '  File "ember/capture/confirm_write.py", line 132, in run_confirm_loop',
      'RuntimeError: fake crash injected by the e2e stub',
      '',
    ].join('\n'),
  );
  process.stderr.write('Traceback (most recent call last):\n');
  process.stderr.write('  File "ember/capture/confirm_write.py", line 132, in run_confirm_loop\n');
  process.stderr.write('RuntimeError: fake crash injected by the e2e stub\n');
  process.stderr.write(`error: EMBER-000 InternalError | fake-ember | crash=${crashId}\n`);
  process.exit(1);
}

function hangAndSleep() {
  // Stay alive until killed; print nothing (the client's timeout and
  // APP-008 are what the test wants to see).
  setInterval(() => {}, 10_000);
}

function printListDocument() {
  const total = Number(process.env.FAKE_TOTAL ?? '2');
  const items = [];
  for (let i = 1; i <= total; i += 1) {
    items.push({
      id: i,
      type: 'Finding',
      statement: `fake item ${i}`,
      status: 'Active',
      close_reason: null,
      rationale: null,
      source: null,
      validated: null,
      created_at: '2026-10-30T00:00:00Z',
    });
  }
  process.stdout.write(`${JSON.stringify({ total, items })}\n`);
  process.exit(0);
}

if (process.env.FAKE_FLOOD === '1') {
  // Batch 5 chunk 5 (4.2 #14): the flood comes first — whatever the
  // mode would have printed, the test wants ~40 MB of stdout.
  runFlood();
} else if (mode === 'hang') {
  hangAndSleep();
} else if (mode === 'app') {
  runAppMode(argv);
} else if (mode === 'list') {
  printListDocument();
} else if (mode === 'slow') {
  /* A healthy read that merely takes a while: 400 ms of silence, then
     the SAME list-items document the list mode prints, exit 0. The
     5000 ms default limits must let it answer (never APP-008). */
  setTimeout(printListDocument, 400);
} else if (mode === 'garbage') {
  process.stdout.write('definitely not one json document\n');
  process.exit(0);
} else if (mode === 'error') {
  const detail = process.env.FAKE_ERROR_DETAIL ?? 'db file missing';
  const withNewline = process.env.FAKE_ERROR_MULTILINE === '1';
  const rest = withNewline
    ? `free text with a | inside and\na second line`
    : detail;
  const houseLine = `error: QUERY-003 DbOpenFailed | fake.ember | ${rest}\n`;
  if (process.env.FAKE_STDERR_SPLIT === '1') {
    /* Batch 5 chunk 3 (4.4 #1): the house line arrives in piecewise
       writes — the first cut lands INSIDE the name (so the first
       piece is NOT a house line: the reader must rejoin the pieces
       before any parse), the second cut lands INSIDE a multi-byte
       character (the ellipsis in the detail: the reader must re-decode
       across the boundary). A per-chunk String(chunk).split('\n')
       breaks on both. */
    const leading = Buffer.from('error: QUERY-003 DbOpenFail', 'utf8');
    const middle = Buffer.from('ed | fake.ember | db file', 'utf8');
    const ellipsis = Buffer.from('…', 'utf8');
    const tail = Buffer.from(' missing\ncontinuation line one\ncontinuation line two\n', 'utf8');
    process.stderr.write(leading);
    setTimeout(() => {
      process.stderr.write(Buffer.concat([middle, ellipsis.subarray(0, 1)]));
      setTimeout(() => {
        process.stderr.write(Buffer.concat([ellipsis.subarray(1), tail]));
        process.exit(1);
      }, 25);
    }, 25);
  } else {
    process.stderr.write(houseLine);
    process.stderr.write('continuation line one\ncontinuation line two\n');
    process.exit(1);
  }
} else if (mode === 'unparsable-error') {
  process.stderr.write('this is not the house error line at all\n');
  process.exit(1);
} else if (mode === 'warning-then-error') {
  /* Fix F2: a warning line prints BEFORE the house error line (the
     real `ember relate` does this with its model-change warning), so
     the client must scan past it. */
  process.stderr.write('warning: embedding model changed since build\n');
  process.stderr.write('error: RELATE-036 AiResponseWriteFailed | fake.ember | raw answer save failed | item_id=3\n');
  process.exit(1);
} else if (mode === 'traceback') {
  /* An UNEXPECTED engine death: a raw Python traceback, no house line
     anywhere. The client must fall back to stderr and keep the LAST
     line (the `sqlite3.OperationalError` cause), not the first
     `Traceback` line. */
  process.stderr.write('Traceback (most recent call last):\n');
  process.stderr.write('  File "ember/adapters/sqlite.py", line 118, in open_database\n');
  process.stderr.write('sqlite3.OperationalError: database disk image is malformed\n');
  process.exit(1);
} else if (mode === 'crash') {
  /* Batch 2 Chunk 14: a session death the way the REAL edge handler
     leaves it (Chunk 2): the crash file first, then a raw traceback,
     then the EMBER-000 house line that names the crash id. The file
     goes ONLY into the scenario's own $XDG_STATE_HOME — with the
     variable unset this stub refuses (it must never touch the
     developer's real ~/.local/state). */
  runCrashMode();
} else if (mode === 'session') {
  runSession();
} else if (mode === 'relate') {
  /* App 06 (ticket A35): the scripted relate confirm session — see
     runRelateSession at the end of this file. */
  runRelateSession();
} else {
  process.stderr.write('error: QUERY-003 DbOpenFailed | fake.ember | unknown FAKE_MODE | mode=\n');
  process.exit(1);
}

function runSession() {
  /* ==== Batch 5 chunk 5 (4.4 #5): a CHATTY child that never finishes
     a line — fragment after fragment, no '\n' — never resets the idle
     timer (only COMPLETE lines feed bumpIdle), so the inactivity
     limit must end it even though raw chunks keep arriving. NO other
     output and especially NO prompt: a prompt would arm the 30-minute
     prompt-wait limit instead of the output idle limit. ==== */
  if (process.env.FAKE_SESSION_NO_FULL_LINE === '1') {
    setInterval(() => {
      process.stdout.write('working fragment, never terminated');
    }, 50);
    return;
  }

  const events = process.env.FAKE_SESSION_IDLE === '1'
    // Fix F4: a frozen engine has asked NO question — only non-prompt
    // output, so the client's normal inactivity limit must end it.
    ? [{ event: 'message', text: 'working' }]
    : process.env.FAKE_SESSION_SCRIPT
    ? JSON.parse(process.env.FAKE_SESSION_SCRIPT)
    : [
        { event: 'message', text: 'reading the file' },
        {
          event: 'block',
          kind: 'item',
          fields: { id: 1, type: 'Finding', statement: 'fake statement' },
          text: '- id: 1',
        },
        { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [q]uit', choices: ['y', 'n', 'q'] },
        // `line` and `aborted` are here because the REAL engine's summary
        // always carries them (ember/cli.py passes the human line and
        // `aborted` for capture/relate/maintain alike) — the app's field
        // check (batch 5, 4.4 #7/#8) refuses a summary without them, so
        // the stub must mimic the real shape.
        { event: 'summary', line: 'accepted: 1, rejected: 0, aborted: false', accepted: 1, rejected: 0, aborted: false },
      ];

  // Emit the whole pinned stream, then wait for ONE answer line and
  // report its shape, so the test can pin answer() -> the child
  // received exactly `{"answer": "<text>"}`.
  if (process.env.FAKE_STDOUT_SPLIT === '1') {
    /* ==== Batch 5 chunk 3 (story 30, 4.4 #11) =======================
       Split mode: a JSON event line arrives in TWO writes with a
       multi-byte character cut at the boundary, and the LAST line
       arrives WITHOUT its newline (the pipe closed mid-line). The
       stub then exits 0 without waiting for answers — the reader
       must flush that final partial line on close. The other session
       env modes (FAKE_SESSION_DIE / IDLE / SCRIPT) do not combine
       with this one. */
    const tail = events[events.length - 1];
    // Prefix an ellipsis to the FIRST event's text so the split can
    // land inside a multi-byte character (JSON.stringify keeps raw).
    const head = events.slice(0, -1).map((e, i) =>
      i === 0 && typeof e.text === 'string' && !e.text.includes('…')
        ? { ...e, text: `…${e.text}` }
        : e,
    );
    const [firstLine, ...otherLines] = head.map((e) => Buffer.from(`${JSON.stringify(e)}\n`, 'utf8'));
    splitWrite(process.stdout, firstLine, () => {
      for (const line of otherLines) process.stdout.write(line);
      setTimeout(() => {
        // The final line has NO trailing newline (story 30).
        process.stdout.write(Buffer.from(JSON.stringify(tail), 'utf8'));
        setTimeout(() => process.exit(0), 20);
      }, 25);
    });
    return;
  }
  for (const e of events) {
    process.stdout.write(`${JSON.stringify(e)}\n`);
  }

  /* ==== Batch 5 chunk 6 (4.4 #6, story 21): FAKE_GRANDCHILD=1 ========
     The fake emits its scripted events, then spawns a GRANDCHILD that
     inherits its stdout/stderr pipes, then exits itself. The parent's
     stdio can then only close when the grandchild dies — the
     `setInterval` child never does — so a settle that waits on pipe
     close waits on the grandchild's lifetime. The grandchild's pid is
     logged to FAKE_GRANDCHILD_LOG so the test can pin that the app's
     process-group kill ended the stuck helper. ===================== */
  if (process.env.FAKE_GRANDCHILD === '1') {
    const grandchild = spawn('node', ['-e', 'setInterval(() => {}, 1000)'], {
      // Inherit the SESSION pipes: the child holds the same stdout and
      // stderr the app's reader is waiting on. NOT detached — the
      // grandchild stays in the fake's process group, which is exactly
      // what the app's group kill must reach.
      stdio: ['ignore', 'inherit', 'inherit'],
    });
    if (process.env.FAKE_GRANDCHILD_LOG) {
      fs.appendFileSync(process.env.FAKE_GRANDCHILD_LOG, `${grandchild.pid}\n`);
    }
    process.exit(0);
  }

  /* ==== Batch 5 chunk 5 (4.4 #2): the engine stops reading its stdin
     (the way a crashed or past-prompt engine does) while the PROCESS
     stays alive. The next answer the app writes then hits a broken
     pipe (EPIPE); the session must surface that as an error event,
     never a crash. Verified in a standalone repro: Node's
     process.stdin.destroy() does NOT close fd 0 (stdio fds are kept
     open on purpose), so the REAL fd is closed here — the parent's
     write then raises write EPIPE, and without an 'error' handler on
     child.stdin the parent process DIES on the unhandled error. */
  if (process.env.FAKE_SESSION_CLOSE_STDIN === '1') {
    try {
      fs.closeSync(0);
    } catch {
      /* already closed */
    }
    setInterval(() => {}, 10_000);
    return;
  }

  /* ==== App 05 (ticket A34): die mid-session, for the add e2e ======
     The child emits its scripted events and then dies without ever
     reading stdin — the app must show the error state, never hang. */
  if (process.env.FAKE_SESSION_DIE === '1') {
    process.exit(Number(process.env.FAKE_SESSION_DIE_CODE ?? '1'));
  }
  /* ==== end App 05 block ==== */

  if (process.env.FAKE_SESSION_IDLE === '1') {
    // Test mode: output is above, then go silent forever — the
    // client's inactivity limit (APP-008) is what must end this.
    setInterval(() => {}, 10_000);
    return;
  }

  const answers = [];
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    for (const line of String(chunk).split('\n')) {
      if (line.trim() === '') continue;
      answers.push(line);
    }
  });
  process.stdin.on('end', () => {
    // The app called stop(): a quiet, normal end.
    process.exit(2);
  });
  const check = setInterval(() => {
    if (answers.length > 0) {
      clearInterval(check);
      if (process.env.FAKE_SESSION_SILENT_AFTER_ANSWER === '1') {
        /* Fix F4 test mode: the answer was received and the engine
           hangs forever with no output — the client's POST-answer
           inactivity limit is what must end this, not the long
           prompt-wait. */
        setInterval(() => {}, 10_000);
        return;
      }
      let parsed = null;
      try {
        parsed = JSON.parse(answers[0]);
      } catch {
        parsed = null;
      }
      const okShape =
        typeof parsed === 'object' &&
        parsed !== null &&
        typeof parsed.answer === 'string' &&
        Object.keys(parsed).length === 1;
      process.stdout.write(
        `${JSON.stringify({ event: 'message', text: `answer-shape-ok: ${okShape}, answer-was: ${parsed ? parsed.answer : 'unparsable'}` })}\n`,
      );
      setTimeout(() => process.exit(0), 20);
    }
  }, 10);
}

/* ---------- mode "app": the step-04 read commands over a fixture ---------- */

function runAppMode(argv) {
  const name = argv[0];
  /* ==== Batch 3 F4 (e2e-only, same style as FAKE_ERROR_DETAIL) ======
     FAKE_APP_FAIL holds a comma list of `command:CODE` pairs (e.g.
     `list-items:QUERY-003,history:QUERY-005`): when the command name
     matches a pair, answer with the one house error line carrying that
     code and exit 1. The spawn is already logged (noteSpawn above), so
     a failing command still shows up in the spawn log. */
  const appFail = process.env.FAKE_APP_FAIL;
  if (appFail) {
    for (const pair of appFail.split(',')) {
      const sep = pair.indexOf(':');
      if (sep === -1) continue;
      const [cmd, code] = [pair.slice(0, sep), pair.slice(sep + 1)];
      if (cmd === name) {
        process.stderr.write(`error: ${code} CommandFailed | fake.ember.${name} | the fake was told to fail this command\n`);
        process.exit(1);
        return;
      }
    }
  }
  const flag = (flagName) => {
    const i = argv.indexOf(flagName);
    return i === -1 ? null : argv[i + 1];
  };
  let fx;
  try {
    fx = JSON.parse(require('node:fs').readFileSync(process.env.FAKE_FIXTURE, 'utf8'));
  } catch (err) {
    process.stderr.write(`error: APP-002 BridgeOutputInvalid | fake-ember.app | the FAKE_FIXTURE file could not be read: ${err.message}\n`);
    process.exit(1);
    return;
  }
  const items = fx.items ?? [];
  const statusFilter = flag('--status');
  const typeFilter = flag('--type');

  if (name === 'list-items' || name === 'current-state') {
    /* ==== Batch 5 chunk 11 (N11) ==================================
       `list-items --counts` — the one call that answers the four Home
       counts. The real command (pinned shape, chunk 10) prints ONE
       document whose `summary` carries `active` / `challenged` /
       `closed` / `total`, derived the same way the per-status
       documents above are: from the fixture's items, filtering by
       status. A status outside the three named ones counts only
       toward `total` (the real counter's rule, ember/query/
       list_items.py). Like the real command, --counts ignores the
       filter and paging flags. ==================================== */
    if (name === 'list-items' && argv.includes('--counts')) {
      const summary = { active: 0, challenged: 0, closed: 0 };
      for (const it of items) {
        if (it.status === 'Active') summary.active += 1;
        else if (it.status === 'Challenged') summary.challenged += 1;
        else if (it.status === 'Closed') summary.closed += 1;
      }
      summary.total = items.length;
      process.stdout.write(`${JSON.stringify({ summary })}\n`);
      process.exit(0);
    }
    let rows = items.filter(
      (it) => (statusFilter === null || it.status === statusFilter) && (typeFilter === null || it.type === typeFilter),
    );
    if (name === 'current-state') {
      rows = rows
        .filter((it) => it.status !== 'Closed')
        .sort((a, b) => (a.status === 'Challenged' ? 0 : 1) - (b.status === 'Challenged' ? 0 : 1))
        .map((it) => ({
          id: it.id, type: it.type, statement: it.statement, status: it.status,
          created_at: it.created_at, source_id: 1, status_origin: 'derived', challenged: it.status === 'Challenged',
        }));
      process.stdout.write(`${JSON.stringify({ mode: 'current_state', count: rows.length, items: rows })}\n`);
      process.exit(0);
    }
    const total = rows.length;
    const offset = Number(flag('--offset') ?? '0');
    const limit = flag('--limit') === null ? null : Number(flag('--limit'));
    const page = limit === null ? rows.slice(offset) : rows.slice(offset, offset + limit);
    process.stdout.write(`${JSON.stringify({ total, items: page })}\n`);
    process.exit(0);
  }

  if (name === 'topic-search') {
    const query = String(flag('--query') ?? '').toLowerCase();
    const limit = flag('--limit') === null ? null : Number(flag('--limit'));
    const offset = Number(flag('--offset') ?? '0');
    let rows = items.filter(
      (it) =>
        it.statement.toLowerCase().includes(query) &&
        (statusFilter === null || it.status === statusFilter) &&
        (typeFilter === null || it.type === typeFilter),
    );
    const hits = rows.map((it, i) => ({ item_id: it.id, score: 1 - i * 0.01, type: it.type, statement: it.statement, status: it.status }));
    // `total` is the pre-page count (Batch 6): every match before the
    // offset skip and the limit cap, like the real engine's envelope.
    const total = hits.length;
    const page = limit === null ? hits.slice(offset) : hits.slice(offset, offset + limit);
    process.stdout.write(`${JSON.stringify({ mode: 'topic_search', query: flag('--query') ?? '', total, count: page.length, results: page })}\n`);
    process.exit(0);
  }

  if (name === 'show-item') {
    const id = Number(flag('--item'));
    const doc = (fx.show ?? {})[String(id)];
    if (!doc) {
      process.stderr.write(`error: QUERY-001 QueryItemNotFound | fake.ember.show-item | item ${id} is not in items\n`);
      process.exit(1);
    }
    process.stdout.write(`${JSON.stringify(doc)}\n`);
    process.exit(0);
  }

  if (name === 'history') {
    // The real engine renders the ledger NEWEST first (`(timestamp, id)`
    // descending, Batch 6 finding 4.7 #13) and decodes a status row's
    // new value to its plain status (the `Closed:<reason>` encoding stays
    // only in the ledger). The fixture already mirrors that shape; the
    // sort here keeps the answer engine-true regardless of fixture order.
    let events = (fx.history ?? []).slice();
    events.sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0));
    const itemFilter = flag('--item') === null ? null : Number(flag('--item'));
    if (itemFilter !== null) {
      events = events.filter((e) => e.item_id === itemFilter);
    }
    const since = flag('--since');
    if (since !== null) events = events.filter((e) => e.timestamp >= since);
    const offset = Number(flag('--offset') ?? '0');
    const limit = flag('--limit') === null ? null : Number(flag('--limit'));
    const page = limit === null ? events.slice(offset) : events.slice(offset, offset + limit);
    process.stdout.write(`${JSON.stringify({ mode: 'history', item_id: itemFilter, count: page.length, events: page })}\n`);
    process.exit(0);
  }

  if (name === 'maintain' && argv.includes('--dry-run')) {
    // The real command (pinned shape): with --format json --confirm json
    // a dry run emits ONE message event whose text is the document.
    const changes = Array.from({ length: Number(fx.pending ?? 0) }, (_, i) => ({ item_id: i + 1, to: 'Challenged' }));
    const document = {
      changes,
      command: 'maintain',
      dry_run: true,
      summary: { challenged: 0, closed: 0, reopened: 0, unchanged: items.length, stale: 0, proposed: 0, accepted: 0, rejected: 0, aborted: false },
    };
    process.stdout.write(`${JSON.stringify({ event: 'message', text: JSON.stringify(document) })}\n`);
    process.exit(0);
  }

  /* ==== App 06 (ticket A35) =========================================
     relate runs THROUGH the app mode (one stub child serves the reads
     AND the session, exactly like the real ember): the scripted
     pinned `--confirm json` shapes in runRelateSession below. ==== */
  if (name === 'relate') {
    runRelateSession();
    return;
  }

  process.stderr.write(`error: APP-002 BridgeOutputInvalid | fake.ember.app | the app mode does not speak: ${name}\n`);
  process.exit(1);
}

/* ==== App 06 (ticket A35): the scripted relate confirm session ======
   FAKE_MODE=relate serves the PINNED `ember relate --confirm json`
   shapes (ember/bridge/block_parse.py + docs/commands.md): a
   `link-preview` block BEFORE each choice prompt, the accepted
   `link` block AFTER a write, `relate rejected: ...` lines as message
   events, and the summary event (with accepted/rejected/skipped/
   aborted) last. Env:

   - FAKE_RELATE_EMPTY=1        -> the engine's documented empty-pool
                                  print, then exit 0 (no summary).
   - FAKE_RELATE_SLOW=1         -> emit NOTHING and go silent (the
                                  story-45 preparing state); stdin
                                  end (Stop) is a quiet exit 2.
   - FAKE_RELATE_SCRIPT=<json>  -> the rounds. One array per proposal:
                                  [preview block, choice prompt, (
                                  accepted-block after a y)] and an
                                  optional final round that carries
                                  the message + summary events. The
                                  stub waits for ONE answer line
                                  between rounds and logs every
                                  answer it received, one JSON line
                                  per answer, to the file named by
                                  FAKE_RELATE_ANSWERS (the e2e pins
                                  the y/s/n/q mapping with it).
   ==================================================================== */

function runRelateSession() {
  const answers = [];
  const answerFile = process.env.FAKE_RELATE_ANSWERS;
  let rounds = [];
  if (process.env.FAKE_RELATE_SCRIPT) rounds = JSON.parse(process.env.FAKE_RELATE_SCRIPT);

  function writeAnswers() {
    if (answerFile) fs.writeFileSync(answerFile, answers.map((a) => `${a}\n`).join(''));
  }

  if (process.env.FAKE_RELATE_ERROR === '1') {
    // The refused-at-boot path: one house error line on stderr, exit 1
    // (e.g. the missing optional package, RELATE-017). The bridge
    // client parses it; the screen shows the plain words.
    process.stderr.write(
      `error: ${process.env.FAKE_RELATE_ERROR_CODE ?? 'RELATE-017 EmbedderLoadFailed'} | fake.ember.relate | ${process.env.FAKE_RELATE_ERROR_DETAIL ?? 'sentence_transformers is not installed; install the optional extra with: python -m pip install -e ".[relate]"'}\n`,
    );
    process.exit(1);
  }

  if (process.env.FAKE_RELATE_EMPTY === '1') {
    process.stdout.write(`${JSON.stringify({ event: 'message', text: 'no unrelated items' })}\n`);
    setTimeout(() => process.exit(0), 20);
    return;
  }

  if (process.env.FAKE_RELATE_SLOW === '1') {
    // Silent forever, like a minutes-long model download, until the
    // app stops the session (stdin end -> the story-45 quiet exit 2).
    setInterval(() => {}, 10_000);
    process.stdin.setEncoding('utf8');
    process.stdin.resume(); // start consuming, so EOF fires 'end'
    process.stdin.on('end', () => process.exit(2));
    return;
  }

  let served = 0; // rounds emitted so far
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    for (const line of String(chunk).split('\n')) {
      if (line.trim() === '') continue;
      answers.push(line);
    }
  });
  process.stdin.on('end', () => {
    // The app called stop(): a quiet, normal end (exit 2, no summary).
    writeAnswers();
    process.exit(2);
  });

  function emitNextRound() {
    if (served >= rounds.length) {
      writeAnswers();
      process.exit(Number(process.env.FAKE_RELATE_EXIT ?? '0'));
      return;
    }
    const round = rounds[served];
    served += 1;
    for (const e of round) {
      process.stdout.write(`${JSON.stringify(e)}\n`);
    }
    if (round.some((e) => e.event === 'summary')) {
      // The summary round needs no answer: the run is over.
      writeAnswers();
      setTimeout(() => process.exit(Number(process.env.FAKE_RELATE_EXIT ?? '0')), 20);
      return;
    }
    // Wait for ONE answer, then serve the next round (stdin stays open).
    const check = setInterval(() => {
      if (answers.length >= served) {
        clearInterval(check);
        emitNextRound();
      }
    }, 10);
  }

  emitNextRound();
}

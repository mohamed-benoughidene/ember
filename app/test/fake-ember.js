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
 */

const fs = require('node:fs');

function noteSpawn() {
  if (process.env.FAKE_SPAWN_LOG) {
    fs.appendFileSync(process.env.FAKE_SPAWN_LOG, `${JSON.stringify(process.argv.slice(2))}\n`);
  }
}

const mode = process.env.FAKE_MODE ?? 'list';
const argv = process.argv.slice(2);

if (!argv.includes('--db')) {
  process.stderr.write('error: QUERY-003 DbOpenFailed | fake-ember | db file missing | db_path=\n');
  process.exit(1);
}

noteSpawn();

function hangAndSleep() {
  // Stay alive until killed; print nothing (the client's timeout and
  // APP-008 are what the test wants to see).
  setInterval(() => {}, 10_000);
}

if (mode === 'hang') {
  hangAndSleep();
} else if (mode === 'list') {
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
} else if (mode === 'garbage') {
  process.stdout.write('definitely not one json document\n');
  process.exit(0);
} else if (mode === 'error') {
  const detail = process.env.FAKE_ERROR_DETAIL ?? 'db file missing';
  const withNewline = process.env.FAKE_ERROR_MULTILINE === '1';
  const rest = withNewline
    ? `free text with a | inside and\na second line`
    : detail;
  process.stderr.write(`error: QUERY-003 DbOpenFailed | fake.ember | ${rest}\n`);
  process.stderr.write('continuation line one\ncontinuation line two\n');
  process.exit(1);
} else if (mode === 'unparsable-error') {
  process.stderr.write('this is not the house error line at all\n');
  process.exit(1);
} else if (mode === 'session') {
  runSession();
} else {
  process.stderr.write('error: QUERY-003 DbOpenFailed | fake.ember | unknown FAKE_MODE | mode=\n');
  process.exit(1);
}

function runSession() {
  const events = process.env.FAKE_SESSION_SCRIPT
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
        { event: 'summary', accepted: 1, rejected: 0 },
      ];

  // Emit the whole pinned stream, then wait for ONE answer line and
  // report its shape, so the test can pin answer() -> the child
  // received exactly `{"answer": "<text>"}`.
  for (const e of events) {
    process.stdout.write(`${JSON.stringify(e)}\n`);
  }
  if (process.env.FAKE_SESSION_IDLE === '1') {
    // Test mode: produce output once, then go silent forever — the
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

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
 *                 filter semantics, current-state, topic-search,
 *                 show-item, history, maintain --dry-run) answered from
 *                 the JSON fixture file named by FAKE_FIXTURE, with the
 *                 same envelopes the contract table pins. Unknown item
 *                 ids get the real house line (QUERY-001).
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
} else if (mode === 'app') {
  runAppMode(argv);
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

function runSession() {  const events = process.env.FAKE_SESSION_SCRIPT
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

/* ---------- mode "app": the step-04 read commands over a fixture ---------- */

function runAppMode(argv) {
  const name = argv[0];
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
    let rows = items.filter(
      (it) =>
        it.statement.toLowerCase().includes(query) &&
        (statusFilter === null || it.status === statusFilter) &&
        (typeFilter === null || it.type === typeFilter),
    );
    const hits = rows.map((it, i) => ({ item_id: it.id, score: 1 - i * 0.01, type: it.type, statement: it.statement, status: it.status }));
    const page = limit === null ? hits : hits.slice(0, limit);
    process.stdout.write(`${JSON.stringify({ mode: 'topic_search', query: flag('--query') ?? '', count: page.length, results: page })}\n`);
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
    let events = (fx.history ?? []).slice();
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

  process.stderr.write(`error: APP-002 BridgeOutputInvalid | fake.ember.app | the app mode does not speak: ${name}\n`);
  process.exit(1);
}

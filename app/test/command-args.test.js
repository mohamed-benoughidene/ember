'use strict';

/**
 * The argv builders (app/main/command-args.js): every flag list must be
 * exactly what the bridge contract table pins (`docs/commands.md`
 * "Machine use" + tests/bridge/test_contract_table.py). The app adapts
 * to the bridge, never the reverse — so topic-search gets NO --offset,
 * history's --since is ISO-8601 WITH an offset, and filters use the
 * engine's exact values.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  listItemsArgs,
  topicSearchArgs,
  showItemArgs,
  historyArgs,
  sinceInputToIso,
  STATUSES,
  TYPES,
} = require('../main/command-args');

test('list-items argv: the pinned flags, in a sane order', () => {
  assert.deepEqual(listItemsArgs({}), []);
  assert.deepEqual(listItemsArgs({ status: 'Challenged' }), ['--status', 'Challenged']);
  assert.deepEqual(
    listItemsArgs({ status: 'Closed', type: 'Question', limit: 50, offset: 100 }),
    ['--status', 'Closed', '--type', 'Question', '--limit', '50', '--offset', '100'],
  );
  assert.deepEqual(listItemsArgs({ limit: 1 }), ['--limit', '1'], 'limit 1 crops the page and keeps the total');
  assert.deepEqual(listItemsArgs({ limit: 0 }), ['--limit', '0'], 'limit 0 is the explicit empty page');
  assert.throws(() => listItemsArgs({ status: 'Whatever' }), TypeError);
  assert.throws(() => listItemsArgs({ limit: -1 }), TypeError);
  assert.throws(() => listItemsArgs({ limit: 1.5 }), TypeError);
  assert.throws(() => listItemsArgs({ offset: 'x' }), TypeError);
});

test('topic-search argv: --query always, --limit only (the command has no --offset)', () => {
  assert.deepEqual(topicSearchArgs({ query: 'sqlite' }), ['--query', 'sqlite']);
  assert.deepEqual(
    topicSearchArgs({ query: 'sqlite', status: 'Active', type: 'Decision', limit: 20 }),
    ['--query', 'sqlite', '--status', 'Active', '--type', 'Decision', '--limit', '20'],
  );
  assert.throws(() => topicSearchArgs({ query: '   ' }), TypeError, 'an empty query must be the list, never a bare search');
  assert.throws(() => topicSearchArgs({ query: 42 }), TypeError);
  assert.throws(() => topicSearchArgs({ query: 'sqlite', limit: -3 }), TypeError);
});

test('show-item argv', () => {
  assert.deepEqual(showItemArgs(7), ['--item', '7']);
  assert.throws(() => showItemArgs(null), TypeError);
  assert.throws(() => showItemArgs('seven'), TypeError);
});

test('history argv: --item/--limit/--offset/--since with a UTC offset on --since', () => {
  assert.deepEqual(historyArgs({}), []);
  assert.deepEqual(historyArgs({ item: 3, limit: 10, offset: 20 }), ['--item', '3', '--limit', '10', '--offset', '20']);
  const since = sinceInputToIso('2026-10-30');
  assert.equal(since, '2026-10-30T00:00:00.000Z', 'a date input becomes the moment the day begins, in UTC');
  assert.deepEqual(historyArgs({ item: 3, since }), ['--item', '3', '--since', since]);
  assert.deepEqual(historyArgs({ since: since }), ['--since', since]);
  assert.throws(() => historyArgs({ item: -2 }), TypeError);
});

test('sinceInputToIso: off (null) when empty, null when unparsable (QUERY-007 unreachable by construction)', () => {
  assert.equal(sinceInputToIso(''), null);
  assert.equal(sinceInputToIso(null), null);
  assert.equal(sinceInputToIso('not a date'), null);
  assert.equal(sinceInputToIso('2026-02-30'), null, 'a day that never existed is not a date');
  assert.match(sinceInputToIso('2026-01-01'), /Z$|\+\d{2}:\d{2}$/, 'the engine demands an ISO-8601 timestamp WITH an offset');
});

test('the filter vocabularies are exactly the engine values', () => {
  assert.deepEqual([...STATUSES].sort(), ['Active', 'Challenged', 'Closed']);
  assert.deepEqual([...TYPES].sort(), ['Assumption', 'Decision', 'Finding', 'Question']);
});

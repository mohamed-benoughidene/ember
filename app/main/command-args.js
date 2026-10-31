'use strict';

/**
 * The argv builders for the step-04 read commands (app step file §1).
 *
 * CONTRACT RULE: every builder emits exactly the flags the bridge
 * contract table pins (`tests/bridge/test_contract_table.py` +
 * `docs/commands.md` "Machine use"):
 * - `list-items --status S --type T --limit N --offset N`
 * - `topic-search --query T --status S --type T --limit N` (NO --offset:
 *   the command has no such flag — the app adapts to the bridge, never
 *   the reverse)
 * - `show-item --item N`
 * - `history --item N --limit N --offset N --since TS` (TS is ISO-8601
 *   WITH an offset; QUERY-007 otherwise)
 * - `current-state` (no flags)
 *
 * Builders THROW a TypeError on a value the command would refuse
 * (negative page numbers, non-integer item ids, wrong filter values),
 * so the caller's wrap turns it into a named refusal. Pure module (T1):
 * unit-tested in app/test/command-args.test.js.
 */

const STATUSES = ['Active', 'Challenged', 'Closed'];
const TYPES = ['Decision', 'Assumption', 'Finding', 'Question'];

function optionalFlag(argv, flag, value, allow) {
  if (value === null || value === undefined || value === '') return;
  if (allow && !allow.includes(value)) {
    throw new TypeError(`invalid ${flag} value: ${String(value)}`);
  }
  argv.push(flag, String(value));
}

function nonNegativeInt(value, what) {
  const n = Number(value);
  if (value === null || value === undefined || value === '') return null;
  if (!Number.isInteger(n) || n < 0) throw new TypeError(`${what} must be a whole number from 0 up, got ${String(value)}`);
  return n;
}

/** The browse page: every item in any status, Closed included. */
function listItemsArgs({ status = null, type = null, limit = null, offset = null } = {}) {
  const argv = [];
  optionalFlag(argv, '--status', status, STATUSES);
  optionalFlag(argv, '--type', type, TYPES);
  const lim = nonNegativeInt(limit, '--limit');
  const off = nonNegativeInt(offset, '--offset');
  if (lim !== null) argv.push('--limit', String(lim));
  if (off !== null) argv.push('--offset', String(off));
  return argv;
}

/** The keyword search. `query` is required and always sent. */
function topicSearchArgs({ query, status = null, type = null, limit = null } = {}) {
  if (typeof query !== 'string' || query.trim() === '') {
    throw new TypeError('topic-search needs --query text (the screen only calls it with a query)');
  }
  const argv = ['--query', query];
  optionalFlag(argv, '--status', status, STATUSES);
  optionalFlag(argv, '--type', type, TYPES);
  const lim = nonNegativeInt(limit, '--limit');
  if (lim !== null) argv.push('--limit', String(lim));
  return argv;
}

/** One item: statement, source (verbatim), and all links both ways. */
function showItemArgs(item) {
  const n = nonNegativeInt(item, '--item');
  if (n === null) throw new TypeError('show-item needs --item N');
  return ['--item', String(n)];
}

/**
 * The ledger view, item-scoped or global, paged and dated.
 * `since` is a full ISO-8601 timestamp with a UTC offset (the command
 * refuses naive or garbage input with QUERY-007).
 */
function historyArgs({ item = null, limit = null, offset = null, since = null } = {}) {
  const argv = [];
  const n = nonNegativeInt(item, '--item');
  if (n !== null) argv.push('--item', String(n));
  const lim = nonNegativeInt(limit, '--limit');
  const off = nonNegativeInt(offset, '--offset');
  if (lim !== null) argv.push('--limit', String(lim));
  if (off !== null) argv.push('--offset', String(off));
  if (typeof since === 'string' && since.trim() !== '') argv.push('--since', since);
  return argv;
}

/**
 * Turn a date-input value ("2026-10-30") into the ISO-8601 text with a
 * UTC offset that `history --since` accepts: the moment the day begins,
 * in UTC (a plain Z offset, which ISO-8601 allows). Empty input means
 * the filter is off (null). Unparsable input returns null — the screen
 * shows its own message, the command is never called with a bad value
 * (QUERY-007 stays unreachable by construction).
 */
function sinceInputToIso(value) {
  if (typeof value !== 'string' || value.trim() === '') return null;
  const text = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const date = new Date(`${text}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  // A date that never existed (2026-02-30) rolls over in the parser;
  // the round trip catches it, so --since never receives one.
  if (date.toISOString().slice(0, 10) !== text) return null;
  // 'YYYY-MM-DD' parsed as plain UTC midnight; toISOString renders the
  // same moment with the required UTC offset designator.
  return date.toISOString();
}

module.exports = {
  STATUSES,
  TYPES,
  listItemsArgs,
  topicSearchArgs,
  showItemArgs,
  historyArgs,
  sinceInputToIso,
};

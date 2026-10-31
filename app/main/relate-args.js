'use strict';

/**
 * The argv builder for the Link items session (app step 06).
 *
 * CONTRACT RULE (the step-02/07 rule reused): the builder emits exactly
 * the flags the bridge contract table pins (`tests/bridge/
 * test_contract_table.py` + `docs/commands.md` "Machine use"):
 * - `relate --item N --confirm json` (the user picks from a list; the
 *   app never types an id it did not read from `list-items`)
 * - `relate --latest --confirm json` (the newest unrelated Active item)
 *
 * `--confirm json` and `--db` are added by the bridge client, never
 * here. The two item flags are mutually exclusive and one of them is
 * required (the command usage-errors with exit 2 otherwise); the
 * builder throws a TypeError on a bad value so the IPC wrap turns it
 * into a named APP-002 refusal and the child is never started with a
 * shape the command would refuse. Pure module (T1): unit-tested in
 * app/test/relate-args.test.js.
 */

function requireId(value) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) {
    throw new TypeError(`--item must be a whole number from 1 up, got ${String(value)}`);
  }
  return n;
}

/**
 * The argv (WITHOUT `--db`/`--confirm json`) for one relate start.
 * Exactly one of `item` / `latest` must be given.
 */
function relateArgs({ item = null, latest = false } = {}) {
  if (item !== null && item !== undefined && latest) {
    throw new TypeError('relate takes one of --item or --latest, not both');
  }
  if (latest) return ['--latest'];
  if (item === null || item === undefined) {
    throw new TypeError('relate needs one of --item or --latest');
  }
  return ['--item', String(requireId(item))];
}

module.exports = { relateArgs };

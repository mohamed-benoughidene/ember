'use strict';

/**
 * The argv builders for the step-07 Fix and close write commands
 * (app step file §1).
 *
 * CONTRACT RULE (the step-02 rule reused): every builder emits exactly
 * the flags the bridge contract table pins (`tests/bridge/
 * test_contract_table.py` + `docs/commands.md`):
 * - `set-status --item N --to Active|Challenged`   (no --dry-run: the command has none)
 * - `close-item --item N --reason invalidated|expired [--dry-run]`
 * - `edit-item --item N --field rationale|source --value TEXT [--dry-run]`
 * - `remove-link --link N [--dry-run]`
 * - `reverse-supersedes --item N --link N`         (no --dry-run)
 * - `set-validated --item N` / `clear-validated --item N`
 * - `undo [--dry-run]` / `redo [--dry-run]`
 *
 * The bridge client adds `--db` and `--format json` (undo/redo and the
 * field-document commands); `set-validated`/`clear-validated` print no
 * document, so the app uses the exit code and re-reads `show-item`.
 *
 * Builders THROW a TypeError on a value the command would refuse (bad
 * status, machine close reason, `statement` — the known but forbidden
 * edit field, non-integer ids), so the IPC wrap turns it into a named
 * APP-002 refusal and the command is never started. Pure module (T1):
 * unit-tested in app/test/fix-close-args.test.js.
 */

const STATUS_TARGETS = ['Active', 'Challenged'];
const HUMAN_CLOSE_REASONS = ['invalidated', 'expired'];
const EDIT_FIELDS = ['rationale', 'source'];
const FLIP_COMMANDS = ['set-validated', 'clear-validated'];
const UNDO_COMMANDS = ['undo', 'redo'];

/** Every action the Fix and close screen may run through this module. */
const FIX_ACTIONS = [
  'set-status',
  'close-item',
  'edit-item',
  'remove-link',
  'reverse-supersedes',
  ...FLIP_COMMANDS,
  ...UNDO_COMMANDS,
];

function requireId(value, what) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) {
    throw new TypeError(`${what} must be a whole number from 1 up, got ${String(value)}`);
  }
  return n;
}

function requireOneOf(value, allowed, what) {
  if (!allowed.includes(value)) {
    throw new TypeError(`${what} must be one of ${allowed.join(', ')}, got ${String(value)}`);
  }
  return value;
}

/**
 * The argv (WITHOUT `--db`, which the bridge client always adds) for
 * one Fix and close action. `payload` carries the action's inputs;
 * `dryRun` (for the commands that have the flag) previews without
 * writing.
 */
function fixActionArgs(action, payload = {}) {
  if (!FIX_ACTIONS.includes(action)) {
    throw new TypeError(`unknown Fix and close action: ${String(action)}`);
  }
  const dry = payload.dryRun === true ? ['--dry-run'] : [];
  switch (action) {
    case 'set-status':
      return [
        '--item',
        String(requireId(payload.item, '--item')),
        '--to',
        requireOneOf(payload.to, STATUS_TARGETS, '--to'),
      ];
    case 'close-item': {
      const reason = requireOneOf(payload.reason, HUMAN_CLOSE_REASONS, '--reason');
      return ['--item', String(requireId(payload.item, '--item')), '--reason', reason, ...dry];
    }
    case 'edit-item': {
      const field = requireOneOf(payload.field, EDIT_FIELDS, '--field');
      if (typeof payload.value !== 'string' || payload.value.trim() === '') {
        throw new TypeError('--value must be non-empty text');
      }
      // Values ride as ONE argv element: the command quotes it, the
      // shell never sees it (the bridge client spawns without a shell).
      return ['--item', String(requireId(payload.item, '--item')), '--field', field, '--value', payload.value, ...dry];
    }
    case 'remove-link':
      return ['--link', String(requireId(payload.link, '--link')), ...dry];
    case 'reverse-supersedes':
      // The engine's precondition (closed as superseded + a confirmed,
      // unreversed link pointing at it) is the command's job to refuse
      // (MAINTAIN-005); the screen only needs both ids.
      return ['--item', String(requireId(payload.item, '--item')), '--link', String(requireId(payload.link, '--link'))];
    case 'set-validated':
    case 'clear-validated':
      return ['--item', String(requireId(payload.item, '--item'))];
    case 'undo':
    case 'redo':
      return dry;
    default:
      throw new TypeError(`unknown Fix and close action: ${String(action)}`);
  }
}

/**
 * The dry-run argv for the undo/redo LABEL derivation (stories 113,
 * 121): `undo --dry-run` / `redo --dry-run`. `command` must be exactly
 * 'undo' or 'redo'.
 */
function undoPlanArgs(command) {
  requireOneOf(command, UNDO_COMMANDS, 'command');
  return ['--dry-run'];
}

module.exports = {
  STATUS_TARGETS,
  HUMAN_CLOSE_REASONS,
  EDIT_FIELDS,
  FIX_ACTIONS,
  fixActionArgs,
  undoPlanArgs,
};

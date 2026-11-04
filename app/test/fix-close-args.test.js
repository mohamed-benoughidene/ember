'use strict';

/**
 * The step-07 argv builders (app/main/fix-close-args.js): every action
 * emits EXACTLY the flags the bridge contract table pins
 * (`tests/bridge/test_contract_table.py` + docs/commands.md) — real
 * pinned flags only, no invented ones. Values the engine would refuse
 * never reach a child process: the builder throws, the IPC wrap names
 * the refusal (APP-002).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { fixActionArgs, undoPlanArgs, FIX_ACTIONS } = require('../main/fix-close-args');

test('set-status emits the pinned flags and refuses bad values', () => {
  assert.deepEqual(fixActionArgs('set-status', { item: 3, to: 'Active' }), ['--item', '3', '--to', 'Active']);
  assert.deepEqual(fixActionArgs('set-status', { item: 3, to: 'Challenged' }), ['--item', '3', '--to', 'Challenged']);
  assert.throws(() => fixActionArgs('set-status', { item: 3, to: 'Closed' }), /--to/); // the command takes only Active|Challenged
  assert.throws(() => fixActionArgs('set-status', { item: 0, to: 'Active' }), /--item/);
  assert.throws(() => fixActionArgs('set-status', { item: 'x', to: 'Active' }), /--item/);
});

test('close-item carries reason and the optional dry-run (human reasons only)', () => {
  assert.deepEqual(
    fixActionArgs('close-item', { item: 1, reason: 'invalidated', dryRun: true }),
    ['--item', '1', '--reason', 'invalidated', '--dry-run'],
  );
  assert.deepEqual(fixActionArgs('close-item', { item: 1, reason: 'expired' }), ['--item', '1', '--reason', 'expired']);
  // The machine reasons are refused here, exactly as the engine refuses them.
  for (const reason of ['superseded', 'answered', 'reversed']) {
    assert.throws(() => fixActionArgs('close-item', { item: 1, reason }), /--reason/);
  }
});

test('edit-item writes only rationale on any item it is given, never statement', () => {
  assert.deepEqual(
    fixActionArgs('edit-item', { item: 5, field: 'rationale', value: 'new why', dryRun: true }),
    ['--item', '5', '--field', 'rationale', '--value', 'new why', '--dry-run'],
  );
  assert.deepEqual(
    fixActionArgs('edit-item', { item: 5, field: 'source', value: 'p. 3 of the report' }),
    ['--item', '5', '--field', 'source', '--value', 'p. 3 of the report'],
  );
  // `statement` is the known but forbidden field (story 55): the builder
  // throws, so no child process is ever started for it.
  assert.throws(() => fixActionArgs('edit-item', { item: 1, field: 'statement', value: 'x' }), /--field/);
  assert.throws(() => fixActionArgs('edit-item', { item: 1, field: 'rationale', value: '  ' }), /--value/);
  assert.throws(() => fixActionArgs('edit-item', { item: 1, field: 'rationale', value: 7 }), /--value/);
});

test('remove-link, reverse-supersedes and the validated flip use their pinned flags', () => {
  assert.deepEqual(fixActionArgs('remove-link', { link: 9, dryRun: true }), ['--link', '9', '--dry-run']);
  assert.deepEqual(fixActionArgs('remove-link', { link: 9 }), ['--link', '9']);
  assert.deepEqual(fixActionArgs('reverse-supersedes', { item: 1, link: 2 }), ['--item', '1', '--link', '2']); // the command has NO --dry-run (a dryRun input is simply never sent)
  assert.deepEqual(fixActionArgs('set-validated', { item: 3 }), ['--item', '3']);
  assert.deepEqual(fixActionArgs('clear-validated', { item: 3 }), ['--item', '3']);
  assert.throws(() => fixActionArgs('set-validated', { item: -1 }), /--item/);
});

test('undo and redo send only the dry-run flag, and unknown actions refuse', () => {
  assert.deepEqual(fixActionArgs('undo', {}), []);
  assert.deepEqual(fixActionArgs('undo', { dryRun: true }), ['--dry-run']);
  assert.deepEqual(fixActionArgs('redo', { dryRun: true }), ['--dry-run']);
  assert.deepEqual(undoPlanArgs('undo'), ['--dry-run']);
  assert.deepEqual(undoPlanArgs('redo'), ['--dry-run']);
  assert.throws(() => undoPlanArgs('maintain'), /command/);
  assert.throws(() => fixActionArgs('capture', {}), /unknown Fix and close action/);
  assert.throws(() => fixActionArgs('drop-table', {}), /unknown Fix and close action/);
  assert.deepEqual([...FIX_ACTIONS].sort(), [
    'clear-validated', 'close-item', 'edit-item', 'redo', 'remove-link',
    'reverse-supersedes', 'set-status', 'set-validated', 'undo',
  ].sort(), 'exactly the nine Fix and close commands, no extras');
});

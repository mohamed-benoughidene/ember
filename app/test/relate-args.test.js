'use strict';

/**
 * Unit tests for the Link items argv builder (app step 06,
 * main/relate-args.js): exactly the flags the bridge contract table
 * pins — `relate --item N --confirm json` or `relate --latest --confirm
 * json`, never both, never neither, never a bad id. The child is never
 * started with a shape the command would usage-refuse (exit 2).
 */

const test = require('node:test');
const assert = require('node:assert/strict');

const { relateArgs } = require('../main/relate-args');

test('an item pick builds exactly --item N', () => {
  assert.deepEqual(relateArgs({ item: 3 }), ['--item', '3']);
  assert.deepEqual(relateArgs({ item: '7' }), ['--item', '7']);
});

test('the latest pick builds exactly --latest', () => {
  assert.deepEqual(relateArgs({ latest: true }), ['--latest']);
});

test('both flags together refuse (the command usage-errors otherwise)', () => {
  assert.throws(() => relateArgs({ item: 1, latest: true }), /one of --item or --latest/);
});

test('neither flag refuses; the app never starts a flagless relate', () => {
  assert.throws(() => relateArgs({}), /one of --item or --latest/);
  assert.throws(() => relateArgs(), /one of --item or --latest/);
  assert.throws(() => relateArgs({ item: null }), /one of --item or --latest/);
});

test('a bad id refuses before any child can start (APP-002 at the edge)', () => {
  assert.throws(() => relateArgs({ item: 0 }), /whole number from 1 up/);
  assert.throws(() => relateArgs({ item: -2 }), /whole number from 1 up/);
  assert.throws(() => relateArgs({ item: 1.5 }), /whole number from 1 up/);
  assert.throws(() => relateArgs({ item: 'abc' }), /whole number from 1 up/);
});

test('the bad-id refusal names the flag: --item, never "undefined" (4.8 #10)', () => {
  // Batch 6: the refusal must read "--item must be a whole number
  // from 1 up, got 0" — today requireId is called with no label, so
  // the message says "undefined must be a whole number …".
  for (const bad of [0, -2, 1.5, 'abc']) {
    let message = '';
    try {
      relateArgs({ item: bad });
      assert.fail(`a bad id (${String(bad)}) must refuse`);
    } catch (err) {
      message = err instanceof Error ? err.message : String(err);
    }
    assert.match(message, /--item must be a whole number from 1 up/);
    assert.ok(!message.includes('undefined'), 'the refusal names --item, not "undefined"');
  }
});

test('the builder never emits --confirm json or --db (the bridge client adds them)', () => {
  for (const built of [relateArgs({ item: 1 }), relateArgs({ latest: true })]) {
    assert.ok(!built.includes('--confirm'));
    assert.ok(!built.includes('--db'));
  }
});

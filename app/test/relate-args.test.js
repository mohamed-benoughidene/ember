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

test('the builder never emits --confirm json or --db (the bridge client adds them)', () => {
  for (const built of [relateArgs({ item: 1 }), relateArgs({ latest: true })]) {
    assert.ok(!built.includes('--confirm'));
    assert.ok(!built.includes('--db'));
  }
});

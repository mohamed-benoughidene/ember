'use strict';

/**
 * Pure screen logic for step 04, unit-tested without a DOM:
 * - the shared key shape rule (decision 5-A: shape and length at save;
 *   the real refusal is the first Add's, step 05);
 * - the selectable lookup row's pure HTML (named, keyboard reachable);
 * - the interim pane list (the placeholder shells Home's buttons target).
 */

const test = require('node:test');
const assert = require('node:assert/strict');

test('the key shape rule (shared by the screen and the setKey edge)', async () => {
  const { checkKeyShape, MIN_KEY_LENGTH } = await import('../shared/key-shape.mjs');
  assert.ok(MIN_KEY_LENGTH >= 20, 'decision 5-A: a real key has at least 20 characters');
  assert.deepEqual(checkKeyShape(''), { ok: false, reason: 'empty' });
  assert.deepEqual(checkKeyShape('   '), { ok: false, reason: 'empty' });
  assert.deepEqual(checkKeyShape(undefined), { ok: false, reason: 'empty' });
  assert.deepEqual(checkKeyShape('shortkey'), { ok: false, reason: 'short' });
  assert.deepEqual(checkKeyShape('k'.repeat(MIN_KEY_LENGTH - 1)), { ok: false, reason: 'short' });
  assert.deepEqual(checkKeyShape('a key with spaces in it'), { ok: false, reason: 'whitespace' });
  assert.deepEqual(checkKeyShape('line\nbreak'), { ok: false, reason: 'whitespace' });
  assert.deepEqual(checkKeyShape('sk-or-v1-abcdef1234567890abcd'), { ok: true });
  assert.deepEqual(checkKeyShape('  padded-but-real-key-1234567890  '), { ok: true }, 'outer whitespace is trimmed, not refused');
});

test('the lookup item row is a named, keyboard-reachable control', async () => {
  const { itemRowHtml } = await import('../renderer/screens/lookup.mjs');
  const row = itemRowHtml({ id: 3, type: 'Finding', statement: 'Two people <edited> the file.', status: 'Challenged' }, false);
  assert.match(row, /tabindex="0"/, 'keyboard reachable');
  assert.match(row, /aria-label="Item 3, Finding: Two people &lt;edited&gt; the file\., Challenged"/, 'named for assistive tech');
  assert.match(row, /aria-selected="false"/);
  assert.match(row, /status-pill-challenged/, 'the heat mark with its word');
  assert.doesNotMatch(row, /role="button"/, 'rows keep their table semantics');
});

test('the interim panes are exactly the six unbuilt screens', async () => {
  const { paneNames } = await import('../renderer/screens/placeholder.mjs');
  assert.deepEqual(paneNames().sort(), ['add', 'cleanup', 'fix', 'keepsafe', 'link', 'settings']);
});

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

test('a timed-out WRITE re-reads state first and says "may not have been done" (F3)', async () => {
  const { writeTimeoutNeedsReload } = await import('../renderer/screens/fix-close.mjs');
  // A write timeout is the ambiguous case: reload before the Retry offer.
  assert.equal(writeTimeoutNeedsReload('APP-008', true), true);
  // Reads (the dry-run previews) and every other keep the old behaviour.
  assert.equal(writeTimeoutNeedsReload('APP-008', false), false);
  assert.equal(writeTimeoutNeedsReload('MAINTAIN-025', true), false);
  assert.equal(writeTimeoutNeedsReload(null, true), false);
  assert.equal(writeTimeoutNeedsReload(undefined, true), false);
});

test('error codes appear only behind the Details affordance (4.9 #23)', async (t) => {
  await t.test('no bare code text outside the Details reveal in screens or shared', async () => {
    const fs = require('node:fs');
    const path = require('node:path');
    // A code in visible message text: the `(code ${…})` interpolation or a
    // literal `code APP-nnn` printed inline. The established Details path
    // (blocks.mjs / components/state-block.mjs) hides the raw code line
    // behind a `data-testid="error-code"` element the Details button
    // reveals — lines carrying that marker are the legitimate path.
    const BARE_CODE_TEXT = /code \$\{|\bcode APP-\d{3}\b/;
    const offenders = [];
    for (const dir of ['renderer/screens', 'shared']) {
      const names = fs.readdirSync(path.join(__dirname, '..', dir)).filter((f) => f.endsWith('.mjs')).sort();
      for (const name of names) {
        const lines = fs.readFileSync(path.join(__dirname, '..', dir, name), 'utf8').split('\n');
        lines.forEach((line, i) => {
          if (BARE_CODE_TEXT.test(line) && !line.includes('data-testid="error-code"')) {
            offenders.push(`app/${dir}/${name}:${i + 1}: ${line.trim().slice(0, 120)}`);
          }
        });
      }
    }
    assert.deepEqual(
      offenders,
      [],
      `bare error-code text outside a Details affordance (keep the plain words in the message; move the code behind the Details reveal as blocks.mjs does):\n${offenders.join('\n')}`,
    );
  });
});

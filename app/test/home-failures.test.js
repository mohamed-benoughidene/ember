'use strict';

/**
 * The Home failure grouping core (Batch 3, F4 — Impl-Batch3.md chunk 3).
 * `groupFailuresByCode` folds a list of `{ what, error }` failed blocks
 * into ONE row per distinct error code (decision B3-1: the notice
 * replaces the per-block cards), in first-seen code order.
 *
 * Wording ownership (decisions I7 and I10): the count sentence's exact
 * wording is decided inside `home-failures.mjs` and pinned ONLY here —
 * this file is the sentence's own unit test. The e2e (chunk 4) checks
 * the numbers and the codes on screen and never the wording; every
 * OTHER unit test stays off the wording too.
 *
 * The plain words per code come from the shared sentence table
 * (`plain-sentences.mjs`), so an unknown or shapeless error still
 * lands in a group and never reads as a blank (story 102's rule).
 */

const test = require('node:test');
const assert = require('node:assert/strict');

test('home failures grouping', async (t) => {
  const { groupFailuresByCode } = await import('../shared/home-failures.mjs');
  const { sentenceFor } = await import('../shared/plain-sentences.mjs');

  const fail = (what, code) => ({ what, error: code === undefined ? null : { code, name: 'X', where: 'w', detail: 'd' } });

  await t.test('grouping by code keeps first-seen order', () => {
    const failures = [
      fail('attention', 'QUERY-005'),
      fail('ledger', 'QUERY-003'),
      fail('counts', 'QUERY-005'),
    ];
    const groups = groupFailuresByCode(failures);
    assert.deepEqual(
      groups.map((g) => g.code),
      ['QUERY-005', 'QUERY-003'],
      'the codes come back in the order they were first seen, not sorted'
    );
    // A later repeat of an earlier code must not open a new group.
    const firstSeen = [
      fail('a', 'QUERY-003'),
      fail('b', 'QUERY-005'),
      fail('c', 'QUERY-003'),
    ];
    assert.deepEqual(
      groupFailuresByCode(firstSeen).map((g) => g.code),
      ['QUERY-003', 'QUERY-005']
    );
  });

  await t.test('the count equals the number of failed blocks per code (3-of-one and 2+1)', () => {
    const oneCode = groupFailuresByCode([
      fail('attention', 'QUERY-003'),
      fail('counts', 'QUERY-003'),
      fail('ledger', 'QUERY-003'),
    ]);
    assert.equal(oneCode.length, 1, 'three blocks with one code are ONE group (B3-1)');
    assert.equal(oneCode[0].count, 3);

    const twoCodes = groupFailuresByCode([
      fail('attention', 'QUERY-003'),
      fail('counts', 'QUERY-003'),
      fail('ledger', 'QUERY-005'),
    ]);
    assert.equal(twoCodes.length, 2, 'a 2+1 split is two groups');
    assert.equal(twoCodes[0].count, 2);
    assert.equal(twoCodes[1].count, 1);
    assert.deepEqual(
      twoCodes.map((g) => g.count),
      twoCodes.map((g) => g.blocks.length),
      'the count always equals that group\'s blocks list'
    );
  });

  await t.test('each group carries the names of its failed blocks, in input order', () => {
    const groups = groupFailuresByCode([
      fail('attention', 'QUERY-003'),
      fail('ledger', 'QUERY-005'),
      fail('counts', 'QUERY-003'),
    ]);
    const byCode = new Map(groups.map((g) => [g.code, g]));
    assert.deepEqual(byCode.get('QUERY-003').blocks, ['attention', 'counts']);
    assert.deepEqual(byCode.get('QUERY-005').blocks, ['ledger']);
  });

  await t.test('each group carries the plain words from sentenceFor(code), so two codes differ visibly', () => {
    const groups = groupFailuresByCode([
      fail('attention', 'QUERY-003'),
      fail('ledger', 'QUERY-005'),
    ]);
    const table = (code) => {
      const words = sentenceFor(code);
      return { title: words.title, what: words.what, next: words.next };
    };
    for (const g of groups) {
      const plain = table(g.code);
      assert.equal(g.words.title, plain.title, `${g.code}'s title is the table's title`);
      assert.equal(g.words.what, plain.what);
      assert.equal(g.words.next, plain.next);
      for (const field of ['title', 'what', 'next']) {
        assert.ok(String(g.words[field]).trim() !== '', `${g.code}.${field} is never blank`);
      }
    }
    assert.notEqual(
      groups[0].words.title,
      groups[1].words.title,
      'two different codes get visibly different titles'
    );
  });

  await t.test('a null/shapeless error still lands in a group, never blank', () => {
    for (const shapeless of [null, undefined, 'garbage', {}, { code: 7 }]) {
      const groups = groupFailuresByCode([{ what: 'attention', error: shapeless }]);
      assert.equal(groups.length, 1, `a ${JSON.stringify(shapeless)} error still gets one group`);
      const plain = sentenceFor(null);
      assert.equal(groups[0].words.title, plain.title, 'the group falls back to the no-code words');
      assert.equal(groups[0].words.what, plain.what);
      assert.equal(groups[0].words.next, plain.next);
      assert.deepEqual(groups[0].blocks, ['attention'], 'the block is still named');
    }
    // Mixed: a real code and a shapeless error stay two separate groups.
    const mixed = groupFailuresByCode([fail('a', 'QUERY-003'), { what: 'b', error: null }]);
    assert.equal(mixed.length, 2);
    assert.equal(mixed[1].words.title, sentenceFor(null).title);
  });

  await t.test('the count sentence wording is pinned ONLY here (I7/I10)', () => {
    const one = groupFailuresByCode([fail('attention', 'QUERY-003')])[0];
    assert.equal(one.words.countSentence, '1 block failed with this error.');
    const many = groupFailuresByCode([
      fail('attention', 'QUERY-003'),
      fail('counts', 'QUERY-003'),
      fail('ledger', 'QUERY-003'),
    ])[0];
    assert.equal(many.words.countSentence, '3 blocks failed with this error.');
    // The count sentence carries the number (I7: the e2e reads number + code).
    assert.match(many.words.countSentence, /\b3\b/);
  });
});

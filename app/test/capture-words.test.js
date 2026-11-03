'use strict';

/**
 * The Add screen's words table's own test (capture-words.mjs). Per the
 * test-wording rule (I10's exception), the words tables' own unit tests
 * MAY pin wording; every other test asserts codes and data only.
 *
 * Pinned here: the two true facts of an Add failure after proposing
 * (the true facts of `ember/cli.py`'s capture command: `stored =
 * _store(conn, raw_text)` runs BEFORE `_propose`, and items are written
 * only inside the confirm loop): the text WAS saved as a source, and NO
 * ITEMS were made. Finding 4.5 #6 (sentence half): "nothing was
 * created" is untrue — the source row exists.
 */

const test = require('node:test');
const assert = require('node:assert/strict');

test('capture words', async (t) => {
  const { addErrorSentence } = await import('../shared/capture-words.mjs');

  await t.test('an Add failure states the note was saved and no items were made (4.5 #6)', () => {
    for (const code of ['CAPTURE-008', 'CAPTURE-022']) {
      const s = addErrorSentence({ code, name: 'x', where: 'x', detail: 'x' });
      assert.match(s.what, /Your text is kept word for word as a source/, `${code}: states the text was saved as a source`);
      assert.match(s.what, /no items were made/, `${code}: states that no items were made`);
      assert.doesNotMatch(s.what, /nothing was (created|made)/i, `${code}: the untrue "nothing was created" is gone`);
    }
  });

  await t.test('every other branch keeps its facts (advice selection unchanged)', () => {
    const callFail = addErrorSentence({ code: 'CAPTURE-008', name: 'AiCallFail', where: 'x', detail: 'unreachable' });
    assert.equal(callFail.title, 'The AI service could not answer.');
    assert.equal(callFail.openSetup, true);
    assert.equal(callFail.retry, true);
    assert.equal(addErrorSentence(null).openSetup, false);
    // An unknown code falls through to the shared table; its own extra
    // line is untouched.
    assert.match(addErrorSentence({ code: 'CAPTURE-999', name: 'Someday', where: 'x', detail: 'x' }).what, /Nothing of yours was changed\./);
    // The refusal for a not-an-assumption keeps saying items are the
    // problem, not that nothing was made (CAPTURE-016's own entry is the
    // one table's; the branch's extra words stay).
    const forced = addErrorSentence({ code: 'CAPTURE-016', name: 'NotAnAssumption', where: 'x', detail: 'nope' });
    assert.equal(forced.openSetup, false);
    assert.equal(forced.retry, true);
  });
});

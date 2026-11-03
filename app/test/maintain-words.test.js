'use strict';

/**
 * The sweep's plain words and the maintain-document shape check
 * (ticket A37). The document shape pinned here is the contract table's
 * `maintain` row (tests/bridge/test_contract_table.py): top-level keys
 * `command`, `changes`, `summary`, `dry_run`, with the engine's own
 * `stale_candidates` shortlist (`candidates` + `truncated`) inside the
 * summary. Every engine cause value below is one
 * `ember/maintain/derive.py` `_close`/`_challenge` trigger_cause
 * literal, re-check by the contract test against the real engine.
 */

const test = require('node:test');
const assert = require('node:assert/strict');

test('maintain words', async (t) => {
  const {
    maintainDocumentFromMessage,
    causeSentence,
    sweepCountsSentence,
    staleIntroSentence,
    staleCapSentence,
    candidateLine,
    phaseOutcomeSentence,
    resultHeadline,
    sweepAnswerFor,
    applyLabel,
  } = await import('../shared/maintain-words.mjs');

  const document = {
    command: 'maintain',
    changes: [{ item_id: 3, old_status: 'Active', new_status: 'Challenged' }],
    summary: { closed: 0, challenged: 1, reopened: 0, unchanged: 3 },
    dry_run: true,
  };
  const messageText = JSON.stringify(document);

  await t.test('the document check accepts exactly the pinned shape from a message event', () => {
    assert.deepEqual(maintainDocumentFromMessage(messageText), document);
    assert.equal(maintainDocumentFromMessage('item 3: Active -> Challenged'), null, 'plain report lines are not the document');
    assert.equal(maintainDocumentFromMessage('[]'), null);
    assert.equal(maintainDocumentFromMessage(null), null);
    assert.equal(maintainDocumentFromMessage('{"command":"other"}'), null, 'another command is not a maintain document');
  });

  await t.test('the document check refuses every drifted top-level key', () => {
    for (const [key, value] of [
      ['command', 'drifted'],
      ['changes', 'not-a-list'],
      ['summary', 'not-an-object'],
      ['dry_run', 'yes'],
    ]) {
      const drifted = JSON.parse(messageText);
      drifted[key] = value;
      assert.equal(maintainDocumentFromMessage(JSON.stringify(drifted)), null, `${key} drift must be refused`);
    }
  });

  await t.test('the because cell names the rule and the link, never a blank', () => {
    assert.equal(causeSentence({ trigger_cause: 'supersedes_confirmed', link_id: 4 }), 'a confirmed supersedes link (link 4) replaces it');
    assert.equal(causeSentence({ trigger_cause: 'answers_confirmed', link_id: 11 }), 'a confirmed answers link (link 11) answers this question');
    assert.equal(causeSentence({ trigger_cause: 'contradicts_confirmed', link_id: 7 }), 'a confirmed contradicts link (link 7) contradicts it');
    assert.equal(causeSentence({ trigger_cause: 'dependency_closed', link_id: 2 }), 'it depends on a closed item (link 2)');
    assert.equal(causeSentence({ trigger_cause: 'dependency_closed', link_id: null }), 'it depends on a closed item (unrecorded)');
    assert.equal(causeSentence({ trigger_cause: 'not-a-known-cause', link_id: 9 }), 'a confirmed link (link 9)');
    assert.equal(causeSentence({}), 'the confirmed links say so');
    assert.equal(causeSentence(null), 'the confirmed links say so');
  });

  await t.test('the counts sentence reads the engine summary only (D3)', () => {
    assert.equal(
      sweepCountsSentence({ closed: 1, challenged: 2, reopened: 0, unchanged: 5 }, 'would'),
      'The sweep would close 1 item, challenge 2 items, and leave 5 unchanged.',
    );
    assert.equal(
      sweepCountsSentence({ closed: 1, challenged: 2, reopened: 1, unchanged: 3 }, 'did'),
      'The sweep closed 1 item, challenged 2 items, reopened 1 item, and left 3 unchanged.',
    );
    // 4.6 #10: after a finished run the sweep DID run — "Nothing
    // changes" is untrue. The honest line says it found nothing to
    // change and what stayed.
    assert.doesNotMatch(sweepCountsSentence({ closed: 0, challenged: 0, reopened: 0, unchanged: 4 }, 'would'), /Nothing changes/);
    assert.equal(sweepCountsSentence({ closed: 0, challenged: 0, reopened: 0, unchanged: 4 }, 'would'), 'The sweep would find nothing to change: 4 items are already in line.');
    assert.equal(sweepCountsSentence({ closed: 0, challenged: 0, reopened: 0, unchanged: 1 }, 'did'), 'The sweep found nothing to change: 1 item is already in line.');
    assert.match(sweepCountsSentence({ closed: 0, challenged: 0, reopened: 0, unchanged: 7 }, 'did'), /The sweep found nothing to change: 7 items are already in line\./);
    assert.equal(sweepCountsSentence(null), '');
  });

  await t.test('the stale note, the cap note and the candidate lines', () => {
    assert.equal(staleIntroSentence(0), '');
    assert.equal(staleIntroSentence(1), 'After the sweep, Ember may propose closing 1 old question that has an answer. You answer each one.');
    assert.ok(/2 old questions/.test(staleIntroSentence(2)));
    assert.equal(staleCapSentence(true), 'The list is capped at 10 questions in one sweep; the rest wait for the next one.');
    assert.equal(staleCapSentence(false), '');
    assert.equal(candidateLine({ item_id: 7, statement: 'should we cache tokens?' }), 'Item 7 — should we cache tokens?');
    assert.equal(candidateLine({ item_id: 9, statement: null }), 'Item 9 — a question without text');
  });

  await t.test('the final outcome and headline sentences', () => {
    assert.equal(phaseOutcomeSentence({ stale: 0, proposed: 0, accepted: 0, rejected: 0 }), '');
    assert.equal(phaseOutcomeSentence({ stale: 1, proposed: 1, accepted: 1, rejected: 0 }), 'Old questions: 1 proposal made, 1 accepted, 0 declined.');
    assert.equal(phaseOutcomeSentence({ stale: 2, proposed: 2, accepted: 1, rejected: 1 }), 'Old questions: 2 proposals made, 1 accepted, 1 declined.');
    assert.equal(phaseOutcomeSentence({ stale: 2, proposed: 0, accepted: 0, rejected: 0, aborted: true }), 'Old questions: none needed a proposal, 0 accepted, 0 declined.');
    assert.equal(resultHeadline({ closed: 1, challenged: 1, reopened: 0 }), 'Done. 2 items were changed. The ledger shows why.');
    assert.equal(resultHeadline({ closed: 0, challenged: 1, reopened: 0 }), 'Done. 1 item was changed. The ledger shows why.');
    assert.equal(resultHeadline({ closed: 0, challenged: 0, reopened: 0 }), 'Done. Nothing needed to change.');
  });

  await t.test('the answer mapping and the apply label', () => {
    assert.equal(sweepAnswerFor('confirm'), 'y');
    assert.equal(sweepAnswerFor('reject'), 'n');
    assert.equal(sweepAnswerFor('stop'), null, 'stop closes the input; it is not a written answer');
    assert.equal(applyLabel(0), 'Apply (no status changes)');
    assert.equal(applyLabel(1), 'Apply 1 change');
    assert.equal(applyLabel(4), 'Apply 4 changes');
  });

  await t.test('MAINTAIN-003 speaks of the reason not being human-settable (4.6 #9)', async () => {
    // The engine raises CloseReasonMismatch (`ember/maintain/errors.py:24`)
    // in validate_close_item when the reason IS one of the 5 close
    // reasons but is NOT in HUMAN_SETTABLE_REASONS (`human_actions.py:52`:
    // only invalidated / expired may be set by a person) — nothing to do
    // with "the reason this item was closed with".
    const { ERROR_SENTENCES } = await import('../shared/plain-sentences.mjs');
    const entry = ERROR_SENTENCES['MAINTAIN-003'];
    const text = `${entry.title} ${entry.what} ${entry.next}`;
    assert.match(text, /set by hand|human-settable|by a person/);
    for (const reason of ['superseded', 'answered', 'reversed']) assert.match(text, new RegExp(reason, 'i'));
    assert.doesNotMatch(text, /did not match|not the reason this item was closed with/, 'the old untrue "reason did not match" words are gone');
  });
});

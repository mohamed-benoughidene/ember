'use strict';

/**
 * The plain-sentence table (plan §5.6, app step file §4). Scope per the
 * step file's wording: the screens of THIS step can surface the APP-
 * namespace and the QUERY- codes QUERY-001, 003, 004, 006, 007 — those
 * need full entries; everything else falls back to a generic family
 * sentence (never a blank). Two anti-drift walks:
 *
 * - every engine/bridge code THIS TABLE CLAIMS must really exist in
 *   `ember/**\/errors.py` (no invented codes);
 * - every history kind `ember/query/history.py` can classify (the
 *   _KIND_BY_PAIR values plus `unknown`) must have a label — the
 *   story-122 walk (undone/redone/item_edited/link_unreversed
 *   included, the U5-1 handoff).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { REPO_ROOT } = require('./util');

test('plain sentences', async (t) => {
  const { ERROR_SENTENCES, sentenceFor, HISTORY_KINDS, historyKindLabel, historyEventSentence, ERROR_FAMILIES } =
    await import('../shared/plain-sentences.mjs');
  const { NAMES } = require('../shared/errors');

  t.test('every APP- code has a full sentence and the stable name', () => {
    for (let n = 0; n <= 8; n += 1) {
      const code = `APP-00${n}`;
      const entry = ERROR_SENTENCES[code];
      assert.ok(entry, `${code} has no entry`);
      for (const field of ['title', 'what', 'next']) {
        assert.equal(typeof entry[field], 'string');
        assert.ok(entry[field].trim().length > 0, `${code}.${field} is blank`);
      }
      const asSentence = sentenceFor(code);
      assert.equal(asSentence.title, entry.title);
    }
  });

  t.test('the step-04 query codes have full sentences', () => {
    for (const code of ['QUERY-001', 'QUERY-003', 'QUERY-004', 'QUERY-006', 'QUERY-007']) {
      const entry = ERROR_SENTENCES[code];
      assert.ok(entry, `${code} has no entry`);
      for (const field of ['title', 'what', 'next']) {
        assert.ok(entry[field].trim().length > 0, `${code}.${field} is blank`);
      }
    }
  });

  t.test('every engine/bridge code the table claims exists in ember/**/errors.py', () => {
    const real = new Set();
    for (const dir of ['ember', 'ember/capture', 'ember/maintain', 'ember/query', 'ember/relate', 'ember/adapters']) {
      const file = path.join(REPO_ROOT, dir, 'errors.py');
      if (!fs.existsSync(file)) continue;
      for (const match of fs.readFileSync(file, 'utf8').matchAll(/code = "([A-Z]+-\d{3})"/g)) {
        real.add(match[1]);
      }
    }
    assert.ok(real.size > 50, `the walk found only ${real.size} codes; the file set must be wrong`);
    const claimed = Object.keys(ERROR_SENTENCES).filter((code) => !code.startsWith('APP-'));
    for (const code of claimed) {
      assert.ok(real.has(code), `${code} is claimed by the sentence table but no errors.py class defines it`);
    }
    // The app's own namespace is defined in app/shared/errors.js, not Python.
    for (const code of Object.keys(ERROR_SENTENCES).filter((c) => c.startsWith('APP-'))) {
      assert.ok(NAMES[code], `${code} is in the table but not in the APP- namespace`);
    }
  });

  t.test('an unknown code falls back to a generic family sentence, never a blank', () => {
    const unknownInKnownFamily = sentenceFor('QUERY-099');
    assert.match(unknownInKnownFamily.title, /query engine/i);
    assert.ok(unknownInKnownFamily.what.includes('QUERY-099'), 'the code must be visible in the generic sentence');
    for (const field of ['title', 'what', 'next']) assert.ok(unknownInKnownFamily[field].trim() !== '');
    const unknownInKnownFamily2 = sentenceFor('CAPTURE-007');
    assert.match(unknownInKnownFamily2.title, /capture engine/i);
    const unknownFamily = sentenceFor('ZZZZ-001');
    assert.ok(unknownFamily.title.trim() !== '' && unknownFamily.what.trim() !== '' && unknownFamily.next.trim() !== '');
    assert.match(unknownFamily.title, /Ember|problem/i);
    for (const [family, words] of Object.entries(ERROR_FAMILIES)) {
      assert.ok(words.trim() !== '', `family ${family} has no words`);
    }
  });

  t.test('every history kind ember/query/history.py can classify has a label (story 122)', () => {
    const source = fs.readFileSync(path.join(REPO_ROOT, 'ember', 'query', 'history.py'), 'utf8');
    const kinds = new Set();
    const pairBlock = source.match(/_KIND_BY_PAIR[\s\S]*?}/);
    assert.ok(pairBlock, 'the _KIND_BY_PAIR block moved — the walk must be updated');
    for (const match of pairBlock[0].matchAll(/:\s*"([a-z_]+)"/g)) kinds.add(match[1]);
    const unknown = source.match(/UNKNOWN_KIND = "([a-z_]+)"/);
    if (unknown) kinds.add(unknown[1]);
    assert.ok(kinds.size >= 14, `expected at least 14 kinds, the walk found ${[...kinds].join(', ')}`);
    for (const kind of kinds) {
      assert.ok(historyKindLabel(kind).trim() !== '', `kind ${kind} has no label`);
    }
    assert.equal(historyKindLabel('undone'), 'Undone');
    assert.equal(historyKindLabel('redone'), 'Redone');
    assert.equal(historyKindLabel('item_edited'), 'Item edited');
    assert.equal(historyKindLabel('link_unreversed'), 'Reversal undone');
    assert.equal(historyKindLabel('never_heard_of_it'), 'Change without words', 'an unknown kind still gets words');
    for (const kind of Object.keys(HISTORY_KINDS)) {
      assert.ok(historyKindLabel(kind).trim() !== '');
    }
  });

  t.test('the undo-era ledger rows read in plain words (U5-1 handoff)', () => {
    const undone = historyEventSentence({
      kind: 'undone', cause: 'user_undo', field_changed: 'undo_of', item_id: null, link_id: null,
      old_value: null, new_value: '7', close_reason: null,
    });
    assert.match(undone, /undone/i);
    assert.match(undone, /nothing was erased/i);
    const redone = historyEventSentence({ kind: 'redone', cause: 'user_redo', field_changed: 'redo_of' });
    assert.match(redone, /redone/i);
    const edited = historyEventSentence({ kind: 'item_edited', cause: 'user_undo', item_id: 5, field_changed: 'rationale' });
    assert.match(edited.toLowerCase(), /item 5/);
    const unreversed = historyEventSentence({ kind: 'link_unreversed', cause: 'user_undo', item_id: 4, link_id: 2 });
    assert.match(unreversed, /reversal/i);
    const status = historyEventSentence({
      kind: 'status_changed', cause: 'user_closed', item_id: 4, link_id: null,
      old_value: 'Active', new_value: 'Closed:answered', close_reason: 'answered',
    });
    assert.match(status.toLowerCase(), /item 4/);
    assert.match(status, /Closed to Closed:answered|Active to Closed:answered/);
    const confirmedLink = historyEventSentence({
      kind: 'link_confirmed', cause: 'user_confirmed', item_id: 5, link_id: 1,
      link_source_item_id: 5, link_target_item_id: 3, link_type: 'contradicts',
    });
    assert.match(confirmedLink.toLowerCase(), /link 1/);
    assert.match(confirmedLink, /item 5 contradicts item 3/);
    assert.match(confirmedLink, /Done by you\./);
  });
});

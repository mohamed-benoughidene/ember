'use strict';

/**
 * The step-09 additions to the shared plain-sentence table (app step
 * 09; ticket A38): the BACKUP-/EXPORT- entries the Keep safe screen
 * can show (stories 70-77) and the db-check report read-map (story
 * 75). The existing anti-drift walks in plain-sentences.test.js keep
 * guarding the table as a whole.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { REPO_ROOT } = require('./util');

test('every BACKUP-/EXPORT- code the screen shows has full words, named per story', async () => {
  const { ERROR_SENTENCES, sentenceFor } = await import('../shared/plain-sentences.mjs');
  for (const code of ['BACKUP-001', 'BACKUP-002', 'BACKUP-003', 'BACKUP-004', 'EXPORT-001', 'EXPORT-002']) {
    const entry = ERROR_SENTENCES[code];
    assert.ok(entry, `${code} has no entry`);
    for (const field of ['title', 'what', 'next']) {
      assert.ok(entry[field].trim().length > 0, `${code}.${field} is blank`);
    }
    assert.equal(sentenceFor(code), entry, 'sentenceFor must find the full entry, not the family fallback');
  }
  // Story 77: failures say the knowledge base file is unchanged.
  for (const code of ['BACKUP-001', 'BACKUP-002', 'BACKUP-003', 'BACKUP-004', 'EXPORT-001', 'EXPORT-002']) {
    assert.match(ERROR_SENTENCES[code].next, /unchanged/, `${code} must say the file is unchanged`);
  }
  // Story 72: the self-overwrite refusal names the protection.
  assert.match(ERROR_SENTENCES['BACKUP-003'].what, /refuses to write over your knowledge base/);
  // Story 74: the export refusal names why (an export cannot be restored).
  assert.match(ERROR_SENTENCES['EXPORT-002'].what, /cannot be restored/);
});

test('the step-09 codes exist in ember/adapters/errors.py (no invented codes)', () => {
  const source = fs.readFileSync(path.join(REPO_ROOT, 'ember', 'adapters', 'errors.py'), 'utf8');
  const real = new Set([...source.matchAll(/code = "([A-Z]+-\d{3})"/g)].map((m) => m[1]));
  for (const code of ['BACKUP-001', 'BACKUP-002', 'BACKUP-003', 'BACKUP-004', 'EXPORT-001', 'EXPORT-002']) {
    assert.ok(real.has(code), `${code} is claimed but no errors.py class defines it`);
  }
});

test('the db-check verdict words cover OK, DRIFT and UNREADABLE (story 75)', async () => {
  const { dbCheckVerdictWords } = await import('../shared/plain-sentences.mjs');
  const ok = dbCheckVerdictWords('OK');
  assert.equal(ok.kind, 'ok');
  assert.match(ok.title, /No problems found/);
  assert.match(ok.next, /changed nothing|nothing was changed/i);
  const drift = dbCheckVerdictWords('DRIFT');
  assert.equal(drift.kind, 'drift');
  assert.match(drift.next, /Try again/, 'DRIFT offers Retry and what to do next');
  const unreadable = dbCheckVerdictWords('UNREADABLE');
  assert.equal(unreadable.kind, 'unreadable');
  assert.match(unreadable.title, /could not be read/);
  // An unknown verdict still gets words, never a blank.
  const unknown = dbCheckVerdictWords('SOMETHING');
  assert.ok(unknown.title.trim() !== '' && unknown.next.trim() !== '');
});

test('every known db-check report line reads as one plain sentence; unknown lines pass through', async () => {
  const { dbCheckRowSentence } = await import('../shared/plain-sentences.mjs');
  // The REAL line shapes, byte for byte from a healthy v13 run:
  const real = [
    ['version: 13', /File format version 13\./],
    ['floors: relate 12 ok, maintain 11 ok, query 10 ok, capture none', /minimum file format is met/],
    ['floors: unmet - relate needs 12', /older than some parts of Ember need/],
    ['triggers: links_compat_insert, links_compat_update, items_closed_reason_insert, items_closed_reason_update - present', /safety triggers are in place/],
    ['triggers: missing items_closed_reason_update', /safety triggers are missing/],
    ['link_compat: 16 rows, matches TYPE_COMPAT', /matches the rules \(16 rows\)/],
    ['link_compat: 15 rows, drift from TYPE_COMPAT (1 missing, 0 extra)', /does not match/],
    ['foreign_key_check: 0 violations', /No item or link points at a record that is gone/],
    ['foreign_key_check: 2 violations', /2 records point at other records that are gone/],
    ['reversal replay: 1 reversed links, column == ledger', /^Replacement records agree with the ledger \(1 reversed link\)\.$/],
    ['reversal replay: 2 reversed links, column != ledger (mismatched links: 4)', /disagree with the ledger/],
    ['group_id: 0 undo/redo pointers, all name existing groups', /Every undo record points at a real change/],
    ['group_id: not applicable (schema v12)', /does not apply to this older file/],
    ['group_id: undo/redo pointers name missing groups', /point at changes that are gone/],
    ['result: OK', /Verdict: no problems found/],
    ['result: DRIFT', /Verdict: things do not match/],
    ['result: UNREADABLE', /Verdict: the file could not be read/],
  ];
  for (const [line, pattern] of real) {
    assert.match(dbCheckRowSentence(line), pattern, `line "${line}" must read in plain words`);
  }
  // A line the map does not know is shown as written, never blank.
  assert.equal(dbCheckRowSentence('some future line: 42'), 'some future line: 42');
  assert.ok(dbCheckRowSentence('').trim() !== '');
});

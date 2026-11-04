'use strict';

/**
 * The step-07 pure words (T1): the Undo/Redo label derivation
 * (shared/undo-labels.mjs — the screen's buttons now, the Edit menu in
 * step 12). The maintain plain sentences NO LONGER have their own
 * table: since Batch 6 they live in the ONE table
 * (shared/plain-sentences.mjs) and shared/maintain-sentences.mjs is a
 * shim delegating to sentenceFor. The anti-drift walk stays: every
 * code the one table claims (APP- excepted) must exist in
 * `ember/**\/errors.py`, and the undo refusal extras must fire on the
 * real engine detail strings (stories 118, 123).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { REPO_ROOT } = require('./util');

const summary = (over = {}) => ({ direction: 'undo', source_action: 'close-item', target_label: 'item 3', source_group_id: 7, new_group_id: null, ...over });

test('undo labels', async (t) => {
  const { undoRedoLabel, undoActionWords, undoDoneSentence, undoDisabledReason, UNDO_ACTION_WORDS } = await import('../shared/undo-labels.mjs');

  await t.test('the label names the action, from the engine summary (story 113)', () => {
    assert.equal(undoRedoLabel(summary()), 'Undo Close item 3');
    assert.equal(undoRedoLabel(summary({ direction: 'redo' })), 'Redo Close item 3');
    assert.equal(undoRedoLabel(summary({ source_action: 'remove-link', target_label: 'link 7' })), 'Undo Removal of link 7');
    assert.equal(undoRedoLabel(summary({ source_action: 'set-status', target_label: 'item 5' })), 'Undo Status change of item 5');
    assert.equal(undoRedoLabel(summary({ source_action: 'set-validated', target_label: 'item 2' })), 'Undo Set verified mark on item 2');
    assert.equal(undoRedoLabel(summary({ source_action: 'clear-validated', target_label: 'item 2' })), 'Undo Clear verified mark on item 2');
    assert.equal(undoRedoLabel(summary({ source_action: 'edit-item', target_label: 'item 4' })), 'Undo Edit item 4');
    assert.equal(undoRedoLabel(summary({ source_action: 'reverse-supersedes', target_label: 'item 1' })), 'Undo Reversal of item 1');
    for (const action of Object.keys(UNDO_ACTION_WORDS)) {
      assert.ok(undoActionWords(action).trim() !== '', `source_action ${action} has words`);
    }
  });

  await t.test('every engine source_action has a label; unknown ones fail loudly', () => {
    // The engine can return exactly what ember/maintain/undo.py's two
    // readers return; walk the real returns (the same read-the-source
    // way the errors.py walk below works) instead of repeating them.
    const source = fs.readFileSync(path.join(REPO_ROOT, 'ember/maintain/undo.py'), 'utf8');
    const real = new Set();
    for (const name of ['_source_action_of_original', '_source_action_of_undo']) {
      const start = source.indexOf(`def ${name}(`);
      assert.ok(start !== -1, `${name} exists in ember/maintain/undo.py`);
      const end = source.indexOf('\ndef ', start + 1);
      const body = source.slice(start, end === -1 ? source.length : end);
      // Bare returns plus the `set-validated ... else clear-validated`
      // ternaries; the Set dedupes close-item's two return sites.
      for (const match of body.matchAll(/return "([a-z-]+)"(?: if [^\n]*? else "([a-z-]+)")?/g)) {
        real.add(match[1]);
        if (match[2]) real.add(match[2]);
      }
    }
    // Unknown finds must fail loudly (the throw below names them); the
    // size pin after the loop means an empty or rotted walk also fails:
    // the regex cannot rot silently.
    for (const action of real) {
      assert.ok(undoActionWords(action), action);
    }
    assert.equal(real.size, 7, `the walk finds exactly the engine's 7 source_actions; found: ${[...real].sort().join(', ')}`);
    assert.throws(() => undoActionWords('maintain'), /unknown source_action/);
    assert.throws(() => undoRedoLabel({ direction: 'sideways', source_action: 'close-item', target_label: 'item 1' }), /unknown direction/);
    assert.throws(() => undoRedoLabel(null), /missing/);
  });

  await t.test('the confirming sentences (story 62) and the honesty line', () => {
    assert.equal(undoDoneSentence(summary()), 'Undone Close item 3: nothing was erased; the ledger keeps both lines.');
    assert.equal(undoDoneSentence(summary({ direction: 'redo' })), 'Redone Close item 3: done again, the same append-only way.');
    assert.equal(undoDoneSentence(summary(), true), 'Undo Close item 3: nothing has changed yet.');
  });

  await t.test('the honest disabled states (111/112/123) and the enabled refusals', () => {
    assert.equal(undoDisabledReason({ code: 'MAINTAIN-023', detail: 'nothing to undo | ungrouped_rows_exist=False' }), 'Nothing to undo.');
    assert.equal(
      undoDisabledReason({ code: 'MAINTAIN-023', detail: 'nothing to undo: older ledger rows carry no undo group (they were written before the grouping upgrade) and are not undoable | ungrouped_rows_exist=True' }),
      'Nothing to undo. Changes written before Undo existed cannot be undone.',
    );
    assert.equal(undoDisabledReason({ code: 'MAINTAIN-024', detail: 'nothing to redo | has_newer_original=False' }), 'Nothing to redo.');
    assert.equal(
      undoDisabledReason({ code: 'MAINTAIN-024', detail: 'nothing to redo: a newer change cleared it | has_newer_original=True' }),
      'Nothing to redo. A newer change cleared it; undo again to make Redo available.',
    );
    // MAINTAIN-025 stays ENABLED: the refusal belongs to the click,
    // where story 118's words show with Try again.
    assert.equal(undoDisabledReason({ code: 'MAINTAIN-025', detail: 'item changed since | item_id=5 group_id=7' }), null);
    assert.equal(undoDisabledReason(null), null);
    assert.equal(undoDisabledReason({ code: 'APP-008', detail: 'timed out' }), null);
  });
});

test('maintain plain sentences', async (t) => {
  const { maintainSentenceFor, undoNoteFor } = await import('../shared/maintain-sentences.mjs');
  const { ERROR_SENTENCES, sentenceFor } = await import('../shared/plain-sentences.mjs');
  // The ONE table: the MAINTAIN- entries and CAPTURE-016 moved there
  // in Batch 6 chunk 2; the shim only delegates.
  const MAINTAIN_SENTENCES = ERROR_SENTENCES;

  await t.test('the step-07 code range has full entries (step file §4)', () => {
    for (const code of [
      'MAINTAIN-001', 'MAINTAIN-002', 'MAINTAIN-003', 'MAINTAIN-004', 'MAINTAIN-005', 'MAINTAIN-006',
      'MAINTAIN-013', 'MAINTAIN-014', 'MAINTAIN-015', 'MAINTAIN-016', 'MAINTAIN-017',
      'MAINTAIN-023', 'MAINTAIN-024', 'MAINTAIN-025', 'MAINTAIN-026', 'MAINTAIN-027',
      'CAPTURE-016', // story 53's forced-path refusal (validated is Assumption-only)
    ]) {
      const entry = MAINTAIN_SENTENCES[code];
      assert.ok(entry, `${code} has no entry`);
      for (const field of ['title', 'what', 'next']) {
        assert.ok(typeof entry[field] === 'string' && entry[field].trim() !== '', `${code}.${field} is blank`);
      }
    }
  });

  await t.test('every code the table claims exists in ember/**/errors.py (no drift)', () => {
    const real = new Set();
    for (const dir of ['ember', 'ember/capture', 'ember/maintain', 'ember/query', 'ember/relate', 'ember/adapters']) {
      const file = path.join(REPO_ROOT, dir, 'errors.py');
      if (!fs.existsSync(file)) continue;
      // Same lenient regex as the plain-sentences claim walk: the -000
      // base in ember/errors.py is written `code: str = ...`.
      for (const match of fs.readFileSync(file, 'utf8').matchAll(/code(?::\s*str)? = "([A-Z]+-\d{3})"/g)) real.add(match[1]);
    }
    for (const code of Object.keys(MAINTAIN_SENTENCES).filter((c) => !c.startsWith('APP-'))) {
      assert.ok(real.has(code), `${code} is claimed by the maintain sentence table but no errors.py class defines it`);
    }
    // The real engine detail strings the notes must recognise.
    assert.ok(real.has('CAPTURE-016') && real.has('MAINTAIN-025'));
  });

  await t.test('unknown codes fall through to the shared family sentence, never blank', () => {
    // F5 gave every engine code an entry, so the fall-through needs a
    // hypothetical future code (one the engine does not define yet).
    const generic = maintainSentenceFor('MAINTAIN-999');
    assert.equal(generic.title, sentenceFor('MAINTAIN-999').title, 'falls back to the shared table');
    assert.match(generic.title, /maintain engine/i);
    for (const field of ['title', 'what', 'next']) assert.ok(generic[field].trim() !== '');
    const named = maintainSentenceFor('MAINTAIN-025');
    assert.match(named.title, /refused/i);
  });

  await t.test('the story-118/123 notes fire on the REAL engine detail strings', () => {
    assert.equal(undoNoteFor('MAINTAIN-023', 'nothing to undo | ungrouped_rows_exist=False'), null);
    assert.match(
      undoNoteFor('MAINTAIN-023', 'nothing to undo: older ledger rows carry no undo group (they were written before the grouping upgrade) and are not undoable | ungrouped_rows_exist=True'),
      /before Undo existed cannot be undone/,
    );
    assert.equal(undoNoteFor('MAINTAIN-024', 'nothing to redo | has_newer_original=False'), null);
    assert.match(undoNoteFor('MAINTAIN-024', 'nothing to redo: a newer change cleared it | has_newer_original=True'), /Undo again/);
    assert.equal(undoNoteFor('MAINTAIN-025', 'item changed since | item_id=5'), null);
  });
});

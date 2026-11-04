/**
 * The maintain-engine sentence shim (Batch 6 chunk 2: the ONE sentence
 * table). Since Batch 6 moved every MAINTAIN- entry and CAPTURE-016
 * into the single `ERROR_SENTENCES` table in plain-sentences.mjs, this
 * module holds no table of its own any more: `maintainSentenceFor`
 * delegates to `sentenceFor` (the Fix and close screen,
 * `app/renderer/screens/fix-close.mjs`, imports it here). An unknown
 * code gets the generic family sentence — never a blank (story 102).
 *
 * `undoNoteFor` keeps the honest undo-refusal extras the step file
 * pins (they ride on the detail string, not the code):
 * - story 123 (MAINTAIN-023 with pre-grouping rows): the note that
 *   older changes cannot be undone;
 * - story 118 rides on MAINTAIN-025.
 *
 * Pure module (T1): strings in, strings out; no DOM, no I/O.
 */

import { sentenceFor } from './plain-sentences.mjs';

/**
 * The sentence for any code the Fix and close screen can show. Every
 * MAINTAIN- code lives in the one table (plain-sentences.mjs), so this
 * is exactly `sentenceFor` now — kept as a named wrapper because the
 * screen reads it by this name.
 *
 * @param {string} code e.g. "MAINTAIN-025"
 * @returns {{title: string, what: string, next: string}}
 */
export function maintainSentenceFor(code) {
  return sentenceFor(code);
}

/**
 * The honest undo-refusal extras the step file pins:
 * - story 123 (MAINTAIN-023 with pre-grouping rows): the note that
 *   older changes cannot be undone.
 * - story 118 rides on MAINTAIN-025 (its sentence lives in the one
 *   table, read by `maintainSentenceFor` above).
 *
 * @param {string} code
 * @param {string} detail the engine's error detail line
 * @returns {string|null} one extra sentence, or null
 */
export function undoNoteFor(code, detail = '') {
  if (code === 'MAINTAIN-023' && /no undo group|ungrouped_rows_exist=True|older ledger rows/i.test(detail)) {
    return 'Changes written before Undo existed cannot be undone; they carry no undo record.';
  }
  if (code === 'MAINTAIN-024' && /newer change cleared it|has_newer_original=True/i.test(detail)) {
    return 'A newer change cleared the redo. Undo again to make Redo available.';
  }
  return null;
}

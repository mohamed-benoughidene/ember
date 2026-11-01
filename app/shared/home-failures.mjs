/**
 * The Home failure grouping core (Batch 3, F4 — Impl-Batch3.md chunk 3).
 *
 * When a Home load fails, the three engine-fed blocks (attention,
 * counts, ledger) each record one `{ what, error }` (`what` names the
 * block, `error` the plain info shape `{code, name, where, detail}`).
 * Decision B3-1: Home shows ONE notice per error code instead of one
 * card per failed block, so the failures fold into one row per
 * distinct code, in first-seen order.
 *
 * Each row carries the shared table's plain words for that code
 * (`plain-sentences.mjs`: exact entry, else the generic family
 * sentence, never a blank), plus this module's ONE count sentence.
 * Wording ownership (decisions I7 and I10): the count sentence's
 * exact wording lives ONLY here and is pinned ONLY by
 * `test/home-failures.test.js` — the e2e checks the number and the
 * code on screen, never the wording.
 *
 * A shapeless error (null, or one without a usable code) still lands
 * in its own group under the no-code words (story 102: errors say
 * what failed and what to do next, never a blank).
 *
 * Pure module (T1): strings in, objects out; no DOM, no I/O.
 */

import { sentenceFor } from './plain-sentences.mjs';

/**
 * The ONE count sentence (its wording is pinned by the unit test).
 * @param {number} count
 * @returns {string}
 */
function countSentence(count) {
  return count === 1 ? '1 block failed with this error.' : `${count} blocks failed with this error.`;
}

/**
 * Fold failed blocks into one row per distinct error code.
 *
 * @param {Array<{what?: string, error?: {code?: string, name?: string, where?: string, detail?: string}|null}>} failures
 * @returns {Array<{code: string|null, count: number, blocks: string[], words: {title: string, what: string, next: string, countSentence: string}}>}
 *          one entry per distinct code, in first-seen order
 */
export function groupFailuresByCode(failures) {
  const rows = [];
  const byCode = new Map();
  const list = Array.isArray(failures) ? failures : [];
  for (const failure of list) {
    const what = failure && typeof failure.what === 'string' ? failure.what : '';
    const error = failure && typeof failure.error === 'object' && failure.error !== null ? failure.error : null;
    const code = error && typeof error.code === 'string' && error.code !== '' ? error.code : null;
    let row = byCode.get(code);
    if (!row) {
      const words = sentenceFor(code);
      row = { code, count: 0, blocks: [], words: { ...words, countSentence: '' } };
      byCode.set(code, row);
      rows.push(row);
    }
    row.count += 1;
    row.blocks.push(what);
  }
  for (const row of rows) row.words.countSentence = countSentence(row.count);
  return rows;
}

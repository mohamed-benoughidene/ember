/**
 * The maintain-engine plain sentences (app step file §4: this step's
 * screens surface MAINTAIN-001-006, 013-017 and the undo codes 023-027
 * via the §5.6 table; L2 undo plan §5.3 for the 023-027 words).
 *
 * Kept as its own ADDITIVE module (not squeezed into
 * plain-sentences.mjs, which steps 05/06/08 extend in their own
 * worktrees): `maintainSentenceFor` falls back to the shared
 * `sentenceFor` for every code not listed here, so the family sentence
 * (never a blank, story 102) still covers 007-012 and 018-022.
 *
 * Story wording, pinned by the step file:
 * - MAINTAIN-023 (NothingToUndo) carries the honest state plus, on
 *   files whose older rows predate the undo grouping, the story-123
 *   note ("older changes cannot be undone");
 * - MAINTAIN-025 (UndoRefused) is the story-118 refusal ("something
 *   changed since");
 * - MAINTAIN-024 (NothingToRedo) is the honest empty redo.
 *
 * Pure module (T1): strings in, strings out; no DOM, no I/O. A node
 * test walks `ember/maintain/errors.py` and fails when this table
 * claims a code that does not exist (no drift, same rule as the
 * step-04 table's walk).
 */

import { sentenceFor } from './plain-sentences.mjs';

export const MAINTAIN_SENTENCES = {
  'MAINTAIN-001': {
    title: 'There is no item with that number.',
    what: 'The item number is not in this knowledge base.',
    next: 'Pick the item from the list again and try once more.',
  },
  'MAINTAIN-002': {
    title: 'That close reason is not allowed.',
    what: 'Only a person chooses between "It was wrong (invalidated)" and "It ran out (expired)".',
    next: 'Pick the reason again from the list and try once more.',
  },
  'MAINTAIN-003': {
    title: 'The close reason did not match.',
    what: 'The reason given is not the reason this item was closed with.',
    next: 'Check the item in Look up, then try once more.',
  },
  'MAINTAIN-004': {
    title: 'This item is already Closed.',
    what: 'A Closed item keeps its own close reason; it cannot be closed again.',
    next: 'To bring it back, undo its close with the Undo button.',
  },
  'MAINTAIN-005': {
    title: 'This replacement cannot be reversed.',
    what: 'A reversal needs the older item closed as superseded, with a confirmed replacement link that is not already reversed.',
    next: 'Look the item up again in Look up, then try once more.',
  },
  'MAINTAIN-006': {
    title: 'That status change is not allowed.',
    what: 'You can move an item between Active and Challenged; a Closed item cannot change status. It reopens only by undoing its close.',
    next: 'Pick a different item, or undo the close first.',
  },
  'MAINTAIN-013': {
    title: 'That field cannot be edited.',
    what: 'Ember knows the field but never allows it to be edited by hand.',
    next: 'Use the edit buttons on the item; they show what this item allows.',
  },
  'MAINTAIN-014': {
    title: 'This item cannot be edited that way.',
    what: 'The rationale belongs to a Decision and the source to a Finding; other kinds keep theirs as written.',
    next: 'Check the item’s type at the top of the item panel.',
  },
  'MAINTAIN-015': {
    title: 'This link cannot be removed.',
    what: 'Only a confirmed link can be removed (marked Rejected).',
    next: 'Check the link in Look up, then try once more.',
  },
  'MAINTAIN-016': {
    title: 'The edit could not be written.',
    what: 'The knowledge base refused the change while it was being written, and nothing was changed.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'MAINTAIN-017': {
    title: 'The link could not be removed.',
    what: 'The knowledge base refused the change while it was being written, and nothing was changed.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  /* --- the undo codes (L2 undo plan §5.3; stories 111-123) --- */
  'MAINTAIN-023': {
    title: 'Nothing to undo.',
    what: 'Undo has no change waiting: every change so far is already undone, or none of your changes are undoable yet.',
    next: 'The Undo button stays off until you make a change it covers.',
  },
  'MAINTAIN-024': {
    title: 'Nothing to redo.',
    what: 'Redo has no undone change waiting: nothing was undone, or a newer change cleared the redo.',
    next: 'The Redo button stays off until you undo something again.',
  },
  'MAINTAIN-025': {
    title: 'This undo was refused.',
    what: 'At least one item or link this undo would restore has changed since (a sweep, a newer edit). Ember refused so nothing gets mixed up.',
    next: 'Read the item’s current state in Look up, then try again only if the change still looks right.',
  },
  'MAINTAIN-026': {
    title: 'The undo could not be written.',
    what: 'The knowledge base refused the undo while it was being written. It was rolled back, so nothing changed and nothing was half-undone.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'MAINTAIN-027': {
    title: 'A ledger entry cannot be read safely.',
    what: 'The undo history holds an entry Ember does not recognise. Ember refused rather than guess what it meant.',
    next: 'Run the health check (Keep safe) and send the Details line with a bug report.',
  },
  /* Forced-path companion of story 53 ("verified" is Assumption-only):
     the screen keeps the button off, so this only shows if the rule is
     somehow reached anyway. */
  'CAPTURE-016': {
    title: 'Only an Assumption can carry the verified mark.',
    what: 'The verified mark records your own checking of an assumption; findings, decisions and questions do not take it.',
    next: 'Pick the item again from the list.',
  },
};

/**
 * The sentence for any code the Fix and close screen can show. Exact
 * MAINTAIN entry first; otherwise the shared table (its generic
 * MAINTAIN family sentence, never a blank; story 102).
 *
 * @param {string} code e.g. "MAINTAIN-025"
 * @returns {{title: string, what: string, next: string}}
 */
export function maintainSentenceFor(code) {
  if (typeof code === 'string' && MAINTAIN_SENTENCES[code]) return MAINTAIN_SENTENCES[code];
  return sentenceFor(code);
}

/**
 * The honest undo-refusal extras the step file pins:
 * - story 123 (MAINTAIN-023 with pre-grouping rows): the note that
 *   older changes cannot be undone.
 * - story 118 rides on MAINTAIN-025 (the sentence above).
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

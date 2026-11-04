/**
 * The plain words for the errors the Link items screen can show
 * (app step 06). The plain-sentence table (plain-sentences.mjs) stays
 * the ONE code -> words mapping; its App 06 block carries the RELATE-
 * entries this screen can surface. Two codes need a refinement the
 * table alone cannot carry, because the blocks pick the ADVICE (the
 * setup path, the install hint):
 *
 * - `RELATE-038` (ApiKeyMissing, Batch 6 D-08/I17): no key was given
 *   at the first relate (story 48's refusal twin of Add's CAPTURE-022
 *   path) — the app says so and opens the AI-connection setup.
 * - `RELATE-039` (EmbedderPackageMissing, Batch 6 D-08/I17): the
 *   optional `sentence-transformers` package is missing (the step
 *   file's "missing optional package ... with what to do") — the app
 *   says plainly what to install, with no retry.
 *
 * Every branch is decided by the CODE alone: no detail text from the
 * engine is ever matched (D-08 — the app no longer reads Python's
 * words like "ai api key missing"). RELATE-017 (a failed model load)
 * and RELATE-040 (a load that timed out) ride their own table entries
 * through the shared fallback, which retries rather than installs.
 *
 * Every branch keeps the two true facts of a link-run failure: nothing
 * was linked beyond the links already shown, and the knowledge base is
 * unchanged by a failed run (the engine writes only after confirms, in
 * one transaction per link). Pure module (T1).
 */

import { sentenceFor } from './plain-sentences.mjs';

const NOTHING_CHANGED = 'No link was added or changed. Your knowledge base file is untouched.';
const INSTALL_HINT = 'The relate extra is one install command: python -m pip install -e ".[relate]". Whoever set Ember up for you can run it.';

const REJECTION_RE = /^relate rejected: ([A-Z]+-\d{3})(?:\s*\|\s*(.*))?$/;

/**
 * One log line -> the words shown inline (the step file: gatekeeper
 * rejections "are shown in plain words"). `relate rejected: CODE |
 * detail` becomes that code's plain sentence plus the engine's detail;
 * every other line is shown as written. Never a blank.
 *
 * @param {string} line a validated session message's text
 * @returns {string}
 */
export function relateRejectionLine(line) {
  if (typeof line !== 'string') return '';
  const m = REJECTION_RE.exec(line.trim());
  if (!m) return line;
  const sentence = sentenceFor(m[1]);
  const detail = typeof m[2] === 'string' && m[2].trim() !== '' ? ` (${m[2].trim()})` : '';
  return `Ember's rules rejected this proposal. ${sentence.what}${detail}`;
}

/**
 * @param {{code?: string, name?: string, where?: string, detail?: string}|null} error
 * @returns {{title: string, what: string, next: string, openSetup: boolean, retry: boolean}}
 */
export function relateErrorSentence(error) {
  if (error && error.code === 'RELATE-038') {
    return {
      title: 'Ember needs the AI connection.',
      what: `Linking asks the AI service for proposals, and no working key was given. ${NOTHING_CHANGED}`,
      next: 'Check the AI connection, then try again.',
      openSetup: true,
      retry: true,
    };
  }
  if (error && error.code === 'RELATE-039') {
    return {
      title: 'The linking brain is not installed on this computer.',
      what: `Linking needs an optional language package that is missing here. ${NOTHING_CHANGED}`,
      next: INSTALL_HINT,
      openSetup: false,
      retry: false,
    };
  }
  const base = sentenceFor(error && error.code ? error.code : null);
  return {
    title: base.title,
    what: `${base.what} ${NOTHING_CHANGED}`,
    next: base.next,
    openSetup: false,
    retry: true,
  };
}

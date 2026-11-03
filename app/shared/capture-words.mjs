/**
 * The plain words for the errors the Add screen can show (app step 05,
 * stories 27-29 and the decision 5-A refusal at the first Add).
 *
 * The plain-sentence table (plain-sentences.mjs) stays the ONE code ->
 * words mapping. Two codes need a refinement the table alone cannot
 * carry (the blocks below pick the ADVICE, not the words): `CAPTURE-008`
 * (AiCallFail) fires when the service cannot be reached or refuses the
 * key (story 27), and `CAPTURE-022` (ApiKeyMissing, Batch 6 D-08/I17)
 * is the engine's own dedicated code for "no key was given" — the
 * setup problem with its own advice block. The two codes are decided
 * by their CODE alone: no detail text from the engine is ever matched
 * (D-08 — the app no longer reads Python's words like
 * "ai api key missing"; the engine, through the code, decides which
 * block shows).
 *
 * Every branch keeps the two true facts of an Add failure: the text is
 * kept word for word as a source, and no items were made (the source
 * is stored before the AI call — `ember/cli.py`: `stored = _store(...)`
 * runs before `_propose`; items are written only after confirms).
 * Pure module (T1).
 */

import { sentenceFor } from './plain-sentences.mjs';

const TEXT_KEPT = 'Your text is kept word for word as a source; no items were made from it.';

/**
 * @param {{code?: string, name?: string, where?: string, detail?: string}|null} error
 * @returns {{title: string, what: string, next: string, openSetup: boolean, retry: boolean}}
 */
export function addErrorSentence(error) {
  if (error && error.code === 'CAPTURE-022') {
    return {
      title: 'Ember needs the AI connection.',
      what: `The AI service could not be used because no working key was given. ${TEXT_KEPT}`,
      next: 'Check the AI connection, then try again.',
      openSetup: true,
      retry: true,
    };
  }
  if (error && error.code === 'CAPTURE-008') {
    return {
      title: 'The AI service could not answer.',
      what: `The request failed: the service was not reachable, or it refused the key. ${TEXT_KEPT}`,
      next: 'Check the AI connection, then try again.',
      openSetup: true,
      retry: true,
    };
  }
  const base = sentenceFor(error && error.code ? error.code : null);
  return {
    title: base.title,
    what: `${base.what} Nothing of yours was changed.`,
    next: base.next,
    openSetup: false,
    retry: true,
  };
}

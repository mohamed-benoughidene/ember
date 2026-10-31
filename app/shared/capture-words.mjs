/**
 * The plain words for the errors the Add screen can show (app step 05,
 * stories 27-29 and the decision 5-A refusal at the first Add).
 *
 * The plain-sentence table (plain-sentences.mjs) stays the ONE code ->
 * words mapping. One engine code needs a refinement the table alone
 * cannot carry: `CAPTURE-008` (AiCallFail) fires BOTH when the service
 * cannot be reached (story 27) AND when no key was given or the key was
 * refused (decision 5-A / stories 5, 8, 29). The engine's own detail
 * line ("ai api key missing" is the exact message `ember/adapters/llm.py`
 * raises for the missing-key case) picks the branch — the engine, not
 * the app, still decides which message shows.
 *
 * Every branch keeps the two true facts of an Add failure: the text is
 * kept word for word as a source, and nothing was created (the source
 * is stored before the AI call; items are written only after confirms).
 * Pure module (T1).
 */

import { sentenceFor } from './plain-sentences.mjs';

const TEXT_KEPT = 'Your text is kept word for word as a source; nothing was created.';

/**
 * @param {{code?: string, name?: string, where?: string, detail?: string}|null} error
 * @returns {{title: string, what: string, next: string, openSetup: boolean, retry: boolean}}
 */
export function addErrorSentence(error) {
  const detail = error && typeof error.detail === 'string' ? error.detail : '';
  if (error && error.code === 'CAPTURE-008') {
    if (detail.includes('ai api key missing')) {
      return {
        title: 'Ember needs the AI connection.',
        what: `The AI service could not be used because no working key was given. ${TEXT_KEPT}`,
        next: 'Check the AI connection, then try again.',
        openSetup: true,
        retry: true,
      };
    }
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

/**
 * Screen helpers for the five-UI-state rule (plan §5.2: errors show
 * inside the block that failed, with what failed and a Retry; no bare
 * code on screen — "Details" reveals it).
 *
 * Consumes the step-03 state-block components; the plain-sentence
 * shared table turns an error info into visible words, and the raw
 * `${code} ${name} | ${detail}` line is one click away. Pure render
 * helpers plus one tiny binding function.
 */

import { sentenceFor } from '../../shared/plain-sentences.mjs';
import { esc } from '../design/escape-html.mjs';
import { errorHtml, stateBlockHtml, bindStateBlock } from '../components/state-block.mjs';

/**
 * Error state inside one failed block. `error` is the plain info shape
 * {code, name, where, detail}; `what` names the block ("the counts"),
 * `onRetry` re-runs that block's load.
 */
export function showErrorBlock(container, error, { what, onRetry }) {
  const sentence = sentenceFor(error && error.code ? error.code : null);
  container.innerHTML = `${errorHtml({
    title: sentence.title,
    detail: sentence.what,
    why: `${sentence.next} Nothing of yours was changed.`,
    onRetry: 'block-retry',
  })}<p class="help" data-testid="error-code" hidden>${esc(`${error ? `${error.code} ${error.name} | ${error.detail}` : 'no details'}`)}</p>`;
  bindStateBlock(container, {
    'block-retry': () => onRetry(),
    'show-details': () => {
      const code = container.querySelector('[data-testid="error-code"]');
      if (code) code.hidden = !code.hidden;
    },
  });
}

/** Loading state for one block (grey bars at real size, one sentence). */
export function showLoadingBlock(container, hint) {
  container.innerHTML = stateBlockHtml('loading', { hint });
}

/**
 * One data block from an {ok, data} | {ok:false, error} result:
 * returns the data, or shows the error block and returns null.
 */
export function dataOrNull(container, result, { what, onRetry }) {
  if (result && result.ok) return result.data;
  showErrorBlock(container, result ? result.error : null, { what, onRetry });
  return null;
}

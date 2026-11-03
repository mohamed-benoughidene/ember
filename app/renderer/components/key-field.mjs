/**
 * Key field (Batch 6, D-14/F7d): the ONE masked key box used by the
 * first-run setup and the Settings AI pane. One password input with the
 * eye toggle INSIDE the field (an icon button over the input's right
 * edge) — there is no separate Show/Hide button beside it. The toggle's
 * accessible names are "Show key" / "Hide key"; the eye icon itself is
 * decorative (aria-hidden), the names carry it.
 *
 * Props in, HTML out (same contract as button.mjs); the caller re-renders
 * on the toggle action. Styling comes from tokens.css only, as inline
 * var() references — no literal sizes of any step of the type scale.
 */

import { esc } from '../design/escape-html.mjs';

export const EYE_SHOW_LABEL = 'Show key';
export const EYE_HIDE_LABEL = 'Hide key';

/** Feather-style open eye (shown while the text is masked). */
const EYE_OPEN = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>`;

/** Feather-style crossed-out eye (shown while the text is visible). */
const EYE_CLOSED = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;

/**
 * One masked key box with its eye toggle. `showKey` flips both the
 * input type (password/text) and the toggle's accessible name. The
 * input keeps the caller's `id` (for a visible <label for>) and
 * `aria-describedby` hook; the eye is inside the wrapper, so it reads
 * as part of the field.
 */
export function keyFieldHtml({ id, testid, toggleAction, value = '', showKey = false, ariaLabel = 'Your AI key', describedBy = null } = {}) {
  if (typeof id !== 'string' || id.trim() === '') throw new Error('a key field needs an input id');
  if (typeof testid !== 'string' || testid.trim() === '') throw new Error('a key field needs a data-testid');
  if (typeof toggleAction !== 'string' || toggleAction.trim() === '') {
    throw new Error('a key field needs the eye toggle action name');
  }
  const eye = showKey ? EYE_CLOSED : EYE_OPEN;
  const eyeLabel = showKey ? EYE_HIDE_LABEL : EYE_SHOW_LABEL;
  return `<div class="key-field" style="position:relative">
    <input type="${showKey ? 'text' : 'password'}" id="${esc(id)}" data-testid="${esc(testid)}" class="key-field__input" autocomplete="off" aria-label="${esc(ariaLabel)}"${describedBy ? ` aria-describedby="${esc(describedBy)}"` : ''} value="${esc(value)}" style="padding-right:var(--s7)">
    <button type="button" class="key-field__eye" data-action="${esc(toggleAction)}" aria-label="${esc(eyeLabel)}" style="position:absolute;top:50%;right:var(--s2);transform:translateY(-50%);display:inline-flex;align-items:center;justify-content:center;min-height:2.4rem;padding:0 var(--s2);border:0;background:none;color:var(--ink-2);cursor:pointer" title="${esc(eyeLabel)}">${eye}</button>
  </div>`;
}

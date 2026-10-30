/**
 * StateBlock (L3 app step 03): the five UI states every screen step
 * (04+) consumes, so all screens show them the same way
 * (docs/DESIGN.md "Empty, loading, error" and the approved prototype).
 *
 * The five states:
 *   normal  — the regular screen frame (no block; screens render content;
 *             `normalFrameHtml` gives them the title-row shape);
 *   loading — grey bars at real size, one plain sentence;
 *   empty   — keeps its frame, one sentence;
 *   error   — inside the failed block, a Retry button AND a Details one;
 *   no-key  — the screen needs the AI connection; points at Settings.
 *
 * Props in, HTML out (pure, no framework); events are wired by
 * `bindStateBlock` from `data-action` hooks. Pure functions are unit
 * tested in node without a DOM.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from './button.mjs';

export const STATE_KINDS = ['loading', 'empty', 'error', 'noKey'];

const SKELETON_BARS = [
  { width: '40%', height: 16 },
  { width: '85%', height: 22 },
  { width: '70%', height: 14 },
  { width: '7rem', height: 38 },
  { width: '7rem', height: 38 },
];

/** Loading: grey bars at real size. */
export function loadingHtml({ hint = 'Reading. Nothing is saved yet.' } = {}) {
  const bars = SKELETON_BARS.map(
    (b) => `<span class="skel" style="width:${b.width};height:${b.height}px;margin:var(--s2) 0" aria-hidden="true"></span>`,
  ).join('');
  return `<div class="state state--loading" data-testid="state-loading" role="status"><div class="panel"><div class="pad">${bars}</div></div><p class="hint">${esc(hint)}</p></div>`;
}

/** Empty: keeps its frame, one sentence, one way forward. */
export function emptyHtml({ title = 'Nothing here yet.', next = null, onNext = null } = {}) {
  const action = next && onNext ? `<div class="actions" style="justify-content:center">${buttonHtml({ label: next, action: onNext, variant: 'secondary' })}</div>` : '';
  return `<div class="state state--empty" data-testid="state-empty"><div class="empty">${esc(title)}${action}</div></div>`;
}

/** Error: in the failed block, with Retry and Details. */
export function errorHtml({ title = 'Something did not work.', detail = '', why = '', onRetry = 'retry', onDetails = 'show-details' } = {}) {
  return `<div class="state state--error" data-testid="state-error" role="alert"><div class="errbox"><strong>${esc(title)}</strong><span class="detail">${esc(detail)}</span>${
    why ? `<span class="hint">${esc(why)}</span>` : ''
  }<div class="actions">${buttonHtml({ label: 'Try again', action: onRetry, variant: 'secondary' })}${buttonHtml({ label: 'Details', action: onDetails, variant: 'text' })}</div></div></div>`;
}

/** No-key: this job needs the AI connection; everything else works. */
export function noKeyHtml({ what = 'This screen', onOpenSettings = 'open-settings' } = {}) {
  return `<div class="state state--no-key" data-testid="state-no-key"><div class="errbox"><strong>${esc(what)} needs the AI connection.</strong><span class="detail">Ember has no AI key yet. Everything else works without one.</span><div class="actions">${buttonHtml({ label: 'Set up the AI connection', action: onOpenSettings, variant: 'primary' })}</div></div></div>`;
}

/**
 * One entry point: kind 'loading' | 'empty' | 'error' | 'noKey' with the
 * kind's props. Unknown kinds throw (typed shapes, never blank).
 */
export function stateBlockHtml(kind, props = {}) {
  switch (kind) {
    case 'loading': return loadingHtml(props);
    case 'empty': return emptyHtml(props);
    case 'error': return errorHtml(props);
    case 'noKey': return noKeyHtml(props);
    default: throw new Error(`unknown state kind: ${String(kind)}`);
  }
}

/**
 * Wire one rendered block's buttons to handlers, by data-action.
 * Example: bindStateBlock(root, { retry: fn, 'show-details': fn }).
 */
export function bindStateBlock(root, handlers) {
  root.querySelectorAll('[data-action]').forEach((el) => {
    const fn = handlers[el.dataset.action];
    if (typeof fn === 'function') el.addEventListener('click', fn);
  });
}

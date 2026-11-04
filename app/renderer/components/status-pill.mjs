/**
 * StatusPill (L3 app step 03, DESIGN.md "Components"): the heat mark
 * plus its word. "Heat mark: 12px. Full dot Active, half dot Challenged,
 * ring Closed. Always followed by the word." Status never depends on
 * colour alone — the shape differs and the word is real text.
 */

import { esc } from '../design/escape-html.mjs';
import { HEAT_STATUSES, heatMarkHtml, settleClass } from './heat-mark.mjs';

export { HEAT_STATUSES };

/** The pill: mark + word. `settle` rides through to the mark. */
export function statusPillHtml(status, { settle = '' } = {}) {
  if (!HEAT_STATUSES.includes(status)) throw new Error(`unknown heat status: ${String(status)}`);
  return `<span class="st st--${status.toLowerCase()}" data-testid="status-pill-${status.toLowerCase()}">${heatMarkHtml(status, { settle })}<span class="st__word">${esc(status)}</span></span>`;
}

/**
 * DOM form for live screens: renders the pill; a later call with a new
 * status re-renders mark + word and runs the ONE settle motion on the
 * mark. The settle class is removed on animationend so a later change
 * can re-run the same animation. Nothing animates on first render.
 */
export function renderStatusPill(el, status, { fromStatus = null, animate = true } = {}) {
  const settle = animate ? settleClass(fromStatus, status) : '';
  el.innerHTML = statusPillHtml(status, { settle });
  const svg = el.querySelector('svg');
  if (svg && settle) {
    svg.addEventListener('animationend', () => svg.classList.remove(settle), { once: true });
  }
  return el;
}

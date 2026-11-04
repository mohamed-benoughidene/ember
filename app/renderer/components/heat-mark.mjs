/**
 * HeatMark (L3 app step 03, DESIGN.md "Components" + "Motion").
 *
 * The signature move: every item shows how hot it is. A full dot is
 * Active, a half dot is Challenged (needs a second look), an empty ring
 * is Closed (ash). The shapes differ so status never depends on colour
 * alone, and the word always follows (see status-pill.mjs).
 *
 * ONE motion: a heat mark settles when its status CHANGES — Active
 * lights up (~260 ms), Challenged turns (~240 ms), Closed cools
 * (~240 ms). Nothing animates on load or revisit: a first render
 * (from === null) and same-to-same never get a settle class. Transform
 * and opacity only; Reduce Motion turns the animation off in CSS
 * (components.css).
 */

import { esc } from '../design/escape-html.mjs';

export const HEAT_STATUSES = ['Active', 'Challenged', 'Closed'];

function shapeFor(status) {
  if (status === 'Active') {
    return '<circle cx="6" cy="6" r="5" fill="var(--heat)"/>';
  }
  if (status === 'Challenged') {
    return '<circle cx="6" cy="6" r="4.2" fill="none" stroke="var(--heat)" stroke-width="1.6"/><path d="M6 1.8a4.2 4.2 0 0 0 0 8.4z" fill="var(--heat)"/>';
  }
  if (status === 'Closed') {
    return '<circle cx="6" cy="6" r="4.2" fill="none" stroke="var(--ink-2)" stroke-width="1.4"/>';
  }
  throw new Error(`unknown heat status: ${String(status)}`);
}

/**
 * The mark itself: 12px SVG, role="img" with an accessible name, one
 * shape per status (full dot / half dot / ring), as in the prototype.
 * `settle` is a CSS animation class (from settleClass) or ''.
 */
export function heatMarkHtml(status, { settle = '' } = {}) {
  const classes = ['heat', settle].filter(Boolean).join(' ');
  return `<svg class="${classes}" viewBox="0 0 12 12" width="12" height="12" role="img" aria-label="${esc(status)}">${shapeFor(status)}</svg>`;
}

/**
 * The settle class for a status CHANGE, or '' for a first render and
 * for same-to-same (nothing animates on load or revisit).
 */
export function settleClass(fromStatus, toStatus) {
  if (fromStatus == null || fromStatus === toStatus) return '';
  if (!HEAT_STATUSES.includes(toStatus)) throw new Error(`unknown heat status: ${String(toStatus)}`);
  if (toStatus === 'Active') return 'heat--settle-heat';
  if (toStatus === 'Challenged') return 'heat--settle-half';
  return 'heat--settle-cool';
}

/**
 * The one DOM helper of the design layer: put a heat mark into `el`,
 * animating only a real change (animate=false for lists mounted whole —
 * the change is not visible mark by mark, DESIGN.md Motion rules).
 * The settle class is removed on animationend so a later change can
 * re-run the same animation.
 */
export function renderHeatMark(el, status, { fromStatus = null, animate = true } = {}) {
  const settle = animate ? settleClass(fromStatus, status) : '';
  el.innerHTML = heatMarkHtml(status, { settle });
  const svg = el.querySelector('svg');
  if (svg && settle) {
    svg.addEventListener('animationend', () => svg.classList.remove(settle), { once: true });
  }
  return svg;
}

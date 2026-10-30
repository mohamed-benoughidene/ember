/**
 * Button (L3 app step 03, DESIGN.md "Components"). Four variants:
 * primary (the ONE main button per screen), secondary, text, danger.
 * Danger follows a preview with an inline confirmation that names the
 * object. Disabled controls stay readable and say why.
 * Props in, HTML out; the caller wires events via data-action.
 */

import { esc } from '../design/escape-html.mjs';

export const BUTTON_VARIANTS = ['primary', 'secondary', 'text', 'danger'];

export function buttonHtml({ label, variant = 'secondary', action = null, kbd = null, title = null, disabled = null, testid = null } = {}) {
  if (!BUTTON_VARIANTS.includes(variant)) throw new Error(`unknown button variant: ${String(variant)}`);
  if (typeof label !== 'string' || label.trim() === '') throw new Error('a button needs a visible label');
  const cls = variant === 'secondary' ? 'btn' : `btn btn--${variant}`;
  const attrs = [
    `class="${cls}"`,
    action ? `data-action="${esc(action)}"` : '',
    testid ? `data-testid="${esc(testid)}"` : '',
    title ? `title="${esc(title)}"` : '',
    disabled !== null ? `disabled` : '',
  ].filter(Boolean).join(' ');
  const kbdSpan = kbd ? `<span class="kbd">${esc(kbd)}</span>` : '';
  return `<button type="button" ${attrs}>${esc(label)}${kbdSpan}</button>`;
}

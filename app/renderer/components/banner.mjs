/**
 * Banner (L3 app step 03, DESIGN.md components): a quiet notice bar
 * across the top of a screen — boot notices, APP-004 style repairs,
 * the sweep education line. Props in, HTML out; optional one action.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from './button.mjs';

export function bannerHtml({ text, actionLabel = null, action = null } = {}) {
  if (typeof text !== 'string' || text.trim() === '') throw new Error('a banner needs text');
  const btn = actionLabel && action ? buttonHtml({ label: actionLabel, action, variant: 'text' }) : '';
  return `<div class="banner" data-testid="banner" role="note">${esc(text)}${btn}</div>`;
}

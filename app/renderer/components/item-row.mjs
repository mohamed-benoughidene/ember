/**
 * ItemRow (L3 app step 03, DESIGN.md "Table"): one row of the ledger —
 * mono number, plain sentence, status as a heat mark with its word.
 * 1px rules, no zebra (styles in components.css .ember-table).
 * Props in, HTML out.
 */

import { esc } from '../design/escape-html.mjs';
import { statusPillHtml } from './status-pill.mjs';

export function itemRowHtml({ id, text, status } = {}) {
  return `<tr data-testid="item-row-${esc(id)}"><td class="num dim">${esc(id)}</td><td>${esc(text)}</td><td>${statusPillHtml(status)}</td></tr>`;
}

/** The full table (many rows): header + rows, no zebra. */
export function itemTableHtml(items) {
  const rows = items.map((it) => itemRowHtml(it)).join('');
  return `<table class="ember-table" data-testid="item-table"><thead><tr><th class="num">No.</th><th>Item</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}

/**
 * ProvenanceLine (L3 app step 03, DESIGN.md "Provenance list"): where an
 * item came from and what challenged or replaced it, in plain lines —
 * label column and value column: Source, Why, Challenged by, Replaced by,
 * Answered by. Props in, HTML out.
 */

import { esc } from '../design/escape-html.mjs';

export const PROVENANCE_LABELS = ['Source', 'Why', 'Challenged by', 'Replaced by', 'Answered by'];

export function provenanceLineHtml(label, value) {
  return `<li><span class="k">${esc(label)}</span><span class="v">${esc(value)}</span></li>`;
}

/** The whole list; `entries` is [label, value] pairs in display order. */
export function provenanceListHtml(entries) {
  if (!Array.isArray(entries)) throw new Error('provenance entries must be [label, value] pairs');
  return `<ul class="lineage" data-testid="provenance">${entries.map(([label, value]) => provenanceLineHtml(label, value)).join('')}</ul>`;
}

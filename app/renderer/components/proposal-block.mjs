/**
 * ProposalBlock (L3 app step 03, DESIGN.md): what Add proposes — type,
 * statement, quote from the source, a check message if the gatekeeper
 * warns. Buttons run left to right: Stop (Esc), Edit (e), Reject (n),
 * Confirm (Return). The main choice is on the trailing side.
 * Props in, HTML out; the Add screen (step 05) wires the events.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from './button.mjs';

export const PROPOSAL_TYPES = ['Decision', 'Assumption', 'Finding', 'Question'];

export function proposalBlockHtml({ type, statement, quote, warn = null, linkKind = false } = {}) {
  if (linkKind) throw new Error('link proposals use the link screen flow (step 06), not ProposalBlock');
  if (!PROPOSAL_TYPES.includes(type)) throw new Error(`unknown proposal type: ${String(type)}`);
  const warnHtml = warn
    ? `<p class="hint" data-testid="proposal-warn">${esc(warn)}</p>`
    : '';
  const quoteHtml = quote ? `<blockquote class="quote">${esc(quote)}</blockquote>` : '';
  const buttons = [
    buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text' }),
    buttonHtml({ label: 'Edit', kbd: 'e', action: 'proposal-edit', variant: 'secondary' }),
    buttonHtml({ label: 'Reject', kbd: 'n', action: 'proposal-reject', variant: 'secondary' }),
    buttonHtml({ label: 'Confirm', kbd: 'Return', action: 'proposal-confirm', variant: 'primary' }),
  ].join('');
  return `<div class="panel" data-testid="proposal" data-proposal-type="${esc(type)}"><div class="pad"><p class="lbl">${esc(type)}</p><p class="statement"><strong>${esc(statement)}</strong></p>${quoteHtml}${warnHtml}<div class="actions">${buttons}</div></div></div>`;
}

/**
 * Plain words and the document check for the Clean up (sweep) screen
 * (L3 app step 08, ticket A37; app/renderer/screens/cleanup.mjs reads
 * these).
 *
 * Everything here is ONE rule stated once (D3): the numbers come from
 * the `maintain` document the engine printed — never recomputed in the
 * app. The document shape (top-level keys `command`, `changes`,
 * `summary`, `dry_run`; `summary.stale_candidates` = the engine's own
 * shortlist model with `candidates` + `truncated`) is pinned by
 * `tests/bridge/test_contract_table.py`; `maintainDocumentFromMessage`
 * re-checks exactly that shape at the app edge (D4), because a child
 * line is untrusted until validated.
 *
 * Pure module (T1): strings in, strings out; no DOM, no I/O.
 */

/** The command name the document must carry. */
export const MAINTAIN_COMMAND = 'maintain';

/**
 * The engine cap for the stale-question shortlist (a fact of the
 * command, stated once so the words cannot drift from it).
 */
export const STALE_CAP = 10;

/**
 * Check one `message` event's text against the pinned maintain
 * document shape. Returns the parsed document, or null when the text
 * is any other line (short information lines ride the same event
 * kind) or when the shape drifted (the caller then raises APP-002 —
 * never a blank screen).
 *
 * @param {string} text one message event's raw text
 * @returns {object|null}
 */
export function maintainDocumentFromMessage(text) {
  if (typeof text !== 'string') return null;
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null;
  if (parsed.command !== MAINTAIN_COMMAND) return null;
  if (!Array.isArray(parsed.changes)) return null;
  if (typeof parsed.summary !== 'object' || parsed.summary === null || Array.isArray(parsed.summary)) return null;
  if (typeof parsed.dry_run !== 'boolean') return null;
  return parsed;
}

/**
 * The "Because" cell for one preview row (story 64: the rule/cause per
 * row). `change` is one engine StatusChange: `trigger_cause` and
 * `link_id` say why. Unknown causes still get words — never a blank.
 */
export function causeSentence(change) {
  const cause = typeof change?.trigger_cause === 'string' ? change.trigger_cause : '';
  const link = change && change.link_id !== null && change.link_id !== undefined ? `link ${change.link_id}` : null;
  switch (cause) {
    case 'supersedes_confirmed':
      return `a confirmed supersedes link (${link ?? 'unrecorded'}) replaces it`;
    case 'answers_confirmed':
      return `a confirmed answers link (${link ?? 'unrecorded'}) answers this question`;
    case 'contradicts_confirmed':
      return `a confirmed contradicts link (${link ?? 'unrecorded'}) contradicts it`;
    case 'dependency_closed':
      return `it depends on a closed item (${link ?? 'unrecorded'})`;
    default:
      return link ? `a confirmed link (${link})` : 'the confirmed links say so';
  }
}

/**
 * The counts sentence under the preview table / in the result (the
 * engine's own summary numbers: closed, challenged, reopened,
 * unchanged). `tense` 'would' for the preview, 'did' for the applied
 * result.
 */
export function sweepCountsSentence(summary, tense = 'would') {
  if (typeof summary !== 'object' || summary === null) return '';
  const parts = [];
  const n = (v) => (typeof v === 'number' ? v : 0);
  const thing = (count, verb, noun) => `${count} ${count === 1 ? noun : `${noun}s`}`;
  if (n(summary.closed) > 0) parts.push(`${tense === 'did' ? 'closed' : 'would close'} ${thing(n(summary.closed), 'close', 'item')}`);
  if (n(summary.challenged) > 0) parts.push(`${tense === 'did' ? 'challenged' : 'challenge'} ${thing(n(summary.challenged), 'challenge', 'item')}`);
  if (n(summary.reopened) > 0) parts.push(`${tense === 'did' ? 'reopened' : 'reopen'} ${thing(n(summary.reopened), 'reopen', 'item')}`);
  const unchanged = `${tense === 'did' ? 'left' : 'leave'} ${n(summary.unchanged)} unchanged`;
  if (parts.length === 0) return `Nothing changes. ${n(summary.unchanged)} item${n(summary.unchanged) === 1 ? ' is' : 's are'} already in line.`;
  return `The sweep ${parts.join(', ')}, and ${unchanged}.`;;
}

/**
 * The lead-in for the stale-question note (my task: the "stale: N"
 * summary in plain words). Empty string when there is nothing to ask.
 */
export function staleIntroSentence(stale) {
  const n = typeof stale === 'number' ? stale : 0;
  if (n <= 0) return '';
  return `After the sweep, Ember may propose closing ${n === 1 ? '1 old question that has an answer' : `${n} old questions that have answers`}. You answer each one.`;
}

/** The cap note, shown only when the engine actually truncated. */
export function staleCapSentence(truncated) {
  return truncated === true ? `The list is capped at ${STALE_CAP} questions in one sweep; the rest wait for the next one.` : '';
}

/** One shortlist row's plain words. */
export function candidateLine(candidate) {
  if (typeof candidate !== 'object' || candidate === null) return 'An unknown question';
  const name = typeof candidate.statement === 'string' && candidate.statement !== '' ? candidate.statement : 'a question without text';
  return `Item ${candidate.item_id} — ${name}`;
}

/**
 * The phase-5 outcome sentence for the final summary (the engine's
 * own proposed/accepted/rejected numbers). Empty when nothing was
 * asked.
 */
export function phaseOutcomeSentence(summary) {
  if (typeof summary !== 'object' || summary === null) return '';
  const n = (v) => (typeof v === 'number' ? v : 0);
  if (n(summary.stale) <= 0) return '';
  const asked = n(summary.proposed);
  const accepted = n(summary.accepted);
  const declined = n(summary.rejected);
  return `Old questions: ${asked === 0 ? 'none needed a proposal' : `${asked} ${asked === 1 ? 'proposal' : 'proposals'} made`}, ${accepted} accepted, ${declined} declined.`;
}

/** The result headline after an applied sweep (story 67). */
export function resultHeadline(summary) {
  const changed = (summary?.closed ?? 0) + (summary?.challenged ?? 0) + (summary?.reopened ?? 0);
  if (changed === 0) return 'Done. Nothing needed to change.';
  return `Done. ${changed} ${changed === 1 ? 'item was' : 'items were'} changed. The ledger shows why.`;
}

/**
 * The answer text for one loop action, sent to the engine through the
 * confirm session. 'stop' returns null — the screen calls stop()
 * (closing the input; the engine reads that as a quit), never a
 * written answer.
 *
 * @param {'confirm'|'reject'|'stop'} action
 * @returns {string|null}
 */
export function sweepAnswerFor(action) {
  if (action === 'confirm') return 'y';
  if (action === 'reject') return 'n';
  return null;
}

/** The Apply button's label (story 66: it says how many changes). */
export function applyLabel(changesCount) {
  const n = typeof changesCount === 'number' ? changesCount : 0;
  return n === 0 ? 'Apply (no status changes)' : `Apply ${n} ${n === 1 ? 'change' : 'changes'}`;
}

/**
 * The Link items confirm-session view model (app step 06, ticket A35).
 *
 * A PURE reducer over the validated `--confirm json` session events of
 * `ember relate` (bridge L2 §5.4, D4 already applied by the bridge
 * client): every event folds into one view object the Link screen
 * renders. No DOM, no I/O (T1) — the node suite drives the SAME event
 * shapes the Python contract suite pins
 * (tests/bridge/test_json_confirm.py, test_confirm_json_cli.py).
 *
 * The engine decides everything (P4), the app only renders what
 * arrived. The relate prompt kinds are choice only (`[y]es / [n]o /
 * [s]kip / [q]uit`); anything else is drift and fails loud in the log,
 * the same rule as Add. A proposal block of kind `link-preview` shows
 * BEFORE its prompt; the accepted `link` block arrives AFTER the write
 * — the accepted list is staged and only lands when the engine's next
 * event (or the summary) proves the write, exactly like Add's
 * staged- confirm pattern.
 */

/**
 * One fresh view. `awaiting` is null or 'choice'; `proposal` is the
 * open link preview {fields, text}; `log` carries every message event
 * (including the engine's `relate rejected: ...` gatekeeper lines) in
 * order; `links` is the accepted-links list, filled ONLY from the
 * engine's accepted `link` blocks (the blocks are printed after the
 * write, so a block IS the proof the link landed); `confirming` marks
 * the window between a staged confirm and its block, so a dead child
 * can never leave a half-proven row on the list; `emptySignal`
 * records that the engine printed one of its two documented
 * empty-pool lines ("no unrelated items", or the phase-2
 * {"pool_size": 0} document); those exits print NO summary event, so
 * the screen needs the flag to tell a hard early end (APP-002) from
 * story 46's honest "done".
 */
export function initialRelateView() {
  return {
    seenAny: false,
    proposal: null, // {fields, text} — one link preview
    awaiting: null, // null | 'choice' | 'unknown'
    unknownPrompt: null, // {text} — drift, fail loud
    log: [],
    links: [], // [{linkId, sourceItemId, targetItemId, linkType, status, rationale}]
    summary: null, // {accepted, rejected, skipped, aborted}
    confirming: false, // a confirm is in flight, its block has not arrived
    emptySignal: false,
    emptyText: null, // the engine's own empty-pool print, kept as evidence
  };
}

/** The engine's two documented empty-pool prints (docs/commands.md). */
export function relateEmptySignal(text) {
  if (typeof text !== 'string') return false;
  if (text === 'no unrelated items') return true;
  try {
    const parsed = JSON.parse(text);
    return (
      parsed &&
      typeof parsed === 'object' &&
      parsed.phase === 2 &&
      parsed.pool_size === 0
    );
  } catch {
    return false;
  }
}

/**
 * The picked item's row, read back from the pick list the app itself
 * loaded (`list-items`): both endpoints of a proposal show their real
 * words (story 43) without the app recomputing anything (D3) — the
 * statements come verbatim from the command's own document.
 *
 * @param {Array<{id: number, type?: string, statement?: string}>} pickList
 * @param {number|null} id
 * @returns {{id: number, type: string|null, statement: string|null}}
 */
export function pickRowFor(pickList, id) {
  const wanted = Number(id);
  const row =
    Array.isArray(pickList) && pickList.find((it) => Number(it && it.id) === wanted);
  if (!row) return { id: wanted, type: null, statement: null };
  return {
    id: wanted,
    type: typeof row.type === 'string' ? row.type : null,
    statement: typeof row.statement === 'string' ? row.statement : null,
  };
}

/**
 * Fold ONE validated session event into the view. Returns a new view;
 * the input is not mutated.
 */
export function applyRelateEvent(view, event) {
  const next = { ...view };
  next.seenAny = true;
  const ev = event && typeof event === 'object' ? event : {};
  switch (ev.event) {
    case 'block': {
      if (ev.kind === 'link-preview') {
        const fields = ev.fields && typeof ev.fields === 'object' ? ev.fields : null;
        next.proposal = { fields, text: typeof ev.text === 'string' ? ev.text : '' };
        next.awaiting = null;
        next.unknownPrompt = null;
        next.confirming = false;
        return next;
      }
      if (ev.kind === 'link') {
        // The accepted link: the engine writes first, prints second, so
        // THIS block is the proof the confirm landed (story 24's rule,
        // relate shape). An unparseable block is still the engine's own
        // proof of a write — kept with its raw text as the evidence.
        const f = ev.fields && typeof ev.fields === 'object' ? ev.fields : null;
        next.links = [
          ...next.links,
          {
            linkId: f && Number.isInteger(f.link_id) ? f.link_id : null,
            sourceItemId: f && Number.isInteger(f.source_item_id) ? f.source_item_id : null,
            targetItemId: f && Number.isInteger(f.target_item_id) ? f.target_item_id : null,
            linkType: f && typeof f.link_type === 'string' ? f.link_type : null,
            status: f && typeof f.status === 'string' ? f.status : null,
            rationale: f && (typeof f.rationale === 'string' || f.rationale === null) ? f.rationale : null,
            rawText: typeof ev.text === 'string' ? ev.text : '',
          },
        ];
        next.proposal = null;
        next.awaiting = null;
        next.confirming = false;
        return next;
      }
      // Drift: fail loud in the log, keep going — never fail silently.
      next.log = [...next.log, `a block of kind "${String(ev.kind)}" arrived (a link run shows link previews)`];
      return next;
    }
    case 'prompt': {
      if (ev.kind === 'choice') {
        next.awaiting = 'choice';
        return next;
      }
      // relate asks choices only; any other kind is drift (fail loud).
      next.awaiting = 'unknown';
      next.unknownPrompt = { text: typeof ev.text === 'string' ? ev.text : '' };
      return next;
    }
    case 'message': {
      const text = typeof ev.text === 'string' ? ev.text : '';
      next.log = [...next.log, text];
      if (relateEmptySignal(text)) {
        next.emptySignal = true;
        // Keep the engine's own line: the empty state quotes it, D3.
        if (next.emptyText === null) next.emptyText = text;
      }
      return next;
    }
    case 'summary':
      next.summary = {
        accepted: Number(ev.accepted ?? 0),
        rejected: Number(ev.rejected ?? 0),
        skipped: Number(ev.skipped ?? 0),
        aborted: ev.aborted === true || ev.aborted === 1,
      };
      return next;
    default:
      return next;
  }
}

/**
 * Stage one confirm ('y') on the open preview: the confirm is in
 * flight until the engine's accepted `link` block proves the write
 * (see initialRelateView). Call after answerRelate('y') was accepted
 * by the main process.
 */
export function recordConfirm(view) {
  return { ...view, confirming: true, proposal: null, awaiting: null };
}

/**
 * Read a summary event's plain sentence (story 47): confirmed /
 * skipped / rejected counts, from the engine's own numbers (D3).
 */
export function relateSummarySentence(summary) {
  if (!summary || typeof summary !== 'object') return 'The run ended.';
  const a = Number(summary.accepted ?? 0);
  const s = Number(summary.skipped ?? 0);
  const r = Number(summary.rejected ?? 0);
  return `Done. ${a} ${a === 1 ? 'link' : 'links'} confirmed, ${s} skipped, ${r} rejected.`;
}

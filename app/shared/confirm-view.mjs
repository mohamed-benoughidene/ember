/**
 * The Add confirm-session view model (app step 05, tickets A34).
 *
 * A PURE reducer over the validated `--confirm json` session events
 * (bridge L2 §5.4, D4 already applied by the bridge client): every
 * event folds into one view object the Add screen renders. No DOM, no
 * I/O (T1) — the node suite drives the same event streams the Python
 * contract suite pins (tests/bridge/test_confirm_json_cli.py).
 *
 * The engine decides everything (P4): the app only renders what
 * arrived. Unknown prompts stay fail-loud (raw text kept, kind
 * 'unknown'), the same drift rule the block parsers use on the Python
 * side.
 */

/**
 * One fresh view. `awaiting` is null, 'choice', 'type', 'statement',
 * 'metadata' or 'unknown'; `editValues` carries the user's edit draft;
 * `saved` is the "Saved so far" list (story 24); `log` carries every
 * message event (drops, gatekeeper rejections, warnings) in order.
 */
export function initialAddView() {
  return {
    seenAny: false,
    proposal: null, // {fields, text, warn}
    awaiting: null,
    editValues: null, // {type, statement, metadata}
    editMessage: null, // the engine's re-ask line ("invalid type", ...)
    unknownPrompt: null, // {text, choices} — drift, fail loud
    log: [],
    saved: [], // [{id, type, statement}]
    summary: null, // the summary event object
    pendingConfirm: null, // staged until the engine's next event proves the write
  };
}

/**
 * The near-duplicate warning words (story 19). `fields` is one parsed
 * capture block's fields; null warning (or no warning key) -> null.
 */
export function proposalWarnText(fields) {
  const warning = fields && fields.near_dup_warning;
  if (!warning || typeof warning.matching_item_id !== 'number') return null;
  const pct = Math.round((Number(warning.similarity) || 0) * 100);
  return `Looks very similar to item ${warning.matching_item_id} (${pct}% alike). Confirming both is fine if they really say different things.`;
}

/** The edit draft values: keep what is open, fill the rest from the proposal. */
function mergeEditValues(view) {
  const keep = view.editValues ?? {};
  const fields = view.proposal && view.proposal.fields ? view.proposal.fields : {};
  return {
    type: keep.type ?? (typeof fields.type === 'string' ? fields.type : ''),
    statement: keep.statement ?? (typeof fields.statement === 'string' ? fields.statement : ''),
    metadata:
      keep.metadata ??
      (fields.metadata === null || fields.metadata === undefined ? '' : String(fields.metadata)),
  };
}

const EDIT_KINDS = ['type', 'statement', 'metadata'];

/**
 * Fold ONE validated session event into the view. Returns a new view;
 * the input is not mutated.
 */
export function applyAddEvent(view, event) {
  const next = { ...view };
  if (next.pendingConfirm) {
    // The engine only produces the next event after the confirm's write
    // went through (a failing write exits instead), so the next event
    // is the proof that the confirm took effect (story 24).
    next.saved = [...next.saved, next.pendingConfirm];
    next.pendingConfirm = null;
  }
  next.seenAny = true;
  const ev = event && typeof event === 'object' ? event : {};
  switch (ev.event) {
    case 'block': {
      if (ev.kind !== 'item') {
        // Drift: fail loud in the log, keep going — never fail silently.
        next.log = [...next.log, `a block of kind "${String(ev.kind)}" arrived (an add shows items)`];
        return next;
      }
      const fields = ev.fields && typeof ev.fields === 'object' ? ev.fields : null;
      next.proposal = {
        fields,
        text: typeof ev.text === 'string' ? ev.text : '',
        warn: proposalWarnText(fields),
      };
      next.awaiting = null;
      next.editValues = null;
      next.editMessage = null;
      next.unknownPrompt = null;
      return next;
    }
    case 'prompt': {
      if (ev.kind === 'choice') {
        next.awaiting = 'choice';
        return next;
      }
      if (EDIT_KINDS.includes(ev.kind)) {
        next.awaiting = ev.kind;
        next.editValues = mergeEditValues(view);
        next.editMessage = null;
        return next;
      }
      next.awaiting = 'unknown';
      next.unknownPrompt = {
        text: typeof ev.text === 'string' ? ev.text : '',
      };
      return next;
    }
    case 'message': {
      next.log = [...next.log, typeof ev.text === 'string' ? ev.text : ''];
      if (EDIT_KINDS.includes(next.awaiting)) next.editMessage = typeof ev.text === 'string' ? ev.text : '';
      return next;
    }
    case 'summary':
      next.summary = { ...ev };
      return next;
    default:
      return next;
  }
}

/**
 * Stage one confirm ('y') on the current proposal: staged until the
 * engine's next event proves the write (see above). Call right after
 * `answerAdd('y')` was accepted by the main process.
 */
export function recordConfirm(view) {
  const fields = view.proposal && view.proposal.fields ? view.proposal.fields : null;
  return {
    ...view,
    pendingConfirm: {
      id: fields && typeof fields.id === 'number' ? fields.id : null,
      type: fields && typeof fields.type === 'string' ? fields.type : null,
      statement:
        fields && typeof fields.statement === 'string'
          ? fields.statement
          : '(a proposal that arrived as raw text only)',
    },
  };
}

/**
 * Which final stage the view is in, from the events alone (the engine
 * decides, D3/story 28: zero confirmed AND zero rejected at a normal
 * end means nothing could be proposed from this text):
 * 'loading' | 'session' | 'stopped' | 'empty' | 'summary'.
 */
export function addStage(view) {
  if (view.summary) {
    if (Number(view.summary.aborted) === 1) return 'stopped';
    if (Number(view.summary.accepted ?? 0) === 0 && Number(view.summary.rejected ?? 0) === 0) {
      return 'empty';
    }
    return 'summary';
  }
  return view.seenAny ? 'session' : 'loading';
}

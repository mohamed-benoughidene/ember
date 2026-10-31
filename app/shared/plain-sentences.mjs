/**
 * The plain-sentence table (interface-app-plan.md §5.6, L2 §5.6).
 *
 * One entry per code/word the step-04 screens can show TODAY (app step
 * file §4): the APP- namespace plus the QUERY- codes the read commands
 * raise (QUERY-001, 003, 004, 006, 007). Every other engine or bridge
 * code falls back to a generic family sentence — NEVER a blank (story
 * 102: errors say what failed and what to do next, with the code on
 * request).
 *
 * History words (app step file §1, story 122): every `history` event
 * kind, including the undo-era kinds (`undone`, `redone`, `item_edited`,
 * `link_unreversed` — the U5-1 handoff), has a plain label and
 * sentence. A node test walks `ember/**\/errors.py` and `ember/query/
 * history.py` and fails when this table claims a code that does not
 * exist, or when a history kind has no entry.
 *
 * Pure module (T1): strings in, strings out; no DOM, no I/O.
 */

/* ---------- error codes ---------- */

export const ERROR_SENTENCES = {
  'APP-000': {
    title: 'Something in the app did not work.',
    what: 'Ember hit an unexpected internal error.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'APP-001': {
    title: 'Ember could not be started.',
    what: 'The app could not start the Ember program that holds your knowledge base.',
    next: 'Make sure Ember is installed, then try again.',
  },
  'APP-002': {
    title: 'Ember gave an unreadable answer.',
    what: 'The Ember program answered, but the app could not read the answer as data.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'APP-003': {
    title: 'The AI connection could not be saved.',
    what: 'The operating system keyring is not available, so the key was NOT saved on disk.',
    next: 'You can keep the key for this session only, or try again later.',
  },
  'APP-004': {
    title: 'Your settings could not be read.',
    what: 'The settings file is damaged or was written by another version. The usual settings are in use.',
    next: 'Saving a setting rewrites the file. Nothing else is affected.',
  },
  'APP-005': {
    title: 'The keyboard shortcut was refused.',
    what: 'Another program may already use this shortcut.',
    next: 'Use the tray icon or the File menu to add text instead.',
  },
  'APP-006': {
    title: 'That file is not a knowledge base.',
    what: 'The chosen file is missing, or it is not an Ember knowledge base file.',
    next: 'Choose a different file, or start a new one in setup.',
  },
  'APP-007': {
    title: 'Ember is not installed where the app expects it.',
    what: 'The app could not find the Ember program.',
    next: 'Check the installation, then reopen the app.',
  },
  'APP-008': {
    title: 'Ember took too long to answer.',
    what: 'A read was tried twice; a write is never repeated automatically, so nothing was done twice.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'QUERY-001': {
    title: 'There is no item with that number.',
    what: 'The item number is not in this knowledge base. It may have never existed on this file.',
    next: 'Look the item up again and select it from the list.',
  },
  'QUERY-003': {
    title: 'The knowledge base file could not be opened.',
    what: 'The file is missing, was moved, or is not a readable Ember knowledge base.',
    next: 'Check where the file is, then open it again in setup.',
  },
  'QUERY-004': {
    title: 'This knowledge base is in an older format.',
    what: 'The file was made by an older version of Ember and this view needs a newer format.',
    next: 'Open the file with the Ember command line once, then try again here.',
  },
  'QUERY-006': {
    title: 'That filter or limit was not understood.',
    what: 'A filter value or a paging size was outside its allowed values.',
    next: 'Set the filters again and try once more.',
  },
  'QUERY-007': {
    title: 'That date was not understood.',
    what: 'The date filter needs a full date; the text given did not read as one.',
    next: 'Pick the date again from the date field and try once more.',
  },
};

/** Family names for the generic fallback: code prefix -> plain family. */
export const ERROR_FAMILIES = {
  APP: 'in the app itself',
  QUERY: 'in the query engine (the reading views)',
  BRIDGE: 'between the app and the Ember program',
  CAPTURE: 'in the capture engine (adding text)',
  RELATE: 'in the relate engine (linking items)',
  MAINTAIN: 'in the maintain engine (the sweep)',
  BACKUP: 'in the backup command',
  EXPORT: 'in the export command',
};

/**
 * The sentence for any code. Exact entry first; then a generic family
 * sentence naming the family; then a fully generic sentence. Unknown
 * code -> generic family title, never a blank (plan §5.6).
 *
 * @param {string} code e.g. "QUERY-003"
 * @returns {{title: string, what: string, next: string}}
 */
export function sentenceFor(code) {
  if (typeof code === 'string' && ERROR_SENTENCES[code]) return ERROR_SENTENCES[code];
  const family = typeof code === 'string' && /^[A-Z]+-\d{3}$/.test(code) ? code.slice(0, code.indexOf('-')) : null;
  if (family !== null) {
    const where = ERROR_FAMILIES[family] ?? 'in Ember';
    return {
      title: `A problem ${where} was reported.`,
      what: `Ember reported the error ${code}. The app has no plainer words for it yet.`,
      next: 'Try again. If it keeps happening, close and reopen the app.',
    };
  }
  return {
    title: 'Something did not work.',
    what: 'Ember reported an error without a code.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  };
}

/* ---------- history (ledger) words: story 122 ---------- */

/**
 * Every `history` event kind (from `ember/query/history.py`'s
 * `_KIND_BY_PAIR` values plus `unknown`) has a plain label and a
 * sentence pattern. The undo-era kinds are here (U5-1 handoff):
 * `undone`, `redone`, `item_edited`, `link_unreversed`.
 */
export const HISTORY_KINDS = {
  created: { label: 'Added' },
  proposed_rejected: { label: 'Proposal rejected' },
  validated: { label: 'Verified mark' },
  link_confirmed: { label: 'Link confirmed' },
  link_rejected: { label: 'Link rejected' },
  status_changed: { label: 'Status changed' },
  status_origin_changed: { label: 'Status source changed' },
  link_reversed: { label: 'Replacement reversed' },
  link_removed: { label: 'Link removed' },
  item_edited: { label: 'Item edited' },
  undone: { label: 'Undone' },
  redone: { label: 'Redone' },
  link_unreversed: { label: 'Reversal undone' },
  unknown: { label: 'Change without words' },
};

/**
 * @param {string} kind a history event kind
 * @returns {string} the plain label, never blank
 */
export function historyKindLabel(kind) {
  const entry = typeof kind === 'string' ? HISTORY_KINDS[kind] : undefined;
  return entry ? entry.label : HISTORY_KINDS.unknown.label;
}

/**
 * The one plain sentence for a history event (the ledger row text).
 * `event` is one envelope row of `ember history`: timestamp, kind,
 * cause, field_changed, item_id, link_id, link_source_item_id,
 * link_target_item_id, link_type, old_value, new_value, close_reason.
 *
 * @param {object} event
 * @returns {string}
 */
export function historyEventSentence(event) {
  if (typeof event !== 'object' || event === null) return historyKindLabel('unknown') + '.';
  const kind = typeof event.kind === 'string' ? event.kind : 'unknown';
  const item = (id) => (id === null || id === undefined ? 'an item' : `item ${id}`);
  const link = (id) => (id === null || id === undefined ? 'a link' : `link ${id}`);
  const oldV = event.old_value ? String(event.old_value) : null;
  const newV = event.new_value ? String(event.new_value) : null;
  let sentence;
  switch (kind) {
    case 'created':
      sentence = `${capitalize(item(event.item_id))} was added.`;
      break;
    case 'proposed_rejected':
      sentence = `A proposal for ${item(event.item_id)} was rejected; nothing was saved.`;
      break;
    case 'validated':
      sentence = `The verified mark on ${item(event.item_id)} changed.`;
      break;
    case 'link_confirmed':
      sentence = `${capitalize(link(event.link_id))} was confirmed: ${item(event.link_source_item_id)} ${humanLinkType(event.link_type)} ${item(event.link_target_item_id)}.`;
      break;
    case 'link_rejected':
      sentence = `${capitalize(link(event.link_id))} was rejected. Nothing is deleted; the link stays on record.`;
      break;
    case 'status_changed': {
      const move = oldV && newV ? `${oldV} to ${newV}` : newV ? `set to ${newV}` : 'changed';
      const reason = event.close_reason ? ` (reason: ${event.close_reason})` : '';
      sentence = `${capitalize(item(event.item_id))} status changed: ${move}${reason}.`;
      break;
    }
    case 'status_origin_changed':
      sentence = `Who set ${item(event.item_id)}'s status changed: by you, or by the sweep.`;
      break;
    case 'link_reversed':
      sentence = `${capitalize(link(event.link_id))} (supersedes) was reversed; the older item is back.`;
      break;
    case 'link_removed':
      sentence = `${capitalize(link(event.link_id))} was removed (marked Rejected, never deleted).`;
      break;
    case 'item_edited':
      sentence = `${capitalize(item(event.item_id))} was edited (${event.field_changed ?? 'a field'} changed).`;
      break;
    case 'undone':
      sentence = 'A change was undone. Nothing was erased; the ledger keeps both lines.';
      break;
    case 'redone':
      sentence = 'An undone change was redone.';
      break;
    case 'link_unreversed':
      sentence = 'A reversal was undone, so the replacement is in force again.';
      break;
    default:
      sentence = 'A change Ember has no words for was recorded.';
      break;
  }
  if (typeof event.cause === 'string' && event.cause.startsWith('user_')) {
    sentence += ' Done by you.';
  }
  return sentence;
}

/** The human words for a link type (glossary words, `depends_on` -> 'depends on'). */
export function humanLinkType(linkType) {
  return typeof linkType === 'string' && linkType !== '' ? linkType.replace(/_/g, ' ') : 'is linked to';
}

function capitalize(text) {
  const s = String(text);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

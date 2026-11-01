/**
 * The plain-sentence table (interface-app-plan.md §5.6, L2 §5.6).
 *
 * One entry per code the screens can show. Fix F5 (plan §5.6: "A
 * test walks `ember/**\/errors.py` and fails when a code has no
 * entry"): the table is now TOTAL over every code the engine defines
 * — plus the tested refinements (`app/shared/capture-words.mjs` for
 * CAPTURE-008, `app/shared/maintain-sentences.mjs` for its MAINTAIN
 * codes, `app/shared/relate-words.mjs` for two RELATE details), which
 * keep precedence where they exist. Every below-entry was written
 * ONLY from the error class's name, docstring and raise sites in the
 * engine — never from assumed behaviour.
 *
 * Every other engine or bridge
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

/* =====================================================================
 * APP STEP 09 (Keep safe) — added at the END of the file as this
 * step's own bracketed block (ticket A38; sibling lanes append their
 * own blocks at the end; nothing above is moved or reformatted).
 *
 * - Full ERROR_SENTENCES entries for the BACKUP-/EXPORT- codes the
 *   Keep safe screen can show (stories 70-77; all six exist in
 *   ember/adapters/errors.py — the drift walk in
 *   test/plain-sentences.test.js keeps chasing the sources).
 * - The db-check report read-map (story 75): every report line the
 *   engine prints (ember/adapters/db_check.py's `lines`) maps to one
 *   plain sentence; an unknown line is shown as written, never blank.
 * ===================================================================== */

Object.assign(ERROR_SENTENCES, {
  'BACKUP-001': {
    title: 'The knowledge base could not be read for the backup.',
    what: 'The knowledge base file is missing, or it is not a readable Ember file, so no backup was written.',
    next: 'Check where your knowledge base file is, then try again. Your knowledge base file is unchanged.',
  },
  'BACKUP-002': {
    title: 'This file is not a knowledge base Ember can back up.',
    what: 'The file could be opened but its record of the format could not be read, so no backup was written.',
    next: 'Check that this is your knowledge base file, then try again. Your knowledge base file is unchanged.',
  },
  'BACKUP-003': {
    title: 'The backup was not written there.',
    what: 'Ember refuses to write over your knowledge base file itself; otherwise the place chosen could not be written to.',
    next: 'Choose a different location for the backup. Your knowledge base file is unchanged.',
  },
  'BACKUP-004': {
    title: 'The backup copy did not read back.',
    what: 'The copy was written but could not be read again as a whole file, so it was deleted rather than left broken.',
    next: 'Try again. If it keeps happening, the disk may be full or faulty. Your knowledge base file is unchanged.',
  },
  'EXPORT-001': {
    title: 'The text file could not be written.',
    what: 'The place chosen refused the write: the folder may be full, read-only, or the name may not be allowed.',
    next: 'Choose a different location for the export. Your knowledge base file is unchanged.',
  },
  'EXPORT-002': {
    title: 'That location is your knowledge base file itself.',
    what: 'An export cannot be restored into Ember, so writing it over your knowledge base would destroy it; Ember refused.',
    next: 'Choose a different file name for the export. Your knowledge base file is unchanged.',
  },
});

/**
 * Report -> verdict words (story 75). `result` is the engine's own
 * `result:` value: `OK` | `DRIFT` | `UNREADABLE`. Anything else reads
 * with the generic words, never a blank.
 *
 * @param {string} result
 * @returns {{title: string, what: string, next: string, kind: 'ok'|'drift'|'unreadable'|'unknown'}}
 */
export function dbCheckVerdictWords(result) {
  if (result === 'OK') {
    return {
      kind: 'ok',
      title: 'No problems found.',
      what: 'Your knowledge base file opened and every check passed.',
      next: 'You can rely on this file. The check read it only; nothing was changed.',
    };
  }
  if (result === 'DRIFT') {
    return {
      kind: 'drift',
      title: 'The check found things that do not match.',
      what: 'The file opened and your items are readable, but some internal records do not match what this version of Ember expects.',
      next: 'Try again. If it stays, tell whoever helps you with Ember — the lines below name what does not match. The check changed nothing.',
    };
  }
  if (result === 'UNREADABLE') {
    return {
      kind: 'unreadable',
      title: 'The file could not be read.',
      what: 'The knowledge base file is missing, was moved, or is not a readable Ember file.',
      next: 'Check where your knowledge base file is, or open a different file below. The check changed nothing.',
    };
  }
  return {
    kind: 'unknown',
    title: 'The check ended without a known verdict.',
    what: `The check reported "${String(result)}", which this version of the app has no words for.`,
    next: 'Try again. The check changed nothing.',
  };
}

/**
 * One report line -> one plain sentence (story 75: "problems in plain
 * words"). The known line shapes come from ember/adapters/db_check.py;
 * an unknown line is returned as written (the renderer escapes it), so
 * a future report can never show a blank row.
 *
 * @param {string} line
 * @returns {string}
 */
export function dbCheckRowSentence(line) {
  if (typeof line !== 'string' || line.trim() === '') return 'The check printed an empty line.';
  let m = line.match(/^version:\s*(\d+)$/);
  if (m) return `File format version ${m[1]}.`;
  if (/^floors:.*unmet/.test(line)) return 'The file is older than some parts of Ember need.';
  if (/^floors:/.test(line)) return "Every part's minimum file format is met.";
  m = line.match(/^triggers:\s*missing\s+(.+)$/);
  if (m) return `Some safety triggers are missing: ${m[1]}.`;
  if (/^triggers:/.test(line)) return 'The safety triggers are in place.';
  m = line.match(/^link_compat:\s*(\d+) rows,\s*drift/);
  if (m) return `The link compatibility table does not match what Ember expects (${m[1]} rows).`;
  m = line.match(/^link_compat:\s*(\d+) rows/);
  if (m) return `The link compatibility table matches the rules (${m[1]} rows).`;
  m = line.match(/^foreign_key_check:\s*(\d+) violations?$/);
  if (m) {
    const n = Number(m[1]);
    return n === 0
      ? 'No item or link points at a record that is gone.'
      : `${n} ${n === 1 ? 'record points' : 'records point'} at other records that are gone.`;
  }
  m = line.match(/^reversal replay:\s*(\d+) reversed links,\s*column != ledger/);
  if (m) return `Replacement records disagree with the ledger (${m[1]} reversed ${m[1] === '1' ? 'link' : 'links'}).`;
  m = line.match(/^reversal replay:\s*(\d+) reversed links/);
  if (m) return `Replacement records agree with the ledger (${m[1]} reversed ${m[1] === '1' ? 'link' : 'links'}).`;
  m = line.match(/^group_id:\s*(\d+) undo\/redo pointers, all name existing groups$/);
  if (m) return `Every undo record points at a real change (${m[1]} records).`;
  if (/^group_id:.*not applicable/.test(line)) return 'The undo-record check does not apply to this older file format.';
  if (/^group_id:/.test(line)) return 'Some undo records point at changes that are gone.';
  if (/^result:\s*OK$/.test(line)) return 'Verdict: no problems found.';
  if (/^result:\s*DRIFT$/.test(line)) return 'Verdict: things do not match.';
  if (/^result:\s*UNREADABLE$/.test(line)) return 'Verdict: the file could not be read.';
  return line.trim();
}

/* =====================================================================
 * APP STEP 06 (Link items) — added at the END of the file as this
 * step's own bracketed block (ticket A35; sibling lanes append their
 * own blocks at the end; nothing above is moved or reformatted).
 *
 * Full ERROR_SENTENCES entries for the RELATE- codes the Link items
 * screen can surface (stories 42-48; step file §1: "missing optional
 * package (RELATE- code through the table with what to do)"). All of
 * them exist in ember/relate/errors.py — the anti-drift walk in
 * test/plain-sentences.test.js keeps chasing the source.
 * ===================================================================== */

Object.assign(ERROR_SENTENCES, {
  'RELATE-001': {
    title: 'There is no item with that number.',
    what: 'The item Ember was asked to link is not in this knowledge base.',
    next: 'Go back to the list and pick the item again.',
  },
  'RELATE-005': {
    title: 'That link kind is not one Ember knows.',
    what: 'A proposal used a link type outside the five kinds Ember keeps (supports, contradicts, supersedes, answers, depends on).',
    next: 'Nothing was written. Run Link items again.',
  },
  'RELATE-006': {
    title: 'Those two items cannot be linked that way.',
    what: 'The kind of link does not fit the two items\' types; Ember\'s compatibility table refuses it.',
    next: 'Nothing was written. You can skip such a proposal or run Link items again.',
  },
  'RELATE-007': {
    title: 'That replacement could not be made.',
    what: 'A supersedes link pointed at an item that is already Closed, which Ember never replaces.',
    next: 'Nothing was written. Run Link items again.',
  },
  'RELATE-008': {
    title: 'That link broke a premise rule.',
    what: 'The proposal failed one of the ordered checks Ember runs before any link is written.',
    next: 'Nothing was written. Run Link items again.',
  },
  'RELATE-009': {
    title: 'That link already exists.',
    what: 'A proposal repeated a link Ember already has (in either direction), however the old link ended up.',
    next: 'Nothing was written. Nothing is duplicated.',
  },
  'RELATE-010': {
    title: 'An item cannot link to itself.',
    what: 'A proposal named the same item on both sides.',
    next: 'Nothing was written. Run Link items again.',
  },
  'RELATE-012': {
    title: 'The knowledge base file could not be opened.',
    what: 'The file for linking is missing, was moved, or is not an Ember knowledge base.',
    next: 'Check where the file is, then open it again in setup. Nothing was changed.',
  },
  'RELATE-014': {
    title: 'This knowledge base is in an older format.',
    what: 'Linking needs a newer file format than this knowledge base has.',
    next: 'Open the file with the Ember command line once (a write migrates it), then try again. Nothing was changed.',
  },
  'RELATE-017': {
    title: 'The linking brain is not installed.',
    what: 'Linking needs the optional language package (sentence-transformers), which is missing on this computer.',
    next: 'Install the relate extra: python -m pip install -e ".[relate]". Then run Link items again.',
  },
  'RELATE-032': {
    title: 'The AI service could not answer.',
    what: 'The request for link proposals failed; the service may be unreachable or it refused the key.',
    next: 'Check the AI connection, then try again. Nothing was changed.',
  },
  'RELATE-035': {
    title: 'Ember is missing a setting it needs.',
    what: 'A needed value (the AI key, or the embedder settings) was not there.',
    next: 'Check the AI connection in Settings, then try again. Nothing was changed.',
  },
});

/* =====================================================================
 * FIX F5 (2026-11-01) — the total table. Every code in
 * `ember/**\/errors.py` that no other sentence file owns now has a
 * full {title, what, next} entry, written ONLY from the class name,
 * its docstring and its raise sites (never assumed behaviour). Codes
 * NOT listed here are owned elsewhere: CAPTURE-008 (capture-words),
 * CAPTURE-016 and MAINTAIN-001..006, 013..017, 023..027
 * (maintain-sentences). The -000 family bases are never raised
 * directly; they get honest general words so the table stays total.
 * ===================================================================== */

Object.assign(ERROR_SENTENCES, {
  'CAPTURE-000': {
    title: 'A problem in the capture engine was reported.',
    what: 'Ember reported a general problem in the part that adds text.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'CAPTURE-001': {
    title: 'The text file could not be found.',
    what: 'The file of text Ember was asked to add is missing.',
    next: 'Check the file, then try again. Nothing was created.',
  },
  'CAPTURE-002': {
    title: 'That text file is too large.',
    what: 'The file is larger than Ember accepts; Ember keeps text files under 5 MB.',
    next: 'Use a smaller text file. Nothing was created.',
  },
  'CAPTURE-003': {
    title: 'The text could not be read.',
    what: 'Reading the text (from a file or pasted input) failed.',
    next: 'Try again. Nothing was created.',
  },
  'CAPTURE-004': {
    title: 'That file is not readable text.',
    what: 'The file is not UTF-8 text; it may be a binary file.',
    next: 'Use a plain text file saved as UTF-8. Nothing was created.',
  },
  'CAPTURE-005': {
    title: 'Reading the stored sources failed.',
    what: 'A read of the stored source texts in the knowledge base failed.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'CAPTURE-006': {
    title: 'Saving the source text failed.',
    what: 'Writing the source text into the knowledge base failed, so nothing was created.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'CAPTURE-007': {
    title: 'The AI service could not be used.',
    what: 'The request to the AI service failed.',
    next: 'Check the AI connection, then try again. Your text is kept; nothing was created.',
  },
  'CAPTURE-008': {
    title: 'The AI service could not answer.',
    what: 'The request for proposals failed: the service was not reachable, or it refused the key.',
    next: 'Check the AI connection in Settings, then try again. Your text is kept; nothing was created.',
  },
  'CAPTURE-009': {
    title: 'The AI answer was not understandable.',
    what: 'The AI service answered, but the answer did not have the shape Ember expects.',
    next: 'Try again. If it keeps happening, check the AI connection. Nothing was created.',
  },
  'CAPTURE-010': {
    title: 'A capture setting was not understood.',
    what: 'A setting that says how much surrounding text Ember sends to the AI (the context mode) has an unknown value.',
    next: 'Check the Ember setting in your environment, then try again. Nothing was created.',
  },
  'CAPTURE-011': {
    title: 'Reading the items failed.',
    what: 'A read of the items in the knowledge base failed.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'CAPTURE-012': {
    title: "The item's source text is missing.",
    what: 'The knowledge base has no stored source text for this item.',
    next: 'Add the text again, or run the health check (Keep safe).',
  },
  'CAPTURE-013': {
    title: 'Saving the item failed.',
    what: 'Writing the new item into the knowledge base failed, so it was not created.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'CAPTURE-014': {
    title: 'The Add was stopped.',
    what: 'Adding was stopped by you, or the answers ended early. This line is not usually shown on its own.',
    next: 'Nothing was created. You can add text again.',
  },
  'CAPTURE-015': {
    title: 'There is no item with that number.',
    what: 'The item number asked for is not in this knowledge base.',
    next: 'Look the item up again and pick it from the list.',
  },
  'RELATE-000': {
    title: 'A problem in the relate engine was reported.',
    what: 'Ember reported a general problem in the part that links items.',
    next: 'Try again. If it keeps happening, close and reopen the app. Nothing was linked.',
  },
  'RELATE-011': {
    title: 'Saving the record of the change failed.',
    what: "The link was being written when the ledger (Ember's record of every change) could not be updated. The save is all-or-nothing.",
    next: 'Try again. If it keeps happening, run the health check (Keep safe). Nothing was linked.',
  },
  'RELATE-013': {
    title: 'The knowledge base could not be brought up to date.',
    what: "Updating the file's format to what Ember needs failed. A backup copy of your file was kept beside it before the attempt.",
    next: 'Run the health check (Keep safe), then try again.',
  },
  'RELATE-016': {
    title: 'Reading the items failed.',
    what: 'A read of the items in the knowledge base failed while Link items was preparing.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'RELATE-018': {
    title: 'Turning text into meaning numbers failed.',
    what: 'The part that compares items by meaning (the embedder) could not process the text.',
    next: 'Try again. Nothing was linked.',
  },
  'RELATE-019': {
    title: 'Saving the meaning numbers failed.',
    what: 'Writing the meaning numbers (the search cache) into the knowledge base failed.',
    next: 'Try again. Nothing was linked.',
  },
  'RELATE-021': {
    title: 'Reading the links failed.',
    what: 'A read of the links between items failed.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'RELATE-022': {
    title: 'Comparing items by meaning failed.',
    what: 'The similarity calculation between texts failed.',
    next: 'Try again. Nothing was linked.',
  },
  'RELATE-023': {
    title: 'Reading the project labels failed.',
    what: 'A read of the project labels (metadata) on items failed.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'RELATE-024': {
    title: 'A proposal pointed at an item that was not offered.',
    what: 'An AI suggestion named a second item outside the candidate list Ember built.',
    next: 'Nothing was written. Run Link items again and pick from the list.',
  },
  'RELATE-025': {
    title: 'A proposal named a different starting item.',
    what: 'An AI suggestion claimed to come from another item than the one being linked.',
    next: 'Nothing was written. Run Link items again.',
  },
  'RELATE-026': {
    title: 'The first item of the link was not found.',
    what: 'The item the link starts from is not in this knowledge base.',
    next: 'Look the item up again. Nothing was written.',
  },
  'RELATE-027': {
    title: 'The second item of the link was not found.',
    what: 'The item the link points to is not in this knowledge base.',
    next: 'Look the item up again. Nothing was written.',
  },
  'RELATE-028': {
    title: 'That replacement would make a loop.',
    what: 'A supersedes link would create a chain where items replace each other in a circle. Ember refuses loops.',
    next: 'Nothing was written. Link a different pair.',
  },
  'RELATE-029': {
    title: 'Saving the link failed.',
    what: 'Writing the confirmed link into the knowledge base failed, so nothing was saved.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'RELATE-030': {
    title: 'The saved AI answer failed a check.',
    what: 'The record Ember keeps of the raw AI answer did not match its expected shape.',
    next: 'Run Link items again. If it keeps happening, run the health check (Keep safe). Nothing was linked.',
  },
  'RELATE-031': {
    title: 'Linking was stopped.',
    what: 'Linking was stopped by you, or the answers ended early.',
    next: 'Nothing was linked. You can run Link items again.',
  },
  'RELATE-033': {
    title: 'The AI answer was not understandable.',
    what: 'The AI service answered, but its link suggestions did not have the shape Ember expects.',
    next: 'Run Link items again. Nothing was written.',
  },
  'RELATE-036': {
    title: 'Saving the raw AI answer failed.',
    what: 'Ember keeps every raw AI answer on file before using it; this save failed, so the run stopped.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe). Nothing was linked.',
  },
  'RELATE-037': {
    title: 'Reading the meaning numbers failed.',
    what: 'The stored meaning numbers (the search cache) could not be read.',
    next: 'Run Link items again. If it keeps happening, run the health check (Keep safe). Nothing was linked.',
  },
  'MAINTAIN-000': {
    title: 'A problem in the maintain engine was reported.',
    what: 'Ember reported a general problem in the part that keeps items current.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'MAINTAIN-007': {
    title: 'The knowledge base file could not be opened.',
    what: 'The file is missing, was moved, or is not a readable Ember knowledge base.',
    next: 'Check where the file is, then open it again in setup. Nothing was changed.',
  },
  'MAINTAIN-008': {
    title: 'The knowledge base could not be brought up to date.',
    what: "Updating the file's format to what Ember needs failed. A backup copy of your file was kept before the attempt.",
    next: 'Run the health check (Keep safe), then try again.',
  },
  'MAINTAIN-009': {
    title: 'This knowledge base is in an older format.',
    what: 'The sweep needs a newer file format than this knowledge base has.',
    next: 'Open the file with the Ember command line once (a write brings it up to date), then try again. Nothing was changed.',
  },
  'MAINTAIN-010': {
    title: 'Reading the items failed.',
    what: 'A read of the items in the knowledge base failed.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'MAINTAIN-011': {
    title: 'Saving the status change failed.',
    what: 'Writing the status change into the knowledge base failed, so nothing was saved.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'MAINTAIN-012': {
    title: 'Saving the record of the change failed.',
    what: "The change was being written when the ledger (Ember's record of every change) could not be updated. Nothing was saved half-way.",
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'MAINTAIN-018': {
    title: 'The AI service could not answer.',
    what: 'The request for close suggestions failed; the service may be unreachable or it refused the key.',
    next: 'Check the AI connection, then run Clean up again. Nothing was changed.',
  },
  'MAINTAIN-019': {
    title: 'The AI answer was not understandable.',
    what: 'The AI service answered, but the close suggestion did not have the shape Ember expects.',
    next: 'Run Clean up again. Nothing was changed.',
  },
  'MAINTAIN-020': {
    title: 'Ember is missing a setting it needs.',
    what: 'The AI key needed for close suggestions was not there.',
    next: 'Check the AI connection in Settings, then run Clean up again. Nothing was changed.',
  },
  'MAINTAIN-021': {
    title: 'Saving the raw AI answer failed.',
    what: 'Ember keeps every raw AI answer on file; this save failed, so the run stopped.',
    next: 'Run Clean up again. Nothing was changed.',
  },
  'MAINTAIN-022': {
    title: 'Clean up was stopped.',
    what: 'The sweep was stopped by you, or the answers ended early.',
    next: 'The changes you already confirmed stay; nothing else was touched. You can run Clean up again.',
  },
  'QUERY-000': {
    title: 'A problem in the query engine was reported.',
    what: 'Ember reported a general problem in the reading views.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'QUERY-002': {
    title: 'There were no words to search for.',
    what: 'The search text had no searchable words in it.',
    next: 'Type what to search for, then search again.',
  },
  'QUERY-005': {
    title: 'Reading the knowledge base failed.',
    what: 'A read of the items, links or ledger failed.',
    next: 'Try again. If it keeps happening, run the health check (Keep safe).',
  },
  'BACKUP-000': {
    title: 'A problem with the backup was reported.',
    what: 'Ember reported a general backup problem.',
    next: 'Try again. Your knowledge base file is unchanged.',
  },
  'EXPORT-000': {
    title: 'A problem with the export was reported.',
    what: 'Ember reported a general export problem.',
    next: 'Try again. Your knowledge base file is unchanged.',
  },
  'BRIDGE-000': {
    title: 'A problem between the app and Ember was reported.',
    what: 'Ember reported a general problem on the structured door between the app and the Ember program.',
    next: 'Try again. If it keeps happening, close and reopen the app.',
  },
  'BRIDGE-001': {
    title: 'An answer could not be sent.',
    what: 'A confirmation answer could not be wrapped as data to send to Ember. This is an internal guard.',
    next: 'Try again.',
  },
});

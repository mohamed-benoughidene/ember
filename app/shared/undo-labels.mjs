/**
 * The Undo/Redo label derivation (app step file §1, spec §5.7, stories
 * 111-114, 123) — the PURE half of the undo bar. The screen itself
 * (renderer/screens/fix-close.mjs) places the buttons; the Edit menu
 * (step 12) consumes the same functions, so the label cannot drift
 * between the screen and the menu.
 *
 * The words come from the engine, never recomputed (D3): `undo
 * --dry-run --format json` answers
 * `summary: {direction, source_group_id, source_action, target_label,
 * new_group_id}` (pinned by tests/bridge/test_contract_table.py), and
 * `target_label` is already "item 3" / "link 7". The label reads
 * "Undo Close item 3" (spec §9: Apple's "Undo Typing" rule).
 *
 * Pure module (T1): objects in, strings out; no DOM, no I/O. Unit
 * tested in app/test/undo-labels.test.js.
 */

/** "Undo <action words> <target>", one entry per source_action the
 * engine's `_source_action` can return (ember/maintain/undo.py). The
 * words read with the engine's own targets ("item 3", "link 7"):
 * "Undo Close item 3", "Undo Removal of link 7". */
export const UNDO_ACTION_WORDS = {
  'close-item': 'Close',
  'set-status': 'Status change of',
  'set-validated': 'Set verified mark on',
  'clear-validated': 'Clear verified mark on',
  'edit-item': 'Edit',
  'remove-link': 'Removal of',
  'reverse-supersedes': 'Reversal of',
};

/**
 * @param {string} sourceAction the dry-run summary's `source_action`
 * @returns {string} the human words, capitalised ("Close"); throws on
 *   an action it does not know (fail loudly, never label wrongly).
 */
export function undoActionWords(sourceAction) {
  const words = UNDO_ACTION_WORDS[sourceAction];
  if (!words) throw new Error(`undo-labels: unknown source_action: ${String(sourceAction)}`);
  return words;
}

/**
 * The button/menu label for one derived plan.
 * `plan` is the dry-run document's `summary`:
 * {direction, source_group_id, source_action, target_label, ...}.
 *
 * @param {object} plan
 * @returns {string} e.g. "Undo Close item 3", "Redo Remove link 7"
 */
export function undoRedoLabel(plan) {
  if (typeof plan !== 'object' || plan === null) {
    throw new Error('undo-labels: the plan summary is missing');
  }
  if (plan.direction !== 'undo' && plan.direction !== 'redo') {
    throw new Error(`undo-labels: unknown direction: ${String(plan.direction)}`);
  }
  const verb = plan.direction === 'undo' ? 'Undo' : 'Redo';
  return `${verb} ${undoActionWords(plan.source_action)} ${plan.target_label}`;
}

/**
 * The confirming/sentence words after the undo or redo APPLIED (story
 * 62 + the honest undo words): built from the same plan fields plus
 * whether anything was written.
 *
 * @param {object} plan the dry-run summary the click was based on
 * @param {boolean} dryRun true only in tests/previews
 * @returns {string}
 */
export function undoDoneSentence(plan, dryRun = false) {
  const label = undoRedoLabel(plan);
  return dryRun
    ? `${label}: nothing has changed yet.`
    : plan.direction === 'undo'
      ? `${label.replace(/^Undo/, 'Undone')}: nothing was erased; the ledger keeps both lines.`
      : `${label.replace(/^Redo/, 'Redone')}: done again, the same append-only way.`;
}

/**
 * The disabled reason for the Undo/Redo buttons when the plan
 * derivation refused. Returns ONE plain sentence for the two honest
 * empty states (MAINTAIN-023/024, stories 111-113, 123), or null when
 * the buttons must stay ENABLED (any other code: the refusal belongs
 * to the click, where story 118's words show with Retry).
 *
 * @param {{code: string, detail?: string}|null} error the parsed error info
 * @returns {string|null}
 */
export function undoDisabledReason(error) {
  if (!error || typeof error.code !== 'string') return null;
  if (error.code === 'MAINTAIN-023') {
    const older = /no undo group|ungrouped_rows_exist=True|older ledger rows/i.test(error.detail ?? '');
    return older
      ? 'Nothing to undo. Changes written before Undo existed cannot be undone.'
      : 'Nothing to undo.';
  }
  if (error.code === 'MAINTAIN-024') {
    const cleared = /newer change cleared it|has_newer_original=True/i.test(error.detail ?? '');
    return cleared
      ? 'Nothing to redo. A newer change cleared it; undo again to make Redo available.'
      : 'Nothing to redo.';
  }
  return null;
}

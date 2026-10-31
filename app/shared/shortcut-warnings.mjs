/**
 * The quick-popup shortcut helpers (app step 10, stories 85-86;
 * interface-app-plan.md §5.5, DESIGN.md "Popup shortcut").
 *
 * Pure module (T1): an accelerator string in, warnings/display out.
 * No DOM, no Electron, no I/O. The pane shows these warnings BEFORE
 * the shortcut is saved; the OS refusal path (APP-005) is the
 * shortcut manager's job, not this table's.
 *
 * Warnings table (story 86, DESIGN.md "Don't use Control as the
 * modifier in a Mac shortcut"):
 *   - Control as a modifier on a Mac (the system uses it);
 *   - no modifier at all (typing a letter would open the popup);
 *   - a standard Mac Command shortcut (Command+Q/W/C/V/Z and the
 *     rest of the prototype's list).
 * Conflicts with OTHER programs are intentionally NOT detected (spec
 * §10 "Open"); the pane says the shortcut is untested on the system.
 */

/** Apple's shown modifier order (spec §10 Fact). */
export const MOD_ORDER = Object.freeze(['Control', 'Alt', 'Shift', 'Command']);

/** The canonical tokens an accelerator may hold. */
const MOD_TOKENS = {
  Control: 'Control',
  Ctrl: 'Control',
  Alt: 'Alt',
  Option: 'Alt',
  AltGr: 'Alt',
  Shift: 'Shift',
  Command: 'Command',
  Cmd: 'Command',
  Meta: 'Command',
  CommandOrControl: 'CommandOrControl',
};

/** The standard Mac Command shortcuts (the approved prototype's list). */
export const STANDARD_MAC_KEYS = Object.freeze([
  'A', 'B', 'C', 'F', 'G', 'H', 'I', 'J', 'M', 'N', 'O', 'P', 'Q',
  'S', 'T', 'U', 'V', 'W', 'X', 'Z', 'E',
]);

/**
 * Parse an Electron accelerator string.
 *
 * @param {string} accelerator e.g. "CommandOrControl+Alt+E"
 * @returns {{ok: true, mods: string[], key: string, raw: string}
 *           | {ok: false, raw: string}}
 *   `mods` holds canonical names in Apple's shown order, with
 *   CommandOrControl kept as-is (it is Command on a Mac, Ctrl
 *   elsewhere and warns in neither case).
 */
export function parseAccelerator(accelerator) {
  if (typeof accelerator !== 'string' || accelerator.trim() === '') {
    return { ok: false, raw: String(accelerator ?? '') };
  }
  const parts = accelerator.split('+').map((p) => p.trim()).filter((p) => p !== '');
  if (parts.length === 0) return { ok: false, raw: accelerator };
  const key = parts[parts.length - 1];
  const rawMods = parts.slice(0, -1);
  const mods = [];
  // A lone modifier with no key at all is not a shortcut; a lone plain
  // key IS parseable (mods = []), so the pane can warn "no modifier".
  if (rawMods.length === 0 && MOD_TOKENS[key]) return { ok: false, raw: accelerator };
  for (const part of rawMods) {
    const token = MOD_TOKENS[part];
    if (!token) return { ok: false, raw: accelerator };
    if (mods.includes(token)) return { ok: false, raw: accelerator };
    mods.push(token);
  }
  if (!/^[A-Z0-9]$/.test(key) && !/^(F\d{1,2}|Tab|Space|Comma|Period|Minus|Equal|PageUp|PageDown|Home|End|Left|Right|Up|Down|Insert|Delete|Backspace|Enter|Esc|Escape)$/.test(key)) {
    return { ok: false, raw: accelerator };
  }
  mods.sort((a, b) => MOD_ORDER.indexOf(a) - MOD_ORDER.indexOf(b));
  return { ok: true, mods, key, raw: accelerator };
}

/** The warnings for one accelerator on one platform ('mac' | 'other'). */
export function acceleratorWarnings(accelerator, platform = 'other') {
  const parsed = parseAccelerator(accelerator);
  if (!parsed.ok) {
    return ['The keys were not read as a shortcut. Set them again.'];
  }
  const warnings = [];
  const isMac = platform === 'mac';
  const effectiveMods = parsed.mods.flatMap((m) =>
    m === 'CommandOrControl' ? (isMac ? ['Command'] : ['Control']) : [m],
  );
  if (effectiveMods.length === 0) {
    warnings.push('Add a modifier key, so typing does not open the popup.');
  }
  if (isMac && effectiveMods.includes('Control')) {
    warnings.push('Control is used by the system on a Mac. Choose Option or Command instead.');
  }
  if (isMac && effectiveMods.length === 1 && effectiveMods[0] === 'Command' && STANDARD_MAC_KEYS.includes(parsed.key)) {
    warnings.push(`Command+${parsed.key} is a standard Mac shortcut. Choose another.`);
  }
  return warnings;
}

/** The human words for one accelerator token (Apple's shown names). */
function tokenName(token, isMac) {
  if (token === 'CommandOrControl') return isMac ? 'Command' : 'Ctrl';
  if (token === 'Command') return 'Command';
  if (token === 'Control') return isMac ? 'Control' : 'Ctrl';
  if (token === 'Alt') return isMac ? 'Option' : 'Alt';
  return 'Shift';
}

/**
 * The keys of an accelerator in shown order, human-named, for the
 * pane's key display (`.kbdkey` spans; DESIGN.md "Popup shortcut").
 *
 * @returns {string[]|null} null when the accelerator cannot be read
 */
export function displayKeys(accelerator, platform = 'other') {
  const parsed = parseAccelerator(accelerator);
  if (!parsed.ok) return null;
  const isMac = platform === 'mac';
  const mods = parsed.mods.map((m) => tokenName(m, isMac));
  const key = ['Comma', 'Period', 'Minus', 'Equal'].includes(parsed.key)
    ? parsed.key.toLowerCase()
    : parsed.key;
  return [...mods, key];
}

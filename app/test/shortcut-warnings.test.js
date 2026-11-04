'use strict';

/**
 * The shortcut warnings table (app step 10, step file §2: "warnings
 * table (Ctrl on Mac, bare key, Cmd+Q/W/C/V/Z etc.)", story 86) plus
 * the accelerator parsing/display the pane shows.
 */

const test = require('node:test');
const assert = require('node:assert/strict');

let mod; // the pure shortcut module (ESM), imported in each test
const warnings = async () => {
  mod ??= await import('../shared/shortcut-warnings.mjs');
  return mod;
};

test('the default shortcut warns nowhere (CommandOrControl is the portable main modifier)', async () => {
  const { acceleratorWarnings } = await warnings();
  assert.deepEqual(acceleratorWarnings('CommandOrControl+Alt+E', 'mac'), []);
  assert.deepEqual(acceleratorWarnings('CommandOrControl+Alt+E', 'other'), []);
});

test('Control as the modifier on a Mac warns (the system uses it)', async () => {
  const { acceleratorWarnings } = await warnings();
  assert.deepEqual(
    acceleratorWarnings('Control+Alt+E', 'mac').length,
    1,
    'exactly the Mac-Control warning',
  );
  assert.match(acceleratorWarnings('Control+Alt+E', 'mac')[0], /Control is used by the system on a Mac/);
  // On Windows/Linux Control is the normal modifier: no warning.
  assert.deepEqual(acceleratorWarnings('Control+Alt+E', 'other'), []);
});

test('a bare key with no modifier warns everywhere', async () => {
  const { acceleratorWarnings } = await warnings();
  for (const platform of ['mac', 'other']) {
    const list = acceleratorWarnings('E', platform);
    assert.equal(list.length, 1, platform);
    assert.match(list[0], /Add a modifier key/);
  }
});

test('standard Mac Command shortcuts warn by name (Q, W, C, V, Z and the rest)', async () => {
  const { acceleratorWarnings, STANDARD_MAC_KEYS } = await warnings();
  for (const key of ['Q', 'W', 'C', 'V', 'Z', 'X', 'S', 'P', 'A', 'E']) {
    assert.ok(STANDARD_MAC_KEYS.includes(key), `${key} is in the standard list`);
    const list = acceleratorWarnings(`Command+${key}`, 'mac');
    assert.equal(list.length, 1, `Command+${key}`);
    assert.match(list[0], /standard Mac shortcut/);
    assert.match(list[0], new RegExp(`Command\\+${key}`), 'the warning names the object');
  }
  // Command+Alt+E has a second modifier: it is not a standard shortcut.
  assert.deepEqual(acceleratorWarnings('Command+Alt+E', 'mac'), []);
  // On Windows/Linux Command+Q is not this rule's business.
  assert.deepEqual(acceleratorWarnings('Command+Q', 'other'), []);
});

test('an unreadable accelerator says so instead of silently passing', async () => {
  const { acceleratorWarnings } = await warnings();
  for (const bad of ['', undefined, 'Coffee+E', 'Alt', 'Control+Control+E', 'Ctrl+Alt+Control+E']) {
    const list = acceleratorWarnings(bad, 'other');
    assert.equal(list.length, 1, String(bad));
    assert.match(list[0], /were not read/);
  }
  // A lone modifier with no key at all is not readable either.
  assert.match(acceleratorWarnings('Shift+', 'other')[0], /were not read/);
});

test('parse: modifiers come back in Apple order, Option means Alt, Cmd means Command', async () => {
  const { parseAccelerator } = await warnings();
  const parsed = parseAccelerator('Shift+Ctrl+Option+Cmd+E');
  assert.deepEqual(parsed.mods, ['Control', 'Alt', 'Shift', 'Command']);
  assert.equal(parsed.key, 'E');
});

test('display: names follow the platform, keys show in the Apple order', async () => {
  const { displayKeys } = await warnings();
  assert.deepEqual(displayKeys('CommandOrControl+Alt+E', 'other'), ['Ctrl', 'Alt', 'E']);
  assert.deepEqual(displayKeys('CommandOrControl+Alt+E', 'mac'), ['Command', 'Option', 'E']);
  assert.deepEqual(displayKeys('CommandOrControl+Shift+Alt+E', 'other'), ['Ctrl', 'Alt', 'Shift', 'E']);
  assert.equal(displayKeys('nonsense', 'other'), null);
});

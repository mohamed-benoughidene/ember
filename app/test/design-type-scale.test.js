'use strict';

/**
 * The type-scale maths (L3 app step 03, step file §2): the five
 * text-size steps to 200%, and the rem conversion the spacing tokens
 * are built on. Pure module, no DOM.
 */

const test = require('node:test');
const assert = require('node:assert/strict');

test('type scale: textScale helpers', async () => {
  const { TEXT_STEPS, textScale, textStepNames, isTwoHundredPercent, remFromPx } = await import(
    '../renderer/design/text-scale.mjs'
  );

  assert.deepEqual(textStepNames(), ['Small', 'Default', 'Large', 'Larger', 'Largest']);
  assert.equal(textScale('Small'), 14);
  assert.equal(textScale('Default'), 15);
  assert.equal(textScale('Large'), 17);
  assert.equal(textScale('Larger'), 22);
  assert.equal(textScale('Largest'), 30);
  assert.equal(textScale('nonsense'), 15, 'unknown step names fall back to Default');

  assert.equal(isTwoHundredPercent(), true, 'Largest is 200% of Default');
  assert.equal(TEXT_STEPS.Largest, 30);
  assert.equal(TEXT_STEPS.Largest, TEXT_STEPS.Default * 2);
});

test('type scale: rem conversion reproduces the seven spacing steps', async () => {
  const { remFromPx } = await import('../renderer/design/text-scale.mjs');
  // DESIGN.md spacing table: px at the Default 15px root.
  assert.equal(remFromPx(4), '0.267rem');
  assert.equal(remFromPx(6), '0.4rem');
  assert.equal(remFromPx(8), '0.533rem');
  assert.equal(remFromPx(12), '0.8rem');
  assert.equal(remFromPx(16), '1.067rem');
  assert.equal(remFromPx(20), '1.333rem');
  assert.equal(remFromPx(32), '2.133rem');
});

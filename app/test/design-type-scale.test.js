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

test('type scale: every font size in the stylesheets names one of the five styles (no literal rem)', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  // The scale owns the sizes in tokens.css (the --type-* custom
  // properties are the five named styles: Title, Heading, Body, Label,
  // Figure). Component styles must reference a named style, never
  // hardcode a rem size — otherwise the scale has a sixth, unnamed
  // step that nothing documents (Batch 6 design audit, finding 11 #3).
  const stylesDir = path.join(__dirname, '..', 'renderer', 'styles');
  const hits = [];
  for (const file of fs.readdirSync(stylesDir).filter((f) => f.endsWith('.css')).sort()) {
    fs.readFileSync(path.join(stylesDir, file), 'utf8').split('\n').forEach((line, i) => {
      if (/font-size:\s*\d+(?:\.\d+)?rem/.test(line)) hits.push(`${file}:${i + 1}: ${line.trim()}`);
    });
  }
  assert.deepEqual(
    hits,
    [],
    `literal rem font sizes must be replaced with --type-* variables:\n${hits.join('\n')}`,
  );
});

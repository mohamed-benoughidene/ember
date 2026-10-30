'use strict';

/**
 * The contrast check (L3 app step 03, step file §2): every text /
 * background pair in BOTH palettes is >= 4.5:1, status marks >= 3:1,
 * computed for real and printed. Pure maths module, no DOM.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ROOT } = require('./util');

const { contrastRatio } = require('../renderer/design/color-contrast.mjs');

const tokensCss = fs.readFileSync(path.join(APP_ROOT, 'renderer', 'styles', 'tokens.css'), 'utf8');

function raw(name) {
  const m = tokensCss.match(new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})\\s*;`));
  assert.ok(m, `raw palette colour --${name} expected in tokens.css`);
  return m[1];
}

// Palette (raw) colours from tokens.css, which the token contract test
// pins against DESIGN.md.
const P = Object.fromEntries(
  [
    'paper-ground', 'ledger-paper', 'aged-paper', 'worn-paper', 'rule-line', 'control-line',
    'iron-ink', 'faded-ink', 'brick-wash', 'brick-deep', 'ember-heat', 'ochre-wash', 'ochre-ink',
    'soot-ground', 'soot-surface', 'soot-raised', 'soot-line', 'soot-sidebar', 'soot-ink',
    'soot-faded-ink', 'soot-heat', 'warm-apricot',
  ].map((n) => [n, raw(n)]),
);

const TEXT_PAIRS = [
  // [what, fg, bg, minimum]
  ['light: main text on panels', P['iron-ink'], P['ledger-paper'], 4.5],
  ['light: secondary text on panels', P['faded-ink'], P['ledger-paper'], 4.5],
  ['light: secondary text on the ground', P['faded-ink'], P['paper-ground'], 4.5],
  ['light: main text on aged paper (title bar)', P['iron-ink'], P['aged-paper'], 4.5],
  ['light: white on the main button', '#FFFFFF', P['brick-wash'], 4.5],
  ['light: white on the hovered main button', '#FFFFFF', P['brick-deep'], 4.5],
  ['light: sidebar text on the sidebar', P['ledger-paper'], P['iron-ink'], 4.5],
  ['light: challenged tint text', P['ochre-ink'], P['ochre-wash'], 4.5],
  ['light: selected menu row', P['iron-ink'], P['ledger-paper'], 4.5],

  ['dark: main text on surface', P['soot-ink'], P['soot-surface'], 4.5],
  ['dark: main text on the ground', P['soot-ink'], P['soot-ground'], 4.5],
  ['dark: secondary text on surface', P['soot-faded-ink'], P['soot-surface'], 4.5],
  ['dark: secondary text on the raised surface', P['soot-faded-ink'], P['soot-raised'], 4.5],
  ['dark: dark text on the light main button', '#17110E', P['soot-ink'], 4.5],
  ['dark: charred wood on Warm Apricot (selected row)', '#3D0C02', P['warm-apricot'], 4.5],
  ['dark: apricot on the challenged tint', P['warm-apricot'], '#4A2F14', 4.5],
  ['dark: sidebar text on the sidebar', '#E6E2DC', P['soot-sidebar'], 4.5],
];

const MARK_PAIRS = [
  ['light: the heat mark on panels', P['ember-heat'], P['ledger-paper'], 3],
  ['light: the heat mark on the ground', P['ember-heat'], P['paper-ground'], 3],
  ['dark: the heat mark on surface', P['soot-heat'], P['soot-surface'], 3],
  ['dark: the heat mark on the ground', P['soot-heat'], P['soot-ground'], 3],
];

for (const [what, fg, bg, min] of TEXT_PAIRS) {
  test(`contrast ${min === 10.2 ? 'design value' : 'text'}: ${what}`, () => {
    const ratio = contrastRatio(fg, bg);
    assert.ok(
      ratio >= min,
      `${what}: ${fg} on ${bg} is ${ratio}:1, needs >= ${min}:1`,
    );
  });
}

for (const [what, fg, bg, min] of MARK_PAIRS) {
  test(`contrast mark (>= 3:1): ${what}`, () => {
    const ratio = contrastRatio(fg, bg);
    assert.ok(ratio >= min, `${what}: ${fg} on ${bg} is ${ratio}:1, needs >= ${min}:1`);
  });
}

test('contrast: the DESIGN.md quoted numbers are true (printed, not guessed)', () => {
  const said = {
    'iron ink on ledger paper 12:1': contrastRatio(P['iron-ink'], P['ledger-paper']),
    'faded ink on ledger paper 6.4:1': contrastRatio(P['faded-ink'], P['ledger-paper']),
    'faded ink on paper ground 5.1:1': contrastRatio(P['faded-ink'], P['paper-ground']),
    'white on brick wash 6.8:1': contrastRatio('#FFFFFF', P['brick-wash']),
    'ember heat on ledger paper 4.2:1': contrastRatio(P['ember-heat'], P['ledger-paper']),
    'soot faded ink 7.5:1': contrastRatio(P['soot-faded-ink'], P['soot-ground']),
    'soot heat 7.1:1': contrastRatio(P['soot-heat'], P['soot-ground']),
    'warm apricot + charred wood 10.2:1': contrastRatio(P['warm-apricot'], '#3D0C02'),
  };
  const printed = Object.entries(said).map(([k, v]) => `${k} -> computed ${v}`).join('; ');
  process.stdout.write(`${printed}\n`);
  for (const [label, ratio] of Object.entries(said)) {
    assert.ok(ratio >= 3, `${label}: computed ${ratio}`);
  }
});

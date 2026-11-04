'use strict';

/**
 * The token contract (L3 app step 03, step file §2): every token
 * docs/DESIGN.md defines exists in app/renderer/styles/tokens.css with
 * the exact value, and no token exists WITHOUT a DESIGN.md/prototype
 * source (no orphans, no invention). Pure file parsing, no Electron.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ROOT, REPO_ROOT } = require('./util');

const DESIGN_MD = path.join(REPO_ROOT, 'docs', 'DESIGN.md');
const TOKENS_CSS = path.join(APP_ROOT, 'renderer', 'styles', 'tokens.css');

const design = fs.readFileSync(DESIGN_MD, 'utf8');
const frontMatter = design.match(/^---\n([\s\S]*?)\n---/)[1];
const tokensCss = fs.readFileSync(TOKENS_CSS, 'utf8');

/** name -> hex for every colour in the DESIGN.md front matter. */
function designPalette() {
  const map = {};
  for (const m of frontMatter.matchAll(/^ {2}([a-z0-9-]+): "(#[0-9A-Fa-f]{6})"$/gm)) {
    map[m[1]] = m[2].toUpperCase();
  }
  return map;
}

/** name -> declarations from tokens.css (all `--x: value;` lines). */
function cssVars() {
  const map = {};
  for (const m of tokensCss.matchAll(/^\s*(--[a-z0-9-]+):\s*([^;]+);\s*(?:\/\*.*\*\/)?$/gm)) {
    map[m[1]] = m[2].trim();
  }
  return map;
}

test('token contract: every DESIGN.md colour exists in tokens.css, exact hex', () => {
  const palette = designPalette();
  const vars = cssVars();
  assert.equal(Object.keys(palette).length, 22, `expected 22 DESIGN.md colours, parsed ${JSON.stringify(palette)}`);
  for (const [name, hex] of Object.entries(palette)) {
    assert.equal(vars[`--${name}`]?.toUpperCase(), hex, `token --${name} must be ${hex}`);
  }
});

test('token contract: the seven spacing steps match the DESIGN.md px table', () => {
  const vars = cssVars();
  // DESIGN.md Spacing table: step -> px at the Default 15px root.
  const pxByStep = { 1: 4, 2: 6, 3: 8, 4: 12, 5: 16, 6: 20, 7: 32 };
  for (const [step, px] of Object.entries(pxByStep)) {
    const rem = vars[`--s${step}`];
    assert.match(rem ?? '', /rem$/, `--s${step} must be in rem (spacing scales with text size)`);
    const computed = Number(rem.replace(/rem$/, '')) * 15;
    assert.equal(Math.round(computed), px, `--s${step} = ${rem} should be ${px}px at Default`);
  }
  assert.equal(Object.keys(vars).filter((v) => /^--s\d$/.test(v)).length, 7, 'exactly seven spacing steps (DESIGN.md rule 2)');
});

test('token contract: the one radius is 6px (DESIGN.md rounded.control)', () => {
  const control = frontMatter.match(/^  control: "([0-9]+px)"$/m);
  const vars = cssVars();
  assert.equal(vars['--radius'], control[1]);
});

test('token contract: the type scale matches the DESIGN.md typography', () => {
  const want = {};
  for (const m of frontMatter.matchAll(/^ {2}(title|heading|body|label|figure):\n((?: {4}[a-zA-Z]+: .*\n)+)/gm)) {
    want[m[1]] = Object.fromEntries(
      [...m[2].matchAll(/ {4}([a-zA-Z]+): (.+)/g)].map(([_, k, v]) => [k, v.replace(/"/g, '').trim()]),
    );
  }
  assert.deepEqual(Object.keys(want).sort(), ['body', 'figure', 'heading', 'label', 'title']);
  const vars = cssVars();
  for (const [style, fields] of Object.entries(want)) {
    assert.equal(vars[`--type-${style}-size`], fields.fontSize, `${style} size`);
    assert.equal(vars[`--type-${style}-weight`], fields.fontWeight, `${style} weight`);
    assert.equal(vars[`--type-${style}-lh`], fields.lineHeight, `${style} line-height`);
    if (fields.letterSpacing) {
      assert.equal(vars[`--type-${style}-ls`], fields.letterSpacing, `${style} letter-spacing`);
    }
  }
  // families: Atkinson first, with the DESIGN.md fallbacks
  assert.match(vars['--font-body'], /^'Atkinson Hyperlegible Next',/);
  assert.match(vars['--font-mono'], /^'Atkinson Hyperlegible Mono',/);
});

test('token contract: the five text-size steps, Largest = 200% of Default', () => {
  const prose = design.match(/Small (\d+)px, Default (\d+)px, Large (\d+)px, Larger (\d+)px, Largest (\d+)px/);
  assert.ok(prose, 'the Text Size Rule prose');
  const [, small, def, large, larger, largest] = prose.map(Number);
  const vars = cssVars();
  assert.equal(vars['--text-small'], `${small}px`);
  assert.equal(vars['--text-default'], `${def}px`);
  assert.equal(vars['--text-large'], `${large}px`);
  assert.equal(vars['--text-larger'], `${larger}px`);
  assert.equal(vars['--text-largest'], `${largest}px`);
  assert.equal(largest, def * 2, 'Largest is 200% of Default (DESIGN.md Text Size Rule)');
});

test('token contract: no orphan tokens and no invented hex values', () => {
  const palette = designPalette();
  const vars = cssVars();
  const declared = [...tokensCss.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]);

  const paletteVars = new Set(Object.keys(palette).map((n) => `--${n}`));
  const roleVars = new Set([
    // the role layer: which palette colour plays each job per theme;
    // names and light values follow the approved prototype.
    '--ground', '--surface', '--surface-2', '--surface-3', '--line', '--line-strong',
    '--ink', '--ink-2', '--heat', '--accent', '--accent-hover', '--accent-ink',
    '--focus', '--danger', '--sel-bg', '--sel-ink', '--warn-bg', '--warn-ink',
    '--nav-bg', '--nav-ink', '--banner-bg', '--banner-ink',
  ]);
  const scaleVars = new Set([
    '--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--radius',
    '--font-body', '--font-mono',
    '--type-title-size', '--type-title-weight', '--type-title-lh', '--type-title-ls',
    '--type-heading-size', '--type-heading-weight', '--type-heading-lh',
    '--type-body-size', '--type-body-weight', '--type-body-lh',
    '--type-label-size', '--type-label-weight', '--type-label-lh',
    '--type-figure-size', '--type-figure-weight', '--type-figure-lh',
    '--text-small', '--text-default', '--text-large', '--text-larger', '--text-largest',
  ]);

  const allowed = new Set([...paletteVars, ...roleVars, ...scaleVars]);
  const orphans = declared.filter((v) => !allowed.has(v));
  assert.deepEqual(orphans, [], `tokens without a contract source: ${orphans.join(', ')}`);
  for (const name of allowed) {
    assert.ok(declared.includes(name), `allowed token ${name} must actually be declared in tokens.css`);
  }

  // hex values: only DESIGN.md palette colours, the button white, and the
  // six dark-role values the approved prototype carries.
  const prototypeDark = new Set(['#342A24', '#5C4E44', '#E6E2DC', '#17110E', '#3D0C02', '#4A2F14']);
  const allowedHexes = new Set([...Object.values(palette), '#FFFFFF', ...prototypeDark]);
  const hexes = [...tokensCss.matchAll(/#([0-9A-Fa-f]{6})\b/g)].map((m) => m[0].toUpperCase());
  const invented = [];
  for (const hex of hexes) {
    if (!allowedHexes.has(hex)) invented.push(hex);
  }
  assert.deepEqual(invented, [], `hex values not in DESIGN.md or the approved prototype: ${invented.join(', ')}`);
});

test('token contract: CSS file is plain CSS (no preprocessors, no frameworks)', () => {
  const stylesDir = path.join(APP_ROOT, 'renderer', 'styles');
  const files = fs.readdirSync(stylesDir);
  for (const f of files) {
    assert.match(f, /\.css$/, `styles/ holds plain css files only, saw ${f}`);
    const body = fs.readFileSync(path.join(stylesDir, f), 'utf8');
    assert.doesNotMatch(body, /@import\s+url\(\s*['"]?https?:/, 'no remote css imports');
  }
  assert.ok(files.includes('tokens.css') && files.includes('fonts.css') && files.includes('components.css'));
});

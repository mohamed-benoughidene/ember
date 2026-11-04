'use strict';

/**
 * Fonts and licence (L3 app step 03, step file §1 + story 108): the
 * Atkinson Hyperlegible files are self-hosted in app/assets/fonts/, the
 * SIL OFL 1.1 licence text and copyright notice sit NEXT to them (the
 * licence requires each copy to carry both), and no @font-face points
 * anywhere but these files. Hashes are pinned so a silent deletion or
 * swap fails the suite.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { APP_ROOT } = require('./util');

const FONTS = path.join(APP_ROOT, 'assets', 'fonts');
const FONTS_CSS = path.join(APP_ROOT, 'renderer', 'styles', 'fonts.css');
const STYLES = path.join(APP_ROOT, 'renderer', 'styles');

const FONT_FILES = {
  'atkinson-hyperlegible-next-latin-400-normal.woff2':
    '5cb240a4d99ab7e6fc3a4d4e6d11d89789fdffe9c86a8384000d662c53283f6f',
  'atkinson-hyperlegible-next-latin-500-normal.woff2':
    'f5243b80fbcabc6756a4f67a2843a581216ecb89019a789335b85c924f05702e',
  'atkinson-hyperlegible-next-latin-600-normal.woff2':
    '828f4525c741b6864718e41aa23a4acbc049b35e6271317c0fd86e0702dd5d2e',
  'atkinson-hyperlegible-mono-latin-400-normal.woff2':
    '87b5b94c18025729fc6ed4e8c25221ade3746dc87213943fa4de49f1f0f26787',
  'atkinson-hyperlegible-mono-latin-600-normal.woff2':
    'a52c1396b3cc1b7c7e52dcb39ed9ed2aeb1b7b0ff3572bca076e441aa7d906f6',
};

const LICENCE_FILES = {
  'atkinson-hyperlegible-next-OFL.txt':
    '474a034e99845062f661855caaa505880d0e9009deddc2727a92795eab374955',
  'atkinson-hyperlegible-mono-OFL.txt':
    '05327050630a640eb824c8fcb7de8b2e605600d8863e4f531ca7c348239916c6',
};

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

test('fonts: the five pinned files exist, byte for byte', () => {
  for (const [name, hash] of Object.entries(FONT_FILES)) {
    const file = path.join(FONTS, name);
    assert.ok(fs.existsSync(file), `${name} must exist (fonts are committed, never fetched at build time)`);
    assert.equal(sha256(file), hash, `${name} changed on disk`);
    const head = fs.readFileSync(file).subarray(0, 4).toString('latin1');
    assert.equal(head, 'wOF2', `${name} is not a woff2 file`);
  }
});

test('licence: the OFL texts ship next to the fonts and are the real ones', () => {
  for (const [name, hash] of Object.entries(LICENCE_FILES)) {
    const file = path.join(FONTS, name);
    assert.ok(fs.existsSync(file), `${name} must ship with the fonts (OFL requirement, story 108)`);
    assert.equal(sha256(file), hash, `${name} changed on disk`);
    const text = fs.readFileSync(file, 'utf8');
    assert.match(text, /SIL OPEN FONT LICENSE Version 1\.1/, 'the OFL 1.1 text');
    assert.match(text, /Copyright 2020-2024 The Atkinson Hyperlegible/, 'the copyright notice');
    assert.match(text, /http:\/\/scripts\.sil\.org\/OFL/, 'the OFL FAQ pointer');
  }
});

test('fonts: exactly the shipped files are referenced, and only from this folder', () => {
  const css = fs.readFileSync(FONTS_CSS, 'utf8');
  const referenced = [...css.matchAll(/url\(([^)]+)\)/g)].map((m) => path.basename(m[1].replace(/['"]/g, '')));
  assert.deepEqual(referenced.sort(), Object.keys(FONT_FILES).sort(), 'fonts.css references exactly the five committed files');

  assert.ok(!/https?:\/\//.test(css), 'no remote URLs in fonts.css (no font CDN, story 107)');
  for (const m of css.matchAll(/url\(([^)]+)\)/g)) {
    assert.match(m[1], /\.\.\/\.\.\/assets\/fonts\//, 'every src points into app/assets/fonts');
  }
  // weights: 400/500/600 Next (DESIGN.md), 400/600 Mono, per the approved prototype
  const faces = [...css.matchAll(/font-family: '([^']+)';[\s\S]*?font-weight: (\d+)/g)];
  const pairs = faces.map(([, family, weight]) => `${family}:${weight}`).sort();
  assert.deepEqual(pairs, [
    'Atkinson Hyperlegible Mono:400',
    'Atkinson Hyperlegible Mono:600',
    'Atkinson Hyperlegible Next:400',
    'Atkinson Hyperlegible Next:500',
    'Atkinson Hyperlegible Next:600',
  ]);
});

test('fonts: latin subset is the shipped default, named as such', () => {
  for (const name of Object.keys(FONT_FILES)) {
    assert.match(name, /-latin-/, 'file names carry the subset, so the limit is visible');
  }
});

test('fonts: no other window CSS fetches a font outside fonts.css', () => {
  for (const f of fs.readdirSync(STYLES).filter((x) => x.endsWith('.css') && x !== 'fonts.css')) {
    const body = fs.readFileSync(path.join(STYLES, f), 'utf8');
    assert.ok(!/@font-face/.test(body), `${f} carries no @font-face (all of them live in fonts.css)`);
    assert.ok(!/url\(.*(woff|ttf|otf)/.test(body), `${f} loads no font file`);
  }
});

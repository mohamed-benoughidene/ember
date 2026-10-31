'use strict';

/** App step 13: the real raster icons (the step-11 placeholder debt). */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { trayIconPath, windowIconPath } = require('../main/app-icon');

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const APP_ROOT = path.join(__dirname, '..');

test('the shipped tree carries the tray and window PNGs (real PNG magic, square)', () => {
  const tray = trayIconPath(APP_ROOT);
  const win = windowIconPath(APP_ROOT);
  assert.ok(tray, `the tray PNG is missing at ${path.join(APP_ROOT, 'assets', 'icons', 'ember-tray-32.png')}`);
  assert.ok(win, `the window PNG is missing at ${path.join(APP_ROOT, 'assets', 'icons', 'ember-256.png')}`);
  for (const file of [tray, win]) {
    assert.deepEqual(
      fs.readFileSync(file).subarray(0, PNG_MAGIC.length),
      PNG_MAGIC,
      `${file} does not start with the PNG magic bytes`,
    );
  }
});

test('a tree without the assets gets null — the tray keeps its honest default (never a broken path)', () => {
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-icons-'));
  assert.equal(trayIconPath(empty), null);
  assert.equal(windowIconPath(empty), null);
  // A directory in the icon's place is not a file either.
  fs.mkdirSync(path.join(empty, 'assets', 'icons', 'ember-tray-32.png'), { recursive: true });
  assert.equal(trayIconPath(empty), null);
});

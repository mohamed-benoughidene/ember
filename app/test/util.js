'use strict';

/** Small shared helpers for the app's node tests. */

const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');
const REPO_ROOT = path.join(APP_ROOT, '..');
const FAKE_EMBER = path.join(__dirname, 'fake-ember.js');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python');

/** The shared error-line regex fixture (read by the Python tests too). */
function errorPatternFixture() {
  const fs = require('node:fs');
  return fs
    .readFileSync(path.join(REPO_ROOT, 'tests', 'fixtures', 'bridge', 'error_parsing_rule.txt'), 'utf8')
    .trim();
}

module.exports = { APP_ROOT, REPO_ROOT, FAKE_EMBER, PYTHON, errorPatternFixture };

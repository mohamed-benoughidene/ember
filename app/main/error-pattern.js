'use strict';

/**
 * Loads the shared error-line regex from the ONE fixture file the
 * Python contract test also reads (bridge L2 §5.2): 
 * `tests/fixtures/bridge/error_parsing_rule.txt`. This is an edge
 * module (T2: file reads live here); it resolves the fixture relative
 * to the app folder. Re-run before every spawn (cheap), so a moved
 * checkout still works.
 */

const fs = require('node:fs');
const path = require('node:path');

/** The fixture, relative to the app/ root (the repo's root is one up). */
const FIXTURE_RELATIVE = ['..', 'tests', 'fixtures', 'bridge', 'error_parsing_rule.txt'];

/**
 * @param {string} [appDir] the app/ directory (default: derived)
 * @returns {string|null} the pattern source, or null when the fixture
 *   is not reachable (packaged builds; the client then treats every
 *   unmatched error line as APP-002 rather than guessing).
 */
function loadErrorPattern(appDir = path.join(__dirname, '..')) {
  const file = path.join(appDir, ...FIXTURE_RELATIVE);
  if (!fs.existsSync(file)) return null;
  const raw = fs.readFileSync(file, 'utf8').trim();
  return raw === '' ? null : raw;
}

module.exports = { loadErrorPattern, FIXTURE_RELATIVE };

'use strict';

/**
 * The error-line parser (bridge L2 §5.2, shared with the Python suite).
 *
 * The regular expression lives in ONE file, `tests/fixtures/bridge/
 * error_parsing_rule.txt`, which the Python contract test and the app
 * tests both read, so the two sides cannot drift. The PATTERN itself
 * is NOT copied here on purpose — the caller loads it with
 * `loadErrorPattern()` (an edge: reading a file) in main/ and passes
 * the string in. Keep this module pure (T1).
 */

/**
 * The pinned regex (bridge plan §5.2). This constant is the fallback
 * used only by pure unit tests; production loads the shared fixture
 * (see main/error-pattern.js) and tests assert the fallback equals the
 * fixture, so a copy here still cannot drift unnoticed.
 */
const PATTERN_FALLBACK =
  '\\Aerror: (?P<code>[A-Z]+-\\d{3}) (?P<name>\\w+) \\| (?P<where>[^|\\n]+) \\| (?P<rest>.*)\\Z';

/**
 * Parse ONE house error line into its named parts.
 *
 * `rest` swallows everything to the end including `|` and newlines
 * (the pattern is compiled with `re.S`-equivalent: the JS `s` flag),
 * and later stderr lines are appended as detail continuation.
 *
 * @param {string} firstLine the first stderr line
 * @param {string} pattern the pattern source (from the shared fixture)
 * @param {string[]} [continuationLines] further stderr lines, joined into detail
 * @returns {{code: string, name: string, where: string, detail: string} | null}
 *   null when the line does not match the house shape.
 */
function parseErrorLine(firstLine, pattern, continuationLines = []) {
  if (typeof firstLine !== 'string') return null;
  // JS has no lookbehind-free equivalent of Python's \A/\Z; anchor by
  // hand: the whole line must start with "error: " and the rest run to
  // the end allowing embedded newlines (the `s` flag, like re.S).
  let source = pattern.replace(/\\A/g, '^').replace(/\\Z/g, '$').replace(/\(\?P</g, '(?<');
  let re;
  try {
    re = new RegExp(source, 's');
  } catch {
    return null;
  }
  const match = re.exec(firstLine);
  if (!match || !match.groups) return null;
  const continuation = continuationLines.join('\n');
  const detail = continuation ? `${match.groups.rest}\n${continuation}` : match.groups.rest;
  return {
    code: match.groups.code,
    name: match.groups.name,
    where: match.groups.where,
    detail,
  };
}

module.exports = { PATTERN_FALLBACK, parseErrorLine };

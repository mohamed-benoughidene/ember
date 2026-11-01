'use strict';

/**
 * The ONE id check the argv builders share (fix C5): a whole number
 * from 1 up. `what` names the flag in the refusal, so both the Link
 * items builder (`--item`) and the Fix-and-close builders report the
 * same honest words. Pure (T1); unit-tested in relate-args.test.js.
 */

/**
 * @param {unknown} value the raw id the renderer sent
 * @param {string} what the flag name for the refusal message
 * @returns {number}
 * @throws {TypeError} when the value is not a whole number from 1 up
 */
function requireId(value, what) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) {
    throw new TypeError(`${what} must be a whole number from 1 up, got ${String(value)}`);
  }
  return n;
}

module.exports = { requireId };

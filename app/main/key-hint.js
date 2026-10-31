'use strict';

/**
 * The masked key hint (app step 10, the AI connection pane, story 89;
 * the approved prototype's "Key ends in 3f9a").
 *
 * The ONLY form in which a stored key may be shown again after it is
 * saved: its last four characters, so the user can tell WHICH key is
 * saved without any pane ever echoing the whole key. The full key
 * itself leaves the main process only as the bridge child's
 * EMBER_AI_API_KEY (never a log, an error, the settings file or the
 * ledger; plan §5.4, I20/I21).
 *
 * Plain CommonJS (the main process's module world). Pure (T1).
 */

/**
 * @param {string|null} key the full key, as the key store holds it
 * @returns {string|null} e.g. "3f9a"; null when there is no key
 */
function maskKey(key) {
  if (typeof key !== 'string' || key.length < 4) return null;
  return key.slice(-4);
}

module.exports = { maskKey };

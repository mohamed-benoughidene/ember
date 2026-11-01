/**
 * The key shape rule (app plan §3 decision 5 = A, bridge D3): Ember does
 * NOT call the AI service to test a key — there is no `check-key`
 * command. At save time the app checks the key's SHAPE and LENGTH only;
 * the real test happens at the first Add, where a refused key shows a
 * plain "key refused" message (stories 5 and 8 are PARTIAL by design,
 * signed off by the maintainer).
 *
 * The rule lives here ONCE so the screen's instant message and the
 * main-process backstop at `ember:setKey` cannot drift. Pure module (T1).
 */

export const MIN_KEY_LENGTH = 20;

/**
 * The ONE reason words for a refused key shape, shared by both layers
 * (fix C5, founder decision: the settings pane's sentences are THE
 * wording — the main-process backstop re-uses exactly these, and the
 * drift test in settings-screen.test.js pins both layers to this one
 * function). Always a full stand-alone sentence, never a secret.
 *
 * @param {'empty'|'whitespace'|'short'} reason
 * @returns {string}
 */
export function keyShapeWords(reason) {
  if (reason === 'empty') return 'The key box is empty. Paste your key, then save it.';
  if (reason === 'whitespace') return 'A key is one unbroken line of characters. This one has a space or a line break inside; copy it again completely.';
  return 'This key is too short. A real key has at least 20 characters with no spaces; copy it again completely.';
}

/**
 * @param {unknown} key the pasted key text
 * @returns {{ok: true} | {ok: false, reason: 'empty'|'whitespace'|'short'}}
 */
export function checkKeyShape(key) {
  if (typeof key !== 'string' || key.trim() === '') return { ok: false, reason: 'empty' };
  const trimmed = key.trim();
  if (/\s/.test(trimmed)) return { ok: false, reason: 'whitespace' };
  if (trimmed.length < MIN_KEY_LENGTH) return { ok: false, reason: 'short' };
  return { ok: true };
}

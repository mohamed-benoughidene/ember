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

'use strict';

/**
 * The event-line parser for `--confirm json` sessions (bridge L2 §5.4).
 *
 * Every stdout line of a confirm session is UNTRUSTED (D4): it must be
 * exactly one JSON object with an `event` field naming one of the four
 * known events. Anything else raises APP-002 (garbage never reaches
 * the renderer).
 */

const EVENT_NAMES = Object.freeze(['block', 'prompt', 'message', 'summary']);

/**
 * Parse one stdout line of a confirm session.
 *
 * @param {string} line one raw stdout line (no trailing newline)
 * @returns {{ok: true, event: {event: string, [k: string]: unknown}} |
 *           {ok: false, error: {code: 'APP-002', name: string, where: string, detail: string}}}
 */
function parseEventLine(line) {
  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch {
    return {
      ok: false,
      error: {
        code: 'APP-002',
        name: 'BridgeOutputInvalid',
        where: 'shared.parseEventLine',
        detail: 'a confirm-session line was not JSON',
      },
    };
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return {
      ok: false,
      error: {
        code: 'APP-002',
        name: 'BridgeOutputInvalid',
        where: 'shared.parseEventLine',
        detail: 'a confirm-session line was not a JSON object',
      },
    };
  }
  if (typeof parsed.event !== 'string' || !EVENT_NAMES.includes(parsed.event)) {
    return {
      ok: false,
      error: {
        code: 'APP-002',
        name: 'BridgeOutputInvalid',
        where: 'shared.parseEventLine',
        detail: 'a confirm-session line named an unknown event',
      },
    };
  }
  return { ok: true, event: parsed };
}

/**
 * The answer line the app writes to a confirm session's stdin.
 * The text is the only free value; it is JSON-encoded once, here.
 *
 * @param {string} text the answer ('y', 'n', 's', 'q', or edit text)
 * @returns {string | null} one stdin line, or null for a non-string
 */
function answerLine(text) {
  if (typeof text !== 'string') return null;
  return JSON.stringify({ answer: text }) + '\n';
}

module.exports = { EVENT_NAMES, parseEventLine, answerLine };

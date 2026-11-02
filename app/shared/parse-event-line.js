'use strict';

/**
 * The event-line parser for `--confirm json` sessions (bridge L2 §5.4).
 *
 * Every stdout line of a confirm session is UNTRUSTED (D4): it must be
 * exactly one JSON object with an `event` field naming one of the four
 * known events, and it must carry the event's required fields with the
 * right types (4.4 #7 masking, 4.4 #8: "Each event type has a field
 * schema. A missing or wrong field is APP-002 with details"). Anything
 * else raises APP-002 — garbage and half-shaped events never reach the
 * renderer.
 *
 * The per-event field schema lives in the ONE file both sides read,
 * `tests/fixtures/bridge/event_schema.json` (the engine's real events are
 * pinned against it by tests/bridge/test_event_schema.py). The frozen
 * table below mirrors it; the app test pins the equality so neither side
 * can drift. Unknown extra keys are allowed (the engine may add fields);
 * every key the table lists is checked whenever it is present.
 */

const EVENT_NAMES = Object.freeze(['block', 'prompt', 'message', 'summary']);

/** The allowed value types, one predicate per fixture type name. */
const TYPE_TESTS = Object.freeze({
  string: (v) => typeof v === 'string',
  number: (v) => typeof v === 'number',
  boolean: (v) => typeof v === 'boolean',
  array: (v) => Array.isArray(v),
  object: (v) => typeof v === 'object' && v !== null && !Array.isArray(v),
  null: (v) => v === null,
});

/**
 * Mirrors tests/fixtures/bridge/event_schema.json (the event-line test
 * pins this equality; change BOTH together).
 */
const EVENT_FIELD_SCHEMAS = Object.freeze({
  block: Object.freeze({
    required: Object.freeze({
      event: Object.freeze(['string']),
      kind: Object.freeze(['string']),
      fields: Object.freeze(['object', 'null']),
      text: Object.freeze(['string']),
    }),
    optional: Object.freeze({}),
  }),
  prompt: Object.freeze({
    required: Object.freeze({
      event: Object.freeze(['string']),
      kind: Object.freeze(['string']),
      text: Object.freeze(['string']),
      choices: Object.freeze(['array']),
    }),
    optional: Object.freeze({}),
  }),
  message: Object.freeze({
    required: Object.freeze({
      event: Object.freeze(['string']),
      text: Object.freeze(['string']),
    }),
    optional: Object.freeze({}),
  }),
  summary: Object.freeze({
    required: Object.freeze({
      event: Object.freeze(['string']),
      accepted: Object.freeze(['number']),
      rejected: Object.freeze(['number']),
      aborted: Object.freeze(['boolean']),
    }),
    optional: Object.freeze({
      warnings: Object.freeze(['number']),
      skipped: Object.freeze(['number']),
      stale: Object.freeze(['number']),
      proposed: Object.freeze(['number']),
    }),
  }),
});

function fieldError(detail) {
  return {
    code: 'APP-002',
    name: 'BridgeOutputInvalid',
    where: 'shared.parseEventLine',
    detail,
  };
}

/**
 * A valid-`event` object must satisfy its fixture entry: every required
 * field present, every listed field that is present well typed.
 *
 * @returns {null | {code: 'APP-002', detail: string, ...}} null when OK
 */
function checkEventFields(event) {
  const schema = EVENT_FIELD_SCHEMAS[event.event];
  if (!schema) return null; // unknown names are refused before this runs
  for (const key of Object.keys(schema.required)) {
    if (!(key in event)) {
      return fieldError(
        `a ${event.event} event is missing its required field "${key}"`,
      );
    }
  }
  const checked = { ...schema.required, ...schema.optional };
  for (const [key, types] of Object.entries(checked)) {
    if (key in event && !types.some((t) => TYPE_TESTS[t](event[key]))) {
      return fieldError(
        `the field "${key}" of a ${event.event} event has a value of the` +
          ` wrong type (expected ${types.join(' or ')})`,
      );
    }
  }
  return null;
}

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
  const fieldProblem = checkEventFields(parsed);
  if (fieldProblem) return { ok: false, error: fieldProblem };
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

module.exports = { EVENT_NAMES, EVENT_FIELD_SCHEMAS, parseEventLine, answerLine };

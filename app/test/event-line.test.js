'use strict';

/** The event-line parser table (step file §2): garbage lines -> APP-002. */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  EVENT_NAMES,
  EVENT_FIELD_SCHEMAS,
  parseEventLine,
  answerLine,
} = require('../shared/parse-event-line');

test('the four pinned event names', () => {
  assert.deepEqual([...EVENT_NAMES], ['block', 'prompt', 'message', 'summary']);
});

test('one valid event of each kind parses whole', () => {
  const cases = [
    '{"event":"block","kind":"item","fields":{"id":1},"text":"- id: 1"}',
    '{"event":"prompt","kind":"choice","text":"[y]es / [n]o / [q]uit","choices":["y","n","q"]}',
    '{"event":"message","text":"dropped proposal: does not quote the source"}',
    '{"event":"summary","line":"accepted: 1, rejected: 0","accepted":1,"rejected":0,"skipped":0,"aborted":false}',
  ];
  for (const line of cases) {
    const result = parseEventLine(line);
    assert.equal(result.ok, true, line);
    assert.equal(typeof result.event.event, 'string');
  }
});

test('field values may contain anything as long as the line is JSON', () => {
  const line = '{"event":"message","text":"quotes: \\": \\" and | and \\n stay inside"}';
  const result = parseEventLine(line);
  assert.equal(result.ok, true);
  assert.equal(result.event.text, 'quotes: ": " and | and \n stay inside');
});

const BAD_LINES = [
  ['not json at all', 'not JSON'],
  ['', 'not JSON'],
  ['["event","message"]', 'not a JSON object'],
  ['42', 'not a JSON object'],
  ['null', 'not a JSON object'],
  ['{"nosevent":1}', 'unknown event'],
  ['{"event":"bogus"}', 'unknown event'],
];

for (const [line, why] of BAD_LINES) {
  test(`garbage line refused as APP-002 (${why})`, () => {
    const result = parseEventLine(line);
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-002');
    assert.equal(result.error.name, 'BridgeOutputInvalid');
    assert.equal(typeof result.error.detail, 'string');
  });
}

test('answerLine writes exactly {"answer": <text>} on one line', () => {
  assert.equal(answerLine('y'), '{"answer":"y"}\n');
  const long = answerLine('a statement with "quotes" and\nnewline');
  assert.deepEqual(JSON.parse(long), { answer: 'a statement with "quotes" and\nnewline' });
  assert.ok(long.endsWith('\n') && long.indexOf('\n') === long.length - 1, 'exactly one line');
});

test('answerLine refuses non-strings (D4: the child never sees junk)', () => {
  assert.equal(answerLine(42), null);
  assert.equal(answerLine(null), null);
  assert.equal(answerLine({ answer: 'y' }), null);
});

// --- the shared event-schema fixture (4.4 #7: masking, 4.4 #8) ----------------

// ONE fixture file both sides read (cross-boundary refs resolve from the
// repo root, like util.js's error-pattern fixture). The engine's pytest
// (tests/bridge/test_event_schema.py) pins the real events against it.
const SCHEMA_FIXTURE = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, '..', '..', 'tests', 'fixtures', 'bridge', 'event_schema.json'),
    'utf8',
  ),
);
const SCHEMA_NAMES = Object.keys(SCHEMA_FIXTURE).filter((k) => !k.startsWith('$'));

/** One sample value for the FIRST allowed type of a schema entry. */
function sample(types) {
  const byType = { string: 'x', number: 1, boolean: true, array: [], object: {}, null: null };
  return byType[types[0]];
}

/** One value whose type is NOT in the allowed list. */
function wrongValue(types) {
  const byType = { string: 'oops', number: 42, boolean: true, array: [], object: {}, null: null };
  const badType = ['string', 'number', 'boolean', 'array', 'object', 'null'].find((t) => !types.includes(t));
  return byType[badType];
}

/** One well-formed event for `name`, optional keys only when asked. */
function buildEvent(name, withOptional) {
  const entry = SCHEMA_FIXTURE[name];
  const event = { event: name };
  for (const [key, types] of Object.entries(entry.required)) {
    if (key !== 'event') event[key] = sample(types);
  }
  if (withOptional) {
    for (const [key, types] of Object.entries(entry.optional)) event[key] = sample(types);
  }
  return event;
}

test('the fixture pins exactly the four event names the parser knows', () => {
  assert.deepEqual([...SCHEMA_NAMES].sort(), [...EVENT_NAMES].sort());
});

test('the parser field table equals the shared fixture (no drift, either side)', () => {
  assert.deepEqual(EVENT_FIELD_SCHEMAS, {
    block: SCHEMA_FIXTURE.block,
    prompt: SCHEMA_FIXTURE.prompt,
    message: SCHEMA_FIXTURE.message,
    summary: SCHEMA_FIXTURE.summary,
  });
});

test('an event carrying every fixture-required field parses whole', () => {
  for (const name of EVENT_NAMES) {
    const bare = parseEventLine(JSON.stringify(buildEvent(name, false)));
    assert.equal(bare.ok, true, name);
    const withOptional = parseEventLine(JSON.stringify(buildEvent(name, true)));
    assert.equal(withOptional.ok, true, name);
  }
});

test('a required field missing is APP-002 with the field named (4.4 #7)', () => {
  for (const name of EVENT_NAMES) {
    for (const key of Object.keys(SCHEMA_FIXTURE[name].required)) {
      if (key === 'event') continue; // dropping it is the unknown-event case, still APP-002
      const event = buildEvent(name, true);
      delete event[key];
      const result = parseEventLine(JSON.stringify(event));
      assert.equal(result.ok, false, `${name} without "${key}"`);
      assert.equal(result.error.code, 'APP-002', `${name} without "${key}"`);
      assert.ok(
        result.error.detail.includes(key),
        `${name} without "${key}": detail must name the field, got "${result.error.detail}"`,
      );
    }
  }
});

test('a wrong-typed field is APP-002 with the field named (4.4 #8)', () => {
  for (const name of EVENT_NAMES) {
    const entry = SCHEMA_FIXTURE[name];
    for (const [key, types] of Object.entries({ ...entry.required, ...entry.optional })) {
      if (key === 'event') continue;
      const event = buildEvent(name, true);
      event[key] = wrongValue(types);
      const result = parseEventLine(JSON.stringify(event));
      assert.equal(result.ok, false, `${name}.${key} wrong type`);
      assert.equal(result.error.code, 'APP-002', `${name}.${key} wrong type`);
      assert.ok(
        result.error.detail.includes(key),
        `${name}.${key}: detail must name the field, got "${result.error.detail}"`,
      );
    }
  }
});

test('{"event":"summary"} with no numbers is refused (the masked-shape case)', () => {
  const result = parseEventLine('{"event":"summary"}');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APP-002');
  // The detail names the FIRST missing required field; the schema lists
  // `line` before the numbers (the human summary line, 4.3 #26).
  assert.ok(
    result.error.detail.includes('line') || result.error.detail.includes('accepted'),
    result.error.detail,
  );
});

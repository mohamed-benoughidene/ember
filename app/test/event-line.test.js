'use strict';

/** The event-line parser table (step file §2): garbage lines -> APP-002. */

const test = require('node:test');
const assert = require('node:assert/strict');
const { EVENT_NAMES, parseEventLine, answerLine } = require('../shared/parse-event-line');

test('the four pinned event names', () => {
  assert.deepEqual([...EVENT_NAMES], ['block', 'prompt', 'message', 'summary']);
});

test('one valid event of each kind parses whole', () => {
  const cases = [
    '{"event":"block","kind":"item","fields":{"id":1},"text":"- id: 1"}',
    '{"event":"prompt","kind":"choice","text":"[y]es / [n]o / [q]uit","choices":["y","n","q"]}',
    '{"event":"message","text":"dropped proposal: does not quote the source"}',
    '{"event":"summary","accepted":1,"rejected":0,"skipped":0,"aborted":false}',
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

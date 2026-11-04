'use strict';

/**
 * The error-line parser table (step file §2, bridge L2 §5.2).
 *
 * The pattern MUST come from the shared fixture file that the Python
 * contract test also reads, and the pattern constant copied inside the
 * pure module must equal it, so neither side can drift.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { PATTERN_FALLBACK, parseErrorLine } = require('../shared/parse-error-line');
const { loadErrorPattern } = require('../main/error-pattern');
const { errorPatternFixture } = require('./util');

test('the pinned fixture and the module fallback are the same pattern', () => {
  const fromFixture = loadErrorPattern();
  assert.equal(fromFixture, errorPatternFixture(), 'main/error-pattern must read the shared fixture');
  assert.equal(PATTERN_FALLBACK, errorPatternFixture(), 'the documented fallback must equal the fixture');
});

test('a plain house error line parses into its named parts', () => {
  const parsed = parseErrorLine(
    'error: QUERY-003 DbOpenFailed | ember.adapters.sqlite.open_query_database | db file missing | db_path=/x',
    errorPatternFixture(),
  );
  assert.deepEqual(parsed, {
    code: 'QUERY-003',
    name: 'DbOpenFailed',
    where: 'ember.adapters.sqlite.open_query_database',
    detail: 'db file missing | db_path=/x',
  });
});

test('free text with a pipe inside stays one detail', () => {
  const parsed = parseErrorLine(
    'error: MAINTAIN-010 ItemsReadFailed | ember.maintain | reason with | inside | k=v',
    errorPatternFixture(),
  );
  assert.equal(parsed.code, 'MAINTAIN-010');
  assert.equal(parsed.where, 'ember.maintain');
  assert.equal(parsed.detail, 'reason with | inside | k=v');
});

test('a newline inside a free-text value cannot break the parse (re.S rule)', () => {
  const firstLine = 'error: CAPTURE-002 SourceInvalid | ember.capture | the reason was | note=a\nmultiline reason';
  const parsed = parseErrorLine(firstLine, errorPatternFixture());
  assert.equal(parsed.code, 'CAPTURE-002');
  assert.equal(parsed.name, 'SourceInvalid');
  assert.ok(parsed.detail.includes('a\nmultiline reason'), JSON.stringify(parsed));
});

test('further stderr lines ride as detail continuation', () => {
  const parsed = parseErrorLine(
    'error: QUERY-001 ItemNotFound | ember.query | no item 9',
    errorPatternFixture(),
    ['second stderr line', 'third stderr line'],
  );
  assert.equal(parsed.detail, 'no item 9\nsecond stderr line\nthird stderr line');
});

test('a non-house line returns null (the caller raises APP-002)', () => {
  assert.equal(parseErrorLine('Traceback (most recent call last):', errorPatternFixture()), null);
  assert.equal(parseErrorLine('', errorPatternFixture()), null);
  assert.equal(parseErrorLine('error: not-the-shape', errorPatternFixture()), null);
});

test('the parser is null-safe on junk inputs', () => {
  assert.equal(parseErrorLine(undefined, errorPatternFixture()), null);
  assert.equal(parseErrorLine('error: QUERY-003 DbOpenFailed | w | m', '(uncompilable('), null);
});

'use strict';

/**
 * The schema-version gate's own tests (app review fix, ticket A43;
 * app/main/kb-schema-version.js): REAL temp sqlite files, opened the
 * way the engine writes them — the version lives in the
 * `schema_version` TABLE (ember/adapters/sqlite.py), never
 * `PRAGMA user_version`. The rule under test: the gate answers "yes"
 * only for an at-or-above-minimum v13 Ember file, and FAILS CLOSED
 * (false) on everything it cannot honestly read — a v12 file, a file
 * with no schema_version table, a file that is not a database at all
 * (the unreadable leg the A43 review flagged), and a missing path.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { schemaVersionIsAtLeast } = require('../main/kb-schema-version');

/** An honest Ember-shaped file: the schema_version table, one row. */
function emberFile(dir, version) {
  const file = path.join(dir, `kb-v${version}.db`);
  const db = new DatabaseSync(file);
  try {
    db.exec('CREATE TABLE schema_version (version INTEGER NOT NULL)');
    db.prepare('INSERT INTO schema_version (version) VALUES (?)').run(version);
  } finally {
    db.close();
  }
  return file;
}

test('schema gate: a real v13 file passes (and the probe writes nothing)', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-gate-v13-'));
  try {
    const file = emberFile(dir, 13);
    const before = fs.readFileSync(file);
    assert.equal(schemaVersionIsAtLeast(file, 13), true);
    assert.deepEqual(fs.readFileSync(file), before, 'the probe must be read-only: the file bytes unchanged');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('schema gate: a real v12 file fails closed (never migrated by the gate)', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-gate-v12-'));
  try {
    assert.equal(schemaVersionIsAtLeast(emberFile(dir, 12), 13), false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('schema gate: a database with NO schema_version table fails closed', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-gate-notable-'));
  try {
    const file = path.join(dir, 'plain.db');
    const db = new DatabaseSync(file);
    try {
      db.exec('CREATE TABLE something_else (id INTEGER)');
    } finally {
      db.close();
    }
    assert.equal(schemaVersionIsAtLeast(file, 13), false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('schema gate: a file that is NOT a database fails closed', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-gate-text-'));
  try {
    const file = path.join(dir, 'not-a-db.db');
    fs.writeFileSync(file, 'just some text, sorry\n');
    assert.equal(schemaVersionIsAtLeast(file, 13), false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('schema gate: a missing path fails closed', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-gate-missing-'));
  try {
    assert.equal(schemaVersionIsAtLeast(path.join(dir, 'nope.db'), 13), false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

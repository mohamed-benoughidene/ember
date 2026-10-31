'use strict';

/**
 * The read-only schema-version probe behind the undo-label gate (app
 * review fix, ticket A43; extracted from main.js so the decision has
 * its own direct tests).
 *
 * Why it exists: the Edit menu's Undo/Redo labels are derived from
 * `ember undo --dry-run --format json`. That dry-run is READ-shaped
 * but runs through the WRITE command path, which silently MIGRATES an
 * older knowledge-base file (spec 12.8's one-way rule). So on a file
 * older than the undo schema (version 13, migration 013) the
 * derivation must never start.
 *
 * The TRUE mechanism: Ember stores its schema version in the
 * `schema_version` TABLE (see ember/adapters/sqlite.py and the
 * migrations), NOT in SQLite's `PRAGMA user_version`.
 *
 * Safety: the file is opened READ-ONLY (`DatabaseSync(dbPath,
 * { readOnly: true })`), so this probe can never migrate, write, or
 * create anything. Any error — a missing file, a file that is not a
 * database at all, a missing table — returns FALSE (fail closed): a
 * file the probe cannot read is never handed to the dry-run. The
 * failure is said once on stderr in the house APP-000 style; it never
 * carries anything secret (it cannot — only the path's failure shape
 * is named).
 */

function schemaVersionIsAtLeast(dbPath, minimum) {
  try {
    const { DatabaseSync } = require('node:sqlite');
    const db = new DatabaseSync(dbPath, { readOnly: true });
    try {
      const row = db.prepare('SELECT version FROM schema_version').get();
      return Number(row && row.version) >= minimum;
    } finally {
      db.close();
    }
  } catch (err) {
    process.stderr.write(`launch-note: APP-000 AppError | the undo-label gate could not read the file's schema version (${err instanceof Error ? err.message : 'unknown error'})\n`);
    return false; // fail closed: an unreadable file is never migrated
  }
}

module.exports = { schemaVersionIsAtLeast };

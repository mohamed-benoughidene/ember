'use strict';

/**
 * The read-only schema-version probe behind the undo-label gate (app
 * review fix, ticket A43; replaced by the G2 decision, 2026-11-01).
 *
 * Why it exists: the Edit menu's Undo/Redo labels are derived from
 * `ember undo --dry-run --format json`. On a knowledge base older than
 * the undo schema (version 13, migration 013) the derivation is
 * refused, and the labels stay honestly disabled.
 *
 * THE MECHANISM (G2, rule B2): the app NEVER opens the knowledge base
 * file itself — not even read-only. It asks the ENGINE's read-only
 * health check, `ember db-check --format json` (through the step-09
 * runner), and reads the `version: N` report line from the document.
 * db-check never migrates and never writes, and DRIFT / UNREADABLE /
 * a missing version line all FAIL CLOSED (return false): a file the
 * engine cannot vouch for is never handed to a dry-run. The failure
 * is said once on stderr in the house APP-000 style; it never carries
 * anything secret.
 */

const { runDbCheck } = require('./db-check-runner');

/**
 * Ask the engine (never the file) whether the knowledge base's schema
 * version is at least `minimum`. Async (one `ember db-check` child).
 *
 * @param {string} dbPath the knowledge base path (`--db`)
 * @param {number} minimum the gate's floor (13 = the undo schema)
 * @param {{emberCommand: string[], errorPattern: string|null}} engine the
 *   resolved `ember` command and the shared error-line regex source
 * @param {typeof import('./db-check-runner').runDbCheck} [runDbCheckImpl] test seam
 * @returns {Promise<boolean>} false (fail closed) when the engine cannot
 *   vouch for the file: any error, DRIFT, UNREADABLE, or a report
 *   without a `version: N` line.
 */
function schemaVersionIsAtLeast(dbPath, minimum, engine, runDbCheckImpl = runDbCheck) {
  return runDbCheckImpl({
    emberCommand: engine.emberCommand,
    errorPattern: engine.errorPattern,
    dbPath,
  }).then((result) => {
    if (!result.ok || result.data.result !== 'OK') {
      process.stderr.write(
        `launch-note: APP-000 AppError | the undo-label gate could not verify the file's schema version (db-check said ${result.ok ? result.data.result : 'an error'})\n`,
      );
      return false;
    }
    const line = result.data.lines.find((l) => /^version: \d+$/.test(l));
    if (!line) {
      process.stderr.write(
        "launch-note: APP-000 AppError | the undo-label gate could not read the file's schema version (no version line in the check report)\n",
      );
      return false;
    }
    return Number(line.slice('version: '.length)) >= minimum;
  });
}

module.exports = { schemaVersionIsAtLeast };

'use strict';

/**
 * The db-check runner (app step 09, Keep safe; ticket A38).
 *
 * WHY not the step-02 runCommand: `db-check` is the one command that
 * ends exit 1 WITH a valid report document on stdout (DRIFT and
 * UNREADABLE do that by contract, docs/commands.md "Engine E: Utility"
 * — "any drift exits 1", "an unreadable database exits 1 too"). The
 * bridge client treats any non-zero exit as "the stderr house error
 * line is THE result", which would throw the whole report away. This
 * module changes exactly that one interpretation: exit 0 AND exit 1
 * both carry the report; every other failure is an error like before.
 * The step-02 bridge client is untouched (additive step rule).
 *
 * Shapes follow the pinned contract (tests/bridge/test_contract_table.py):
 * `db-check --db <path> --format json` prints ONE document with top-level
 * keys command/changes/summary/dry_run, where summary is the report
 * {result, detail, lines} — `result` is OK | DRIFT | UNREADABLE, `lines`
 * is the report's rows. Every child line is untrusted and validated once
 * here (D4). It is a read: it never migrates and never writes (I12).
 *
 * Pure Node, no Electron import, so the node suite runs it directly.
 */

const { spawn } = require('node:child_process');
const { appErrorInfo } = require('../shared/errors');
const { parseErrorLine } = require('../shared/parse-error-line');

const WHERE = 'main.db-check-runner';
const RESULTS = new Set(['OK', 'DRIFT', 'UNREADABLE']);

/**
 * @param {object} options
 * @param {string[]} options.emberCommand resolved command prefix
 * @param {string|null} options.errorPattern shared error-line regex source
 * @param {string} options.dbPath the knowledge base path (`--db`)
 * @param {number} [options.timeoutMs] default 30000 (a read; plan §5.1)
 * @param {number} [options.attempts] default 2 (reads retry once; the
 *   command itself changes nothing, so a repeat is safe — I15)
 * @param {typeof import('node:child_process').spawn} [options.spawnFn] test seam
 * @returns {Promise<{ok: true, data: {result: string, detail: string|null, lines: string[], exitCode: number}} |
 *           {ok: false, error: {code: string, name: string, where: string, detail: string}}>}
 *   A DRIFT or UNREADABLE report is DATA, not an error: the screen
 *   renders it (stories 75, 77).
 */
function runDbCheck(options) {
  const {
    emberCommand,
    errorPattern,
    dbPath,
    timeoutMs = 30_000,
    attempts = 2,
    spawnFn = spawn,
  } = options;

  const argv = [...emberCommand, 'db-check', '--db', dbPath, '--format', 'json'];

  function attemptOnce() {
    return new Promise((resolve) => {
      let child;
      try {
        child = spawnFn(argv[0], argv.slice(1), { env: { ...process.env }, stdio: ['ignore', 'pipe', 'pipe'] });
      } catch (err) {
        resolve({ failed: true, error: appErrorInfo('APP-001', WHERE, err instanceof Error ? err.message : 'spawn failed') });
        return;
      }
      const stdoutChunks = [];
      const stderrLines = [];
      let timedOut = false;
      let settled = false;
      const timer = setTimeout(() => {
        timedOut = true;
        try {
          child.kill('SIGTERM');
        } catch {
          /* already gone */
        }
        setTimeout(() => {
          try {
            child.kill('SIGKILL');
          } catch {
            /* already gone */
          }
        }, 1000);
      }, timeoutMs);
      child.stdout.on('data', (chunk) => stdoutChunks.push(chunk));
      child.stderr.on('data', (chunk) => {
        for (const line of String(chunk).split('\n')) {
          if (line !== '') stderrLines.push(line);
        }
      });
      child.on('error', (err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({ failed: true, error: appErrorInfo('APP-001', WHERE, `could not start the ember command: ${err.message}`) });
      });
      child.on('close', (code) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({
          failed: false,
          timedOut,
          exitCode: typeof code === 'number' ? code : null,
          stdout: Buffer.concat(stdoutChunks).toString('utf8'),
          stderrLines,
        });
      });
    });
  }

  function interpret(run) {
    if (run.exitCode === 0 || run.exitCode === 1) {
      // Exit 0 = the report ends `result: OK`; exit 1 = DRIFT or
      // UNREADABLE. EITHER WAY the document on stdout is the result.
      let parsed;
      try {
        parsed = JSON.parse(run.stdout.trim());
      } catch {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.runDbCheck`, 'ember db-check did not print one JSON document') };
      }
      const summary = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed.summary : null;
      if (
        summary === null ||
        typeof summary !== 'object' ||
        !RESULTS.has(summary.result) ||
        !Array.isArray(summary.lines) ||
        !summary.lines.every((l) => typeof l === 'string')
      ) {
        return { ok: false, error: appErrorInfo('APP-002', `${WHERE}.runDbCheck`, 'ember db-check printed an unexpected report shape') };
      }
      const detail = typeof summary.detail === 'string' ? summary.detail : null;
      return { ok: true, data: { result: summary.result, detail, lines: summary.lines, exitCode: run.exitCode } };
    }
    // Any other exit: the house error line is THE result (bridge L2 §5.2).
    const first = run.stderrLines[0] ?? '';
    const parsed = errorPattern ? parseErrorLine(first, errorPattern, run.stderrLines.slice(1)) : null;
    if (parsed) return { ok: false, error: parsed };
    return {
      ok: false,
      error: appErrorInfo(
        'APP-002',
        `${WHERE}.runDbCheck`,
        `ember db-check exited ${run.exitCode === null ? 'without a code' : run.exitCode}${first ? `: ${first}` : ' (no stderr)'}`,
      ),
    };
  }

  return (async () => {
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const run = await attemptOnce();
      if (run.failed) return { ok: false, error: run.error };
      if (!run.timedOut) return interpret(run);
    }
    return {
      ok: false,
      error: appErrorInfo('APP-008', `${WHERE}.runDbCheck`, `ember db-check timed out after ${timeoutMs} ms, and the one allowed retry timed out too`),
    };
  })();
}

module.exports = { runDbCheck };

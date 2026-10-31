'use strict';

/**
 * The e2e runner (dev-only, Linux): runs every test/e2e/*.js file, in
 * name order, optionally FILTERED by filename words (the step-04 check
 * command `npm --prefix app run e2e -- first-run home lookup` passes
 * three words; a file runs when its name contains ANY of them).
 * Without arguments every e2e runs, exactly as `npm run e2e` always did.
 *
 * Each file gets a 10-minute watchdog (one wedged file can never hold
 * the suite) and the runner exits EXPLICITLY with its verdict: the last
 * Electron child can hold this process open (the step-11 global
 * shortcut registers through the desktop portal).
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const dir = __dirname;
const filters = process.argv.slice(2).filter((a) => a !== '--');
const FILE_TIMEOUT_MS = 10 * 60 * 1000;

let files = fs
  .readdirSync(dir)
  .filter((f) => f.endsWith('.js') && f !== 'run-all.js' && f !== 'helpers')
  .sort()
  .map((f) => path.join(dir, f));

if (filters.length > 0) {
  files = files.filter((f) => filters.some((word) => path.basename(f).includes(word)));
}

async function runFile(file) {
  process.stdout.write(`\n=== e2e ${path.basename(file)} ===\n`);
  const child = spawn(process.execPath, [file], { stdio: 'inherit' });
  const watchdog = setTimeout(() => {
    process.stderr.write(`\ne2e TIMEOUT: ${path.basename(file)} exceeded 10 minutes — killed\n`);
    child.kill('SIGKILL');
  }, FILE_TIMEOUT_MS);
  const code = await new Promise((resolve) => {
    child.on('exit', (c, signal) => resolve(signal === 'SIGKILL' ? 1 : c));
  });
  clearTimeout(watchdog);
  return code === 0;
}

async function main() {
  if (files.length === 0) {
    process.stderr.write(`no e2e file matches: ${filters.join(' ')}\n`);
    process.exit(1);
  }
  let failed = 0;
  for (const file of files) {
    const ok = await runFile(file);
    if (!ok) failed += 1;
  }
  if (failed > 0) {
    process.stderr.write(`\ne2e FAILED: ${failed} of ${files.length} file(s) failed\n`);
    process.exit(1);
  }
  process.stdout.write(`\ne2e OK: ${files.length} file(s) passed\n`);
  process.exit(0); // the last Electron child may hold the loop open
}

main().catch((err) => {
  process.stderr.write(`e2e run-all FAILED: ${err && err.message ? err.message : err}\n`);
  process.exit(1);
});

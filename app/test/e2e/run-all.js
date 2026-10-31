'use strict';

/**
 * The e2e runner (dev-only, Linux): runs every test/e2e/*.js file, in
 * name order, optionally FILTERED by filename words (the step-04 check
 * command `npm --prefix app run e2e -- first-run home lookup` passes
 * three words; a file runs when its name contains ANY of them).
 * Without arguments every e2e runs, exactly as `npm run e2e` always did.
 */

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const dir = __dirname;
const filters = process.argv.slice(2).filter((a) => a !== '--');

let files = fs
  .readdirSync(dir)
  .filter((f) => f.endsWith('.js') && f !== 'run-all.js' && f !== 'helpers')
  .sort()
  .map((f) => path.join(dir, f));

if (filters.length > 0) {
  files = files.filter((f) => filters.some((word) => path.basename(f).includes(word)));
}

if (files.length === 0) {
  process.stderr.write(`no e2e file matches: ${filters.join(' ')}\n`);
  process.exit(1);
}

let failed = 0;
for (const file of files) {
  process.stdout.write(`\n=== e2e ${path.basename(file)} ===\n`);
  const result = spawnSync(process.execPath, [file], { stdio: 'inherit' });
  if (result.status !== 0) failed += 1;
}

if (failed > 0) {
  process.stderr.write(`\ne2e FAILED: ${failed} of ${files.length} file(s) failed\n`);
  process.exit(1);
}
process.stdout.write(`\ne2e OK: ${files.length} file(s) passed\n`);

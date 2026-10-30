'use strict';

/**
 * The node test runner (thin wrapper, same engine as step 02):
 * `node --test` over app/test/'s *.test.js files.
 *
 * Why the wrapper: the step-03 check command is
 *   `npm --prefix app test -- design`
 * and node's runner would read "design" as a missing path. The wrapper
 * takes the first argument as a filename FILTER:
 *   npm test             -> every test/*.test.js   (step-02 behaviour kept)
 *   npm test -- design   -> test/design-*.test.js  (the step-03 check)
 */

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const filter = process.argv[2];
const dir = __dirname;

let files = fs
  .readdirSync(dir)
  .filter((f) => f.endsWith('.test.js'))
  .sort()
  .map((f) => path.join(dir, f));

if (filter) files = files.filter((f) => path.basename(f).includes(filter));

if (files.length === 0) {
  process.stderr.write(`no test file matches "${filter}"\n`);
  process.exit(1);
}

const result = spawnSync(process.execPath, ['--test', ...files], { stdio: 'inherit' });
process.exit(result.status ?? 1);

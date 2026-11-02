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

const ALL_FILES = fs
  .readdirSync(dir)
  .filter((f) => f.endsWith('.test.js'))
  .sort()
  .map((f) => path.join(dir, f));

let files = ALL_FILES;

if (filter) files = files.filter((f) => path.basename(f).includes(filter));

if (files.length === 0) {
  process.stderr.write(`no test file matches "${filter}"\n`);
  process.exit(1);
}

/**
 * Test-hygiene gate (N12, batch 5 chunk 2). A `t.test(...)` subtest that is
 * neither awaited nor returned outlives its parent: node's runner then
 * cancels it silently (node 22+) or never settles the run (node 24, the
 * planted-demo evidence for this chunk). Option B, check-report decision 4:
 * a text-level check, run over every *.test.js BEFORE `node --test` spawns.
 * It can miss unusual shapes, but it never misses this one: the house rule
 * (every file with subtests, e.g. maintain-words.test.js) is
 * `await t.test(...)` / `return t.test(...)` on one line.
 *
 * A file whose line holds a `t.test(` call site not preceded on that line
 * by `await` or `return` is refused: named, one line, then the run stops.
 */
function floatingSubtestLine(file) {
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  for (let i = 0; i < lines.length; i++) {
    const match = /\bt\.test\s*\(/.exec(lines[i]);
    if (!match) continue;
    const before = lines[i].slice(0, match.index).trim();
    if (/(^|\s)(await|return)$/.test(before)) continue;
    return i + 1;
  }
  return null;
}

const refused = [];
for (const file of ALL_FILES) {
  const line = floatingSubtestLine(file);
  if (line) {
    const rel = path.relative(path.join(dir, '..'), file);
    refused.push(`refused by the test-hygiene gate: ${rel}:${line} has a t.test(...) subtest that is neither awaited nor returned — the run stops here (await it or return it)`);
  }
}

if (refused.length > 0) {
  for (const line of refused) process.stderr.write(`${line}\n`);
  process.exit(1);
}

const result = spawnSync(process.execPath, ['--test', '--test-concurrency=1', ...files], { stdio: 'inherit' });
process.exit(result.status ?? 1);

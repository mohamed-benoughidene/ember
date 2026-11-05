'use strict';

/**
 * The e2e runner (dev-only, Linux): runs every test/e2e/*.js file, in
 * name order, optionally FILTERED by filename words (the step-04 check
 * command `npm --prefix app run e2e -- first-run home lookup` passes
 * three words; a file runs when its name contains ANY of them).
 * Without arguments every e2e runs, exactly as `npm run e2e` always did.
 *
 * Each file runs under its OWN xvfb display: the runner spawns
 * `xvfb-run -a node <file>`, so every file gets a freshly picked,
 * free server number (lock-file scan from :99) that dies with the
 * file. This keeps one wedged/starved display from dragging later
 * files down (issue #43: after ~10 files on ONE shared display,
 * browsers stop rendering frames while JS stays healthy). If
 * `xvfb-run` is not installed, files run directly, as before this
 * change. Each file keeps a 10-minute watchdog (one wedged file can
 * never hold the suite) and the runner exits EXPLICITLY with its
 * verdict: the last Electron child can hold this process open (the
 * step-11 global shortcut registers through the desktop portal).
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

// Find xvfb-run on PATH once (returns null when it is not installed).
function findXvfbRun() {
  for (const d of (process.env.PATH || '').split(':')) {
    if (!d) continue;
    const p = path.join(d, 'xvfb-run');
    try {
      fs.accessSync(p, fs.constants.X_OK);
      return p;
    } catch {
      // keep scanning
    }
  }
  return null;
}

const xvfbRun = findXvfbRun();

// Spawn the file's child detached (its own process group) so the
// watchdog can take down the whole tree: xvfb-run's shell, the file,
// its Electron children and that file's Xvfb display — releasing the
// display instead of leaking its lock file.
function spawnFile(file) {
  if (xvfbRun) {
    return spawn(xvfbRun, ['-a', process.execPath, file], { stdio: 'inherit', detached: true });
  }
  return spawn(process.execPath, [file], { stdio: 'inherit' });
}

function killGroup(child, signal) {
  try {
    process.kill(-child.pid, signal);
  } catch {
    child.kill(signal); // no process group (direct spawn) — kill the child alone
  }
}

async function runFile(file) {
  process.stdout.write(`\n=== e2e ${path.basename(file)} ===\n`);
  const child = spawnFile(file);
  let killTimer = null;
  const watchdog = setTimeout(() => {
    process.stderr.write(`\ne2e TIMEOUT: ${path.basename(file)} exceeded 10 minutes — killed\n`);
    // TERM first so xvfb-run/Xvfb clean up their lock files, KILL after.
    killGroup(child, 'SIGTERM');
    killTimer = setTimeout(() => killGroup(child, 'SIGKILL'), 5 * 1000);
  }, FILE_TIMEOUT_MS);
  const code = await new Promise((resolve) => {
    child.on('exit', (c, signal) => resolve(signal === 'SIGKILL' ? 1 : c));
  });
  clearTimeout(watchdog);
  clearTimeout(killTimer);
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

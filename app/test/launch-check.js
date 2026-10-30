'use strict';

/**
 * The S1 check (`npm run check:launch`): the window starts, ONE real
 * read command runs against a REAL knowledge base, `items: N` lands
 * on stdout, the app exits 0. Headless where a display exists (this
 * check needs Electron; without a display or Electron it fails loudly,
 * never silently).
 *
 * It builds a throwaway knowledge base with the project venv's
 * `ember capture-source` (no AI key needed), then launches the real
 * Electron shell with EMBER_APP_LAUNCH_CHECK=1.
 */

const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { APP_ROOT, REPO_ROOT } = require('./util');

const TIMEOUT_MS = 90_000;

function fail(message) {
  process.stderr.write(`check:launch FAILED: ${message}\n`);
  process.exit(1);
}

function main() {
  const venvEmber = path.join(REPO_ROOT, '.venv', 'bin', 'ember');
  if (!fs.existsSync(venvEmber)) {
    fail(`the project venv ember is missing at ${venvEmber} (this check reads a real knowledge base)`);
  }
  const electronBin = path.join(APP_ROOT, 'node_modules', '.bin', 'electron');
  if (!fs.existsSync(electronBin)) {
    fail('electron is not installed — run `npm install` inside app/');
  }

  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-launch-check-'));
  const kbPath = path.join(workDir, 'kb.db');
  try {
    execFileSync(venvEmber, ['capture-source', '--db', kbPath], {
      input: 'A throwaway source text for the app launch check.\n',
      stdio: ['pipe', 'ignore', 'inherit'],
    });

    const child = spawn(electronBin, ['.'], {
      cwd: APP_ROOT,
      env: {
        ...process.env,
        EMBER_APP_LAUNCH_CHECK: '1',
        EMBER_APP_DB: kbPath,
        EMBER_APP_COMMAND: venvEmber,
        RTI_FAKE_WORKDIR: workDir,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      fail('no "items: N" line within 90000 ms');
    }, TIMEOUT_MS);

    child.stdout.on('data', (c) => {
      stdout += String(c);
    });
    child.stderr.on('data', (c) => {
      stderr += String(c);
    });
    child.on('error', (err) => {
      clearTimeout(timer);
      fail(`could not start Electron: ${err.message}`);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const itemsLine = stdout.split('\n').find((line) => /^items: \d+$/.test(line));
      if (code !== 0) {
        fail(`the app exited ${code}${stderr.trim() ? `: ${stderr.trim().split('\n').at(-1)}` : ''}`);
      }
      if (!itemsLine) {
        fail(`exit 0 but no "items: N" line on stdout (stdout: ${JSON.stringify(stdout.slice(0, 200))})`);
      }
      process.stdout.write(`check:launch OK — window started, one read command answered: ${itemsLine}\n`);
      fs.rmSync(workDir, { recursive: true, force: true });
      process.exit(0);
    });
  } catch (err) {
    fs.rmSync(workDir, { recursive: true, force: true });
    fail(`seeding the throwaway knowledge base failed: ${err.message}`);
  }
}

main();

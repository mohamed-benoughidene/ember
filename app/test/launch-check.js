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
  // The venv's ember: POSIX keeps the console script; Windows has no
  // bin/ folder — there the SAME CLI runs as `python -m ember` (the
  // spike note: the entry point is ember/__main__.py), and the matrix
  // job builds the venv with the same layout on every OS.
  // EMBER_APP_COMMAND is a space-split argv prefix (ember-command.js),
  // so the child form is the same string on every platform.
  const isWin = process.platform === 'win32';
  const venvPython = isWin ? path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe') : path.join(REPO_ROOT, '.venv', 'bin', 'python');
  const seedCmd = isWin ? venvPython : path.join(REPO_ROOT, '.venv', 'bin', 'ember');
  const seedBaseArgs = isWin ? ['-m', 'ember', 'capture-source'] : ['capture-source'];
  const commandEnv = isWin ? `${venvPython} -m ember` : path.join(REPO_ROOT, '.venv', 'bin', 'ember');
  const emberPresent = isWin ? seedCmd : commandEnv;
  if (!fs.existsSync(emberPresent)) {
    fail(`the project venv ember is missing (${emberPresent}) — this check reads a real knowledge base`);
  }
  // The Electron binary, resolved the portable way: under PLAIN Node
  // the electron npm package exports the path to the real binary on
  // every OS (the node_modules/.bin shim is a POSIX-only shell script).
  const electronBin = require('electron');
  if (typeof electronBin !== 'string' || !fs.existsSync(electronBin)) {
    fail(`electron is not installed — run \`npm install\` inside app/ (got: ${JSON.stringify(electronBin)})`);
  }

  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-launch-check-'));
  const kbPath = path.join(workDir, 'kb.db');
  try {
    execFileSync(seedCmd, [...seedBaseArgs, '--db', kbPath], {
      input: 'A throwaway source text for the app launch check.\n',
      stdio: ['pipe', 'ignore', 'inherit'],
    });

    const child = spawn(electronBin, ['.'], {
      cwd: APP_ROOT,
      env: {
        ...process.env,
        EMBER_APP_LAUNCH_CHECK: '1',
        EMBER_APP_DB: kbPath,
        EMBER_APP_COMMAND: commandEnv,
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

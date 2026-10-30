'use strict';

/**
 * The first Playwright E2E smoke (dev-only, Linux; the CI story is
 * step 13). It launches the REAL Electron shell,
 *
 *  1. the placeholder renders ("Ember is starting" -> "Ember is running"),
 *  2. the preload seam answers (`window.ember.ping()` and the full
 *     runtime allowlist — the renderer sees EXACTLY the named calls),
 *  3. one real read command's count reaches the DOM ("items: N"),
 *  4. the page world has no `process` (sandbox + contextIsolation).
 *
 * The bridge runs against the fake ember stub so the smoke is
 * deterministic and independent of the Python venv.
 */

const { _electron } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { APP_ROOT } = require('../util');

const EXPECTED_API = [
  'ping',
  'getState',
  'saveSettings',
  'listItems',
  'keyStatus',
  'setKey',
  'setSessionKey',
  'removeKey',
];

async function waitFor(predicate, timeoutMs, what) {
  const start = Date.now();
  while (!(await predicate())) {
    if (Date.now() - start > timeoutMs) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

async function main() {
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-'));
  // A throwaway "knowledge base" with the SQLite header: the fake
  // ember never reads it, but the APP-006 guard may.
  const kbPath = path.join(workDir, 'kb.db');
  fs.writeFileSync(kbPath, Buffer.concat([Buffer.from('SQLite format 3\x00'), Buffer.alloc(96, 0)]));

  const app = await _electron.launch({
    args: ['.'],
    cwd: APP_ROOT,
    env: {
      ...process.env,
      EMBER_APP_DB: kbPath,
      EMBER_APP_COMMAND: `node ${path.join(APP_ROOT, 'test', 'fake-ember.js')}`,
      FAKE_MODE: 'list',
      FAKE_TOTAL: '3',
    },
  });
  try {
    const win = await app.firstWindow();

    // 1. the placeholder renders, from starting to running
    await win.waitForSelector('[data-testid="status"]');
    await waitFor(
      async () => (await win.textContent('[data-testid="status"]')) === 'Ember is running',
      15000,
      'the placeholder to reach "Ember is running"',
    );

    // 2. one real read command's data reached the DOM
    const itemsText = await win.textContent('[data-testid="items"]');
    if (itemsText !== 'items: 3') {
      throw new Error(`the placeholder shows ${JSON.stringify(itemsText)}, expected "items: 3"`);
    }

    // 3. the preload seam answers from the PAGE world
    const pong = await win.evaluate(() => window.ember.ping());
    if (pong !== 'pong') throw new Error(`window.ember.ping() returned ${JSON.stringify(pong)}`);

    // 4. the runtime allowlist is EXACTLY the named list (B5)
    const runtimeApi = await win.evaluate(() => Object.keys(window.ember).sort());
    if (JSON.stringify(runtimeApi) !== JSON.stringify([...EXPECTED_API].sort())) {
      throw new Error(`window.ember exposes ${JSON.stringify(runtimeApi)}, expected exactly ${JSON.stringify(EXPECTED_API)}`);
    }

    // 5. no Node in the page world (T9 at runtime)
    const leaked = await win.evaluate(() => ({
      process: typeof process,
      require: typeof window.require,
      nodeRequire: typeof window.nodeRequire,
    }));
    if (leaked.process !== 'undefined' || leaked.require !== 'undefined' || leaked.nodeRequire !== 'undefined') {
      throw new Error(`Node leaked into the renderer: ${JSON.stringify(leaked)}`);
    }

    const errorText = await win.textContent('[data-testid="error"]');
    if (errorText.trim() !== '') {
      throw new Error(`the placeholder surfaced an error: ${errorText}`);
    }

    process.stdout.write('e2e smoke OK: placeholder renders, seam answers exactly the allowlist, items: 3 shown, no Node in the page world\n');
  } finally {
    await app.close();
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

main().catch((err) => {
  process.stderr.write(`e2e smoke FAILED: ${err.message}\n`);
  process.exit(1);
});

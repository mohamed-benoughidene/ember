'use strict';

/**
 * The Playwright E2E walking skeleton (dev-only, Linux) — same
 * guarantees as the step-02 smoke, now over the real step-04 shell:
 *
 *  1. the app boots into Home (settings seeded with the KB override),
 *  2. the preload seam answers (`window.ember.ping()` and the full
 *     runtime allowlist — the renderer sees EXACTLY the named calls),
 *  3. real read-command data reaches the DOM (the counts panel),
 *  4. the page world has no `process`/`require` (sandbox +
 *     contextIsolation),
 *  5. no error banner.
 *
 * The bridge runs against the fake ember stub (FAKE_MODE=app) so the
 * smoke is deterministic and independent of the Python venv. The
 * XDG_CONFIG_HOME points into a throwaway directory, so the smoke
 * never touches the developer's own settings.
 */

const { _electron } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { APP_ROOT } = require('../util');
const { launchShell } = require('./helpers/shell.js');

const EXPECTED_API = [
  'ping',
  'getState',
  'saveSettings',
  'kbStatus',
  'pickKnowledgeBaseFile',
  'listItems',
  'topicSearch',
  'showItem',
  'history',
  'currentState',
  'maintainDryRun',
  'keyStatus',
  'setKey',
  'setSessionKey',
  'removeKey',
  /* App 05 (ticket A34): the Add confirm-session joins the pinned
     surface: three invoke calls, the buffered attach, two event
     subscriptions. */
  'startAdd',
  'answerAdd',
  'stopAdd',
  'attachAdd',
  'onAddEvent',
  'onAddExit',
  // App step 09 (Keep safe) — appended as this step's own block.
  'pickSaveFile',
  'backupTo',
  'exportTo',
  'dbCheck',
  'switchKnowledgeBase',
  // app step 07 (Fix and close), appended at the END
  'fixAction',
  'undoPlan',
  /* App 06 (ticket A35): the Link items confirm-session joins the
     pinned surface at the END: four invoke calls, the buffered
     attach, two event subscriptions. */
  'startRelate',
  'answerRelate',
  'stopRelate',
  'attachRelate',
  'onRelateEvent',
  'onRelateExit',
];

async function main() {
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-smoke-'));
  const { app, workDir: work } = await launchShell({ workDir, mode: 'app' });
  void work;
  try {
    const win = await app.firstWindow();

    // 1. the shell renders: sidebar + Home pane
    await win.waitForSelector('[data-testid="home-pane"]');
    const navButtons = await win.locator('#nav button').count();
    if (navButtons !== 8) throw new Error(`expected the eight job buttons in the sidebar, saw ${navButtons}`);

    // 2. real read-command data reaches the DOM (5 items in the fixture)
    await win.waitForSelector('[data-testid="counts-panel"]');
    const total = await win.textContent('[data-testid="count-total"]');
    if (total.trim() !== '5') throw new Error(`the total count from list-items should be 5, saw ${total.trim()}`);

    // 3. the preload seam answers from the PAGE world
    const pong = await win.evaluate(() => window.ember.ping());
    if (pong !== 'pong') throw new Error(`window.ember.ping() returned ${JSON.stringify(pong)}`);

    // 4. the runtime allowlist is EXACTLY the named list (B5)
    //    (App 05 adds the six Add-session calls; see EXPECTED_API)
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

    // 6. no notice banner, no boot error
    const banner = await win.locator('#top-banner').innerHTML();
    if (banner.trim() !== '') throw new Error(`a notice banner appeared: ${banner.slice(0, 200)}`);

    process.stdout.write('e2e smoke OK: real shell boots into Home, the counts from list-items reach the DOM (total 5), the seam answers exactly the pinned 34-name allowlist, no Node in the page world\n');  } finally {
    await app.close();
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

main().catch((err) => {
  process.stderr.write(`e2e smoke FAILED: ${err.message}\n`);
  process.exit(1);
});

'use strict';

/**
 * The story-107 E2E (app step 13, dev-only, Linux): the app makes ZERO
 * outside network requests during a real run.
 *
 * How it observes: Playwright sees every request the app's pages make
 * (`page.on('request')` — passive, nothing intercepted, the app runs
 * exactly as always). During one run over Home + three panes the
 * collected URLs are judged: EVERY one must be the app's own
 * `file://` pages and assets, and there must be several (a tap that
 * never fires proves nothing).
 *
 * The app's ONLY permitted network use — `ember` talking to the AI
 * service the user chose — runs inside the child process and is
 * deliberately outside this audit (the fake-AI e2e files exercise it
 * at the Python seam). The CSP origin pins and the no-auto-update rule
 * are asserted statically next door (test/no-network.test.js), and a
 * first candidate main-process audit seam (webRequest) was REVERTED:
 * registering a webRequest listener crashed the network service on
 * Electron 45.1.0 under this desktop (recorded in the build notes).
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { launchShell } = require('./helpers/shell.js');

function fail(message) {
  throw new Error(message);
}

async function main() {
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-e2e-net-'));
  const seen = [];
  const { app } = await launchShell({ workDir, mode: 'app' });

  try {
    const win = await app.firstWindow();
    win.on('request', (request) => seen.push(request.url()));
    // A second window (the quick popup) would be watched the same way;
    // this run never opens it — the main window's audit is the story's
    // claim, and the smoke pins the popup separately.

    await win.waitForSelector('[data-testid="home-pane"]');
    await win.waitForSelector('[data-testid="counts-panel"]');

    // A short walk so more than one page worth of requests happens.
    for (const job of ['lookup', 'keepsafe', 'home', 'add']) {
      await win.locator(`#nav button[data-job="${job}"]`).click();
      await win.waitForTimeout(250);
    }
    await win.waitForSelector('[data-testid="add-pane"]');
    // Give any late request a beat, then close cleanly.
    await win.waitForTimeout(500);
    await Promise.race([
      app.close(),
      new Promise((resolve) => {
        setTimeout(() => {
          try {
            app.process().kill('SIGKILL');
          } catch { /* already gone */ }
          resolve();
        }, 5000);
      }),
    ]);
  } finally {
    fs.rmSync(workDir, { recursive: true, force: true });
  }

  if (seen.length < 3) {
    fail(`the audit saw only ${seen.length} request(s) — an audit this empty proves nothing (${JSON.stringify(seen)})`);
  }
  const outside = seen.filter((url) => !url.startsWith('file://'));
  if (outside.length > 0) {
    fail(`STORY 107 VIOLATED — the app fetched outside its own files: ${JSON.stringify(outside, null, 2)}`);
  }
  process.stdout.write(
    `e2e no-network OK (story 107): the app made ${seen.length} request(s) during the run, every one of them its own file:// pages and assets — zero outside requests\n`,
  );
}

main().catch((err) => {
  process.stderr.write(`e2e no-network FAILED: ${err.message}\n`);
  process.exit(1);
});

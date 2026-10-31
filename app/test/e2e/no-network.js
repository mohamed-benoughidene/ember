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
 * never fires proves nothing). Since the A43 review fix the SAME
 * passive audit runs over the quick POPUP page too (its own array;
 * same rule, about:blank as an allowed empty-page start).
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
  const popupSeen = []; // the popup page's own collection (the A43 fix)
  const { app } = await launchShell({ workDir, mode: 'app' });

  try {
    const win = await app.firstWindow();
    win.on('request', (request) => seen.push(request.url()));
    // The quick popup is watched the same way, below (its own `seen`
    // array; the A43 review fix closed the one-window blind spot).

    await win.waitForSelector('[data-testid="home-pane"]');
    await win.waitForSelector('[data-testid="counts-panel"]');

    // A short walk so more than one page worth of requests happens.
    for (const job of ['lookup', 'keepsafe', 'home', 'add']) {
      await win.locator(`#nav button[data-job="${job}"]`).click();
      await win.waitForTimeout(250);
    }
    await win.waitForSelector('[data-testid="add-pane"]');
    await win.waitForTimeout(500);

    /* --- the quick popup's audit (A43 review fix, story 107's blind
       spot): the SAME passive observation over the popup page. The
       window listener is registered BEFORE the popup opens, so its
       page-load requests are seen from the first one. The popup is
       opened the way popup.js scenario 1 does — through the SAME
       handler the shortcut and tray share — and the run passes the
       story-94 gate because EMBER_APP_DB gives it a chosen file. --- */
    app.on('window', (page) => {
      page.on('request', (request) => popupSeen.push(request.url()));
    });
    // The popup route needs the app's first-run state complete, and
    // Add hides its form without an AI key (the no-key state) — seed
    // both the same way popup.js scenario 1 does, through the same
    // preload seam a real user passes.
    const kept = await win.evaluate((k) => window.ember.setSessionKey(k), 'sk-or-v1-ember-e2e-fake-key-0123456789');
    if (!kept || kept.ok !== true) {
      fail(`the session key could not be kept for the popup audit: ${JSON.stringify(kept)}`);
    }
    const openRes = await win.evaluate(() => window.ember.openQuickPopup());
    if (!openRes || openRes.ok !== true) {
      fail(`the quick popup could not be opened for the popup audit: ${JSON.stringify(openRes)}`);
    }
    let popup = null;
    for (let i = 0; i < 100; i += 1) {
      popup = app.windows().find((w) => w !== win && w.url().includes('quick.html'));
      if (popup) break;
      await new Promise((r) => setTimeout(r, 100));
    }
    if (!popup) fail('no quick popup window appeared for the popup audit');
    await popup.waitForSelector('[data-testid="add-text-input"]'); // the form really rendered
    // Give any late request a beat, then close cleanly.
    await popup.waitForTimeout(500);
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
  if (popupSeen.length < 2) {
    fail(`the popup audit saw only ${popupSeen.length} request(s) — an audit this empty proves nothing (${JSON.stringify(popupSeen)})`);
  }
  const popupOutside = popupSeen.filter((url) => !url.startsWith('file://') && url !== 'about:blank');
  if (popupOutside.length > 0) {
    fail(`STORY 107 VIOLATED — the quick popup fetched outside its own files: ${JSON.stringify(popupOutside, null, 2)}`);
  }
  process.stdout.write(
    `e2e no-network OK (story 107): the app made ${seen.length} request(s) and the quick popup ${popupSeen.length}, every one of them its own file:// pages and assets (about:blank allowed on the popup) — zero outside requests\n`,
  );
}

main().catch((err) => {
  process.stderr.write(`e2e no-network FAILED: ${err.message}\n`);
  process.exit(1);
});

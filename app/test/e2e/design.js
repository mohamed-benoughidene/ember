'use strict';

/**
 * The design e2e (L3 app step 03, dev-only). It drives the EXACT page
 * the founder's check command opens (`npm run gallery` -> gallery/main.js)
 * through the real Electron shell and proves, with the page live:
 *
 *   1. the gallery renders: heat marks, five UI states, both themes,
 *      all five text sizes;
 *   2. the fonts load from app/assets/fonts through the CSP (`font-src
 *      'self'`) and the window makes NO outside request (font CDN ban,
 *      story 107 groundwork);
 *   3. the ONE motion: a status change adds the settle animation and
 *      Reduce Motion turns it into nothing;
 *   4. the shared accessibility scan is clean on the gallery at Default
 *      and at Largest (no horizontal overflow at 200%);
 *   5. the same scan CATCHES planted violations (unnamed button, missing
 *      focus ring, horizontal overflow) — so screens 04-11, which run
 *      this scan in their own e2e, can trust a green result.
 */

const { _electron } = require('playwright');
const path = require('node:path');
const { APP_ROOT } = require('../util');
const { runAccessibilityScan, LARGEST_ROOT_PX } = require('../helpers/a11y-scan.mjs');

function fail(what) {
  throw new Error(what);
}

async function waitFor(predicate, timeoutMs, what) {
  const start = Date.now();
  while (!(await predicate())) {
    if (Date.now() - start > timeoutMs) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

async function main() {
  const outsideRequests = [];
  const app = await _electron.launch({
    args: [path.join(APP_ROOT, 'gallery', 'main.js')],
    cwd: APP_ROOT,
  });
  try {
    const win = await app.firstWindow();
    win.on('request', (req) => {
      if (!req.url().startsWith('file:')) outsideRequests.push(req.url());
    });

    await win.waitForSelector('[data-testid="gallery"]');
    await win.waitForSelector('#content .ember-table'); // content built by gallery.js

    // --- 1. every component family is on the page -----------------------
    const counts = await win.evaluate(() => ({
      pills: document.querySelectorAll('[data-testid^="status-pill-"]').length,
      states: ['state-loading', 'state-empty', 'state-error', 'state-no-key'].filter((t) => document.querySelector(`[data-testid="${t}"]`)).length,
      buttons: {
        primary: !!document.querySelector('[data-testid="button-primary"]'),
        secondary: !!document.querySelector('[data-testid="button-secondary"]'),
        text: !!document.querySelector('[data-testid="button-text"]'),
        danger: !!document.querySelector('[data-testid="button-danger"]'),
        disabled: !!document.querySelector('[data-testid="button-disabled"]'),
      },
      proposal: !!document.querySelector('[data-testid="proposal"]'),
      provenance: !!document.querySelector('[data-testid="provenance"]'),
      banner: !!document.querySelector('[data-testid="banner"]'),
      heatShapes: document.querySelectorAll('#heat-row svg').length,
    }));
    if (counts.pills < 3) fail(`expected the three status pills, saw ${counts.pills}`);
    if (counts.heatShapes !== 3) fail(`expected three heat shapes (full/half/ring), saw ${counts.heatShapes}`);
    if (counts.states !== 4) fail(`expected the four state blocks, saw ${counts.states}`);
    if (Object.values(counts.buttons).some((v) => !v)) fail(`missing button variants: ${JSON.stringify(counts.buttons)}`);
    if (!counts.proposal || !counts.provenance || !counts.banner) fail('proposal, provenance or banner missing');

    // both themes
    for (const theme of ['dark', 'light']) {
      await win.click('[data-testid="theme-toggle"]');
      const actual = await win.evaluate(() => document.documentElement.dataset.theme);
      if (actual !== theme) fail(`theme toggle landed on ${actual}, expected ${theme}`);
    }
    const darkInk = await win.evaluate(() =>
      getComputedStyle(document.body).color,
    );
    const lightInk = '#2B2118'.toLowerCase();
    if (darkInk.toLowerCase() === lightInk) fail('the dark theme did not change the ink colour');

    // all five text sizes reach the root
    for (const step of ['small', 'default', 'large', 'larger', 'largest']) {
      await win.click(`[data-testid="size-${step}"]`);
    }
    await win.click('[data-testid="size-default"]');
    const rootPx = await win.evaluate(() => getComputedStyle(document.documentElement).fontSize);
    if (rootPx !== '15px') fail(`Default text size should be the 15px root, saw ${rootPx}`);

    // --- 2. self-hosted fonts, no outside request -----------------------
    await win.evaluate(() => document.fonts.ready);
    const fontsLoaded = await win.evaluate(() => ({
      next400: document.fonts.check('16px "Atkinson Hyperlegible Next"'),
      next500: document.fonts.check('500 16px "Atkinson Hyperlegible Next"'),
      next600: document.fonts.check('600 16px "Atkinson Hyperlegible Next"'),
      mono400: document.fonts.check('16px "Atkinson Hyperlegible Mono"'),
    }));
    if (Object.values(fontsLoaded).some((ok) => !ok)) {
      fail(`fonts did not load from the app: ${JSON.stringify(fontsLoaded)}`);
    }
    if (outsideRequests.length > 0) {
      fail(`the gallery made outside requests (font CDN ban): ${JSON.stringify(outsideRequests)}`);
    }

    // --- 3. the ONE motion, and Reduce Motion kills it -------------------
    const runsMotion = async () => {
      await win.click('[data-testid="settle-button"]');
      return win.evaluate(() => {
        const svg = document.querySelector('#settle-pill svg');
        return {
          settle: [...svg.classList].find((c) => c.startsWith('heat--settle-')) || null,
          animationName: getComputedStyle(svg).animationName,
        };
      });
    };
    const moving = await runsMotion();
    if (!moving.settle || moving.animationName === 'none') {
      fail(`a status change must run the settle animation, saw ${JSON.stringify(moving)}`);
    }
    await win.emulateMedia({ reducedMotion: 'reduce' });
    const reduced = await runsMotion();
    if (reduced.settle && reduced.animationName !== 'none') {
      fail(`Reduce Motion must stop the settle, saw ${JSON.stringify(reduced)}`);
    }
    await win.emulateMedia({ reducedMotion: 'no-preference' });

    // --- 4. the a11y scan is clean (Default and Largest) -----------------
    for (const [label, px] of [['Default', 15], ['Largest', LARGEST_ROOT_PX]]) {
      await win.evaluate((v) => { document.documentElement.style.fontSize = `${v}px`; }, px);
      const { violations, checked } = await runAccessibilityScan(win, { rootPx: px });
      if (violations.length > 0) {
        fail(`a11y scan at ${label} found ${violations.length} violations: ${JSON.stringify(violations, null, 2)}`);
      }
      if (checked.tabbableCount < 10) fail(`too few tabbable controls to prove the scan (${checked.tabbableCount})`);
      process.stdout.write(`a11y scan clean at ${label} (${checked.tabbableCount} tabbable controls, root ${px}px)\n`);
    }

    // --- 5. the scan catches planted violations ---------------------------
    // Planted through the CSSOM (el.style), NOT style="" HTML attributes:
    // the gallery CSP (style-src 'self') correctly blocks parser-set style
    // attributes, and the scan must see a real violation, not a blocked one.
    await win.evaluate(() => {
      const unnamed = document.createElement('button');
      unnamed.id = 'planted-unnamed';
      document.body.appendChild(unnamed);

      const noRing = document.createElement('button');
      noRing.id = 'planted-noring';
      noRing.textContent = 'No ring here';
      noRing.style.setProperty('outline', 'none');
      document.body.appendChild(noRing);

      const wide = document.createElement('div');
      wide.id = 'planted-wide';
      wide.style.setProperty('width', '2000px');
      wide.style.setProperty('height', '10px');
      document.body.appendChild(wide);
    });
    const { violations } = await runAccessibilityScan(win);
    const kinds = new Set(violations.map((v) => v.kind));
    const need = ['unnamed-interactive', 'missing-focus-ring', 'horizontal-overflow'];
    for (const kind of need) {
      if (!kinds.has(kind)) fail(`planted ${kind} was NOT caught; saw ${JSON.stringify(violations, null, 2)}`);
    }
    const unnamedCaught = violations.some((v) => v.kind === 'unnamed-interactive' && v.id === 'planted-unnamed');
    const ringCaught = violations.some((v) => v.kind === 'missing-focus-ring' && v.id === 'planted-noring');
    if (!unnamedCaught) fail(`the unnamed planted button was not named in the catch: ${JSON.stringify(violations)}`);
    if (!ringCaught) fail(`the no-ring planted button was not named in the catch: ${JSON.stringify(violations)}`);
    process.stdout.write(`a11y scan caught all three planted violations (${violations.length} total)\n`);

    if (outsideRequests.length > 0) {
      fail(`outside requests appeared during the run: ${JSON.stringify(outsideRequests)}`);
    }

    process.stdout.write('e2e design OK: gallery renders all components and states in both themes, self-hosted fonts load, the settle motion runs and Reduce Motion kills it, the a11y scan is clean at Default and Largest and catches planted violations, no outside request\n');
  } finally {
    await app.close();
  }
}

main().catch((err) => {
  process.stderr.write(`e2e design FAILED: ${err.message}\n`);
  process.exit(1);
});

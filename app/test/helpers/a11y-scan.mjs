'use strict';

/**
 * Shared accessibility scan (L3 app step 03, plan §7 item 3).
 *
 * Scans a rendered screen (a Playwright page — Electron or browser) for:
 *   1. interactive elements without an accessible name,
 *   2. missing focus rings, by walking the screen with the TAB key like
 *      a keyboard user and reading the computed outline of each stop,
 *   3. horizontal overflow at the Largest text size (root 30px = 200%),
 *      both document-level scroll and clipped content.
 *
 * Every screen step (04 to 11) calls `runAccessibilityScan(page)` in its
 * OWN e2e and asserts zero violations (stories 96-104). The design e2e
 * (test/e2e/design.js) proves this helper catches planted violations.
 *
 * Dev-only code, one foot in the page world: `scanInPage` runs inside
 * the page (serialized by Playwright, no closures), the rest drives.
 */

const INTERACTIVE = 'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])';

export const LARGEST_ROOT_PX = 30; // the Largest text step (200% of Default)

/**
 * The in-page part. Pure DOM reading: names + overflow at whatever size
 * the page currently renders. Playwright evaluates it as-is.
 */
export function scanInPage() {
  const interactive = 'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])';

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  }

  function accessibleName(el) {
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const text = labelledby
        .split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((n) => n.textContent.trim())
        .join(' ');
      if (text) return text;
    }
    return (
      el.getAttribute('aria-label') ||
      (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? el.getAttribute('placeholder') : null) ||
      (el.textContent && el.textContent.trim()) ||
      el.getAttribute('title') ||
      el.getAttribute('value') ||
      ''
    );
  }

  function describe(el) {
    return {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      cls: (el.getAttribute('class') || '').slice(0, 80),
      html: el.outerHTML.slice(0, 120),
    };
  }

  const unnamed = [];
  const tabbables = [];
  document.querySelectorAll(interactive).forEach((el) => {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    if (!isVisible(el)) return;
    el.dataset.a11yScanIndex = String(tabbables.length);
    tabbables.push(el);
    if (!accessibleName(el)) unnamed.push(describe(el));
  });

  const overflow = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > doc.clientWidth) {
    overflow.push({ where: 'document', scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth });
  }
  document.querySelectorAll('*').forEach((el) => {
    const style = getComputedStyle(el);
    const clips = ['hidden', 'auto', 'scroll'].includes(style.overflowX);
    if (!clips || !isVisible(el)) return;
    if (el.scrollWidth > el.clientWidth + 1) {
      overflow.push({
        where: describe(el),
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      });
    }
  });

  return { unnamed, overflow, tabbableCount: tabbables.length };
}

/**
 * Read the computed focus ring of the focused element, in page. The
 * scan index (set by scanInPage) identifies the element across the walk.
 */
export function focusRingOfActive() {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const s = getComputedStyle(el);
  return {
    index: el.dataset?.a11yScanIndex,
    describe: {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      cls: (el.getAttribute('class') || '').slice(0, 80),
      html: el.outerHTML.slice(0, 120),
    },
    name: (el.textContent || '').trim().slice(0, 60) || el.getAttribute('aria-label') || null,
    outlineStyle: s.outlineStyle,
    outlineWidth: s.outlineWidth,
    outlineColor: s.outlineColor,
  };
}

/**
 * The driver every screen-step e2e calls. Returns the violation list
 * (empty = the screen passed) and how much was checked. The page is
 * temporarily switched to the Largest text size for the whole scan and
 * restored afterwards.
 */
export async function runAccessibilityScan(page, { rootPx = LARGEST_ROOT_PX } = {}) {
  await page.evaluate((px) => {
    document.documentElement.dataset.a11yScanPrevSize = document.documentElement.style.fontSize;
    document.documentElement.style.fontSize = `${px}px`;
  }, rootPx);
  await page.waitForTimeout(120); // let rem-based layout reflow

  const { unnamed, overflow, tabbableCount } = await page.evaluate(scanInPage);

  // Keyboard walk: TAB through the screen like a keyboard user and read
  // the ring of every stop (chromium flips :focus-visible on real keys).
  const missingFocusRing = [];
  const visited = new Set();
  for (let i = 0; i < tabbableCount + 1 && visited.size < tabbableCount; i += 1) {
    await page.keyboard.press('Tab');
    const ring = await page.evaluate(focusRingOfActive);
    if (!ring || ring.index === undefined) break; // body: end of the tab order
    if (visited.has(ring.index)) break; // a focus cycle: every stop covered
    visited.add(ring.index);
    // an absent ring: style 'none' (its reported used width means nothing),
    // or a zero-width outline
    if (ring.outlineStyle === 'none' || !(parseFloat(ring.outlineWidth) > 0)) {
      missingFocusRing.push(ring.describe);
    }
  }

  await page.evaluate(() => {
    const prev = document.documentElement.dataset.a11yScanPrevSize;
    if (prev === undefined) delete document.documentElement.style.fontSize;
    else document.documentElement.style.fontSize = prev;
    delete document.documentElement.dataset.a11yScanPrevSize;
    document.querySelectorAll('[data-a11y-scan-index]').forEach((el) => delete el.dataset.a11yScanIndex);
    document.activeElement && document.activeElement.blur();
  });

  const violations = [
    ...unnamed.map((what) => ({ kind: 'unnamed-interactive', ...what })),
    ...missingFocusRing.map((what) => ({ kind: 'missing-focus-ring', ...what })),
    ...overflow.map((what) => ({ kind: 'horizontal-overflow', ...what })),
  ];
  return { violations, checked: { tabbableCount, atRootPx: rootPx } };
}

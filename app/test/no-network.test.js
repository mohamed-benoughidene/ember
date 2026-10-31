'use strict';

/**
 * Story 107 (step 13): the app makes no network request of its own —
 * the only network use is `ember` talking to the AI service the user
 * chose. The e2e (test/e2e/no-network.js) observes the live app; these
 * are the STATIC halves that cannot drift silently:
 *  - every window carries a content-security policy with NO outside
 *    origin (plan §5.8);
 *  - no auto-update, no crash reporting, no Electron net requests
 *    anywhere in the app code.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');

const WINDOWS = ['index.html', 'quick.html', 'gallery.html'];
const CODE_DIRS = ['main', 'preload', 'shared', 'renderer'];

function read(...parts) {
  return fs.readFileSync(path.join(APP_ROOT, ...parts), 'utf8');
}

function cspOf(htmlFile) {
  const html = read('renderer', htmlFile);
  const match = html.match(/<meta[^>]*http-equiv="Content-Security-Policy"[^>]*content="([^"]*)"/);
  assert.ok(match, `${htmlFile} does not carry a content-security-policy meta tag`);
  return match[1];
}

test('every window ships a content-security policy', () => {
  for (const window of WINDOWS) cspOf(window); // the parser asserts presence
});

for (const window of WINDOWS) {
  test(`CSP of ${window} names no outside origin`, () => {
    const csp = cspOf(window);
    const sources = csp.split(';').flatMap((directive) => directive.trim().split(/\s+/).slice(1));
    const outside = sources.filter((s) => /^https?:\/\//.test(s) || /\b[a-z0-9.-]+\.(com|net|org|io|dev)\b/i.test(s));
    assert.deepEqual(outside, [], `${window}'s CSP allows outside hosts: ${outside.join(', ')}`);
    assert.ok(csp.includes("'self'"), `${window}'s CSP must keep 'self'`);
  });
}

for (const token of ['autoUpdater', 'setFeedURL', 'crashReporter', 'net.request']) {
  test(`no ${token} anywhere in the app code (no auto-update, no app-side requests)`, () => {
    const hits = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(p);
        else if (/\.(js|mjs|html|css)$/.test(entry.name)) {
          const text = fs.readFileSync(p, 'utf8');
          if (text.includes(token)) hits.push(path.relative(APP_ROOT, p));
        }
      }
    };
    for (const dir of CODE_DIRS) walk(path.join(APP_ROOT, dir));
    assert.deepEqual(hits, [], `${token} found in: ${hits.join(', ')}`);
  });
}

test('no http(s) URL in the app code outside the documented words (font CDN ban, plan §8)', () => {
  // Allowed: comments/names that only SAY https (options, licence
  // pointers must stay in docs/, not code). What must never exist is a
  // fetch/load from an outside host in renderer/preload code.
  const hits = [];
  const consider = (file, text) => {
    const rendererOrPreload = file.includes(`${path.sep}renderer${path.sep}`) || file.includes(`${path.sep}preload${path.sep}`);
    if (!rendererOrPreload) return;
    const matches = text.match(/https?:\/\/[^"'\s)>]+/g) ?? [];
    for (const m of matches) {
      if (m.includes('www.w3.org')) continue; // SVG namespace constants, never fetched
      hits.push(`${path.relative(APP_ROOT, file)}: ${m}`);
    }
  };
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (/\.(js|mjs|html|css)$/.test(entry.name)) consider(p, fs.readFileSync(p, 'utf8'));
    }
  };
  walk(path.join(APP_ROOT, 'renderer'));
  walk(path.join(APP_ROOT, 'preload'));
  assert.deepEqual(hits, [], `outside URLs referenced in renderer/preload: ${hits.join(', ')}`);
});

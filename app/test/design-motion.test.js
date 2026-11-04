'use strict';

/**
 * The one motion (L3 app step 03): the heat mark settles on a status
 * change — ~250 ms, transform and opacity only, nothing on first
 * render, and fully off under Reduce Motion (CSS media rule). Node
 * tests pin the pure classifier and the stylesheet's shape; the
 * behavioural proof (animation actually runs / is killed) lives in
 * test/e2e/design.js on the live gallery.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ROOT } = require('./util');

const css = fs.readFileSync(path.join(APP_ROOT, 'renderer', 'styles', 'components.css'), 'utf8');
const { heatMarkHtml, settleClass, HEAT_STATUSES } = require('../renderer/components/heat-mark.mjs');

test('motion: settles only on a real status change', () => {
  assert.equal(settleClass(null, 'Active'), '', 'first render never animates (nothing animates on load)');
  assert.equal(settleClass(null, 'Challenged'), '');
  assert.equal(settleClass(null, 'Closed'), '');
  assert.equal(settleClass('Active', 'Active'), '', 'same-to-same never animates (nothing on revisit)');
  assert.equal(settleClass('Active', 'Challenged'), 'heat--settle-half');
  assert.equal(settleClass('Challenged', 'Closed'), 'heat--settle-cool');
  assert.equal(settleClass('Closed', 'Active'), 'heat--settle-heat');
  assert.throws(() => settleClass('Active', 'Nonexistent'));
});

test('motion: first render has no settle class in the markup', () => {
  const html = heatMarkHtml('Active');
  assert.match(html, /class="heat"/);
  assert.doesNotMatch(html, /settle/);
  const challenged = heatMarkHtml('Challenged', { settle: 'heat--settle-half' });
  assert.match(challenged, /heat--settle-half/);
});

test('motion: three keyframes, transform and opacity ONLY', () => {
  const names = ['heat-settle-heat', 'heat-settle-half', 'heat-settle-cool'];
  for (const name of names) {
    const block = css.match(new RegExp(`@keyframes ${name} \\{([\\s\\S]*?)\\n\\}`));
    assert.ok(block, `@keyframes ${name} exists in components.css`);
    const props = [...block[1].matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
    assert.deepEqual([...new Set(props)].sort(), ['opacity', 'transform'], `${name} moves transform/opacity only, saw ${props}`);
  }
});

test('motion: durations about 250 ms (240-260 ms)', () => {
  const durations = [...css.matchAll(/animation:\s*(heat-settle-[a-z]+)\s+([\d.]+)s/g)];
  assert.equal(durations.length, 3, 'each settle class declares exactly one animation');
  for (const [, name, seconds] of durations) {
    const ms = Number(seconds) * 1000;
    assert.ok(ms >= 240 && ms <= 260, `${name} is ${ms} ms, expected ~250`);
  }
});

test('motion: Reduce Motion turns the settle off in CSS', () => {
  const media = css.match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/);
  assert.ok(media, 'a prefers-reduced-motion block exists');
  for (const cls of ['heat--settle-heat', 'heat--settle-half', 'heat--settle-cool']) {
    assert.ok(media[0].includes(cls), `the reduce block names ${cls}`);
  }
  const body = media[0].split('{').slice(1).join('{');
  assert.match(body, /animation:\s*none\s*!important/, 'the reduce block kills the animations');
});

test('motion: the statuses are exactly the three of the heat rule', () => {
  assert.deepEqual(HEAT_STATUSES, ['Active', 'Challenged', 'Closed']);
});

'use strict';

/**
 * Component contracts (L3 app step 03, step file §1 "fixed contracts"):
 * HeatMark, StatusPill, StateBlock (all four renderable states), Button,
 * Banner, ProvenanceLine, ItemRow, ProposalBlock. Pure HTML-string
 * contracts, unit tested in node without a DOM; the live page proof is
 * test/e2e/design.js.
 */

const test = require('node:test');
const assert = require('node:assert/strict');

const { heatMarkHtml, settleClass } = require('../renderer/components/heat-mark.mjs');
const { statusPillHtml, HEAT_STATUSES: PILL_STATUSES } = require('../renderer/components/status-pill.mjs');
const { stateBlockHtml, STATE_KINDS, loadingHtml, emptyHtml, errorHtml, noKeyHtml } = require('../renderer/components/state-block.mjs');
const { buttonHtml, BUTTON_VARIANTS } = require('../renderer/components/button.mjs');
const { bannerHtml } = require('../renderer/components/banner.mjs');
const { provenanceListHtml, PROVENANCE_LABELS } = require('../renderer/components/provenance-line.mjs');
const { itemRowHtml, itemTableHtml } = require('../renderer/components/item-row.mjs');
const { proposalBlockHtml, PROPOSAL_TYPES } = require('../renderer/components/proposal-block.mjs');

test('heat mark: one shape per status, each with an accessible name', () => {
  const active = heatMarkHtml('Active');
  assert.match(active, /role="img"/);
  assert.match(active, /aria-label="Active"/);
  assert.match(active, /<circle[^>]*fill="var\(--heat\)"\/>/, 'Active is the full dot');

  const challenged = heatMarkHtml('Challenged');
  assert.match(challenged, /aria-label="Challenged"/);
  assert.match(challenged, /stroke="var\(--heat\)"/, 'Challenged: outlined half');
  assert.match(challenged, /<path [^>]*fill="var\(--heat\)"/, 'Challenged: the half fill on top of the ring');

  const closed = heatMarkHtml('Closed');
  assert.match(closed, /aria-label="Closed"/);
  assert.match(closed, /fill="none"/, 'Closed is the empty ring');
  assert.doesNotMatch(closed, /var\(--heat\)/, 'Closed carries no heat colour (ash)');

  assert.equal(new Set(PILL_STATUSES).size, 3);
  assert.throws(() => heatMarkHtml('Deleted'), /unknown heat status/);
});

test('status pill: the mark followed by the word', () => {
  for (const s of ['Active', 'Challenged', 'Closed']) {
    const html = statusPillHtml(s);
    assert.match(html, new RegExp(`aria-label="${s}">.*</svg><span class="st__word">${s}</span>`), `${s}: mark then word`);
  }
});

test('button: four variants, the label is required, disabled keeps a reason', () => {
  assert.deepEqual(BUTTON_VARIANTS, ['primary', 'secondary', 'text', 'danger']);
  const primary = buttonHtml({ label: 'Add text', variant: 'primary', action: 'add-text' });
  assert.match(primary, /class="btn btn--primary"/);
  assert.match(primary, /data-action="add-text"/);
  assert.match(buttonHtml({ label: 'Go', variant: 'secondary' }), /^<button type="button" class="btn"/);
  assert.match(buttonHtml({ label: 'Details', variant: 'text' }), /class="btn btn--text"/);
  assert.match(buttonHtml({ label: 'Close item 3', variant: 'danger' }), /class="btn btn--danger"/);
  const disabled = buttonHtml({ label: 'Add text — needs the AI key first', disabled: '', title: 'why' });
  assert.match(disabled, /disabled/);
  assert.match(disabled, /needs the AI key first/, 'a disabled control says why in its own label');
  assert.throws(() => buttonHtml({ variant: 'primary' }), /label/);
  assert.throws(() => buttonHtml({ label: 'x', variant: 'mega' }), /unknown button variant/);
});

test('state block: the four renderable states of the five-state helper', () => {
  assert.deepEqual(STATE_KINDS, ['loading', 'empty', 'error', 'noKey']);

  const loading = stateBlockHtml('loading');
  assert.match(loading, /data-testid="state-loading"/);
  assert.match(loading, /role="status"/);
  assert.match(loading, /class="skel"/, 'grey bars at real size');

  const empty = stateBlockHtml('empty', { title: 'Nothing here yet.' });
  assert.match(empty, /data-testid="state-empty"/);
  assert.match(empty, /Nothing here yet\./);

  const error = stateBlockHtml('error', { detail: 'APP-008 BridgeTimeout: no answer in time.' });
  assert.match(error, /data-testid="state-error"/);
  assert.match(error, /role="alert"/);
  assert.match(error, /data-action="retry"/, 'error carries Retry');
  assert.match(error, /data-action="show-details"/, 'error carries Details');
  assert.match(error, /APP-008 BridgeTimeout/);
  assert.match(errorHtml({ detail: 'boom' }), /boom/);

  const noKey = stateBlockHtml('noKey', { what: 'Adding text' });
  assert.match(noKey, /data-testid="state-no-key"/);
  assert.match(noKey, /needs the AI connection/);
  assert.match(noKey, /data-action="open-settings"/);
  assert.match(noKey, /btn--primary/, 'the one main action points at Settings');

  assert.throws(() => stateBlockHtml('planting'), /unknown state kind/);
});

test('banner: text required, optional one action', () => {
  assert.match(bannerHtml({ text: 'Saved.' }), />Saved\./);
  const withAction = bannerHtml({ text: 'Repaired.', actionLabel: 'Review', action: 'review' });
  assert.match(withAction, /role="note"/);
  assert.match(withAction, /data-action="review"/);
  assert.throws(() => bannerHtml({}), /text/);
});

test('provenance: label column + value column, the five DESIGN.md labels', () => {
  assert.deepEqual(PROVENANCE_LABELS, ['Source', 'Why', 'Challenged by', 'Replaced by', 'Answered by']);
  const html = provenanceListHtml([
    ['Source', 'Architecture chat, 3 Oct'],
    ['Challenged by', 'item 5 (contradicts)'],
  ]);
  assert.match(html, /class="k">Source</);
  assert.match(html, /class="v">Architecture chat, 3 Oct</);
  assert.match(html, /Challenged by</);
  assert.throws(() => provenanceListHtml('nope'));
});

test('item row: mono number, escaped text, status pill; no zebra classes', () => {
  const row = itemRowHtml({ id: 5, text: 'Two people <edited> the file.', status: 'Challenged' });
  assert.match(row, /<td class="num dim">5<\/td>/);
  assert.match(row, /Two people &lt;edited&gt; the file\./, 'item text is escaped');
  assert.match(row, /status-pill-challenged/);
  const table = itemTableHtml([{ id: 1, text: 'A', status: 'Active' }, { id: 2, text: 'B', status: 'Closed' }]);
  assert.match(table, /<thead>/);
  assert.match(table, /item-row-1/);
  assert.match(table, /item-row-2/);
  assert.doesNotMatch(table, /zebra|striped/);
});

test('proposal block: the four-button order Stop, Edit, Reject, Confirm', () => {
  const html = proposalBlockHtml({
    type: 'Decision',
    statement: 'Use SQLite for local storage.',
    quote: 'We decided to use SQLite for local storage.',
    warn: 'Looks similar to item 1.',
  });
  const order = [...html.matchAll(/data-action="proposal-([a-z-]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ['stop', 'edit', 'reject', 'confirm']);
  assert.match(html, /kbd">Esc</);
  assert.match(html, /kbd">e</);
  assert.match(html, /kbd">n</);
  assert.match(html, /kbd">Return</);
  assert.match(html, /data-testid="proposal-warn">Looks similar to item 1\./);
  assert.match(html, /class="quote">We decided to use SQLite/);
  assert.deepEqual(PROPOSAL_TYPES, ['Decision', 'Assumption', 'Finding', 'Question']);
  assert.throws(() => proposalBlockHtml({ type: 'Rumour', statement: 'x' }), /unknown proposal type/);
});

test('components stay framework-free: no imports beyond the design layer', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const dir = path.join(__dirname, '..', 'renderer', 'components');
  for (const f of fs.readdirSync(dir)) {
    const src = fs.readFileSync(path.join(dir, f), 'utf8');
    assert.doesNotMatch(src, /require\(/, `${f}: no CJS require in the renderer`);
    for (const m of src.matchAll(/from '([^']+)'/g)) {
      assert.match(m[1], /^(\.\.?(\/design|\/components)?\/)/, `${f} imports only design-layer modules, saw ${m[1]}`);
    }
  }
});

/*
 * The gallery script (dev-only). Builds every component in every state
 * from the design components, with a theme toggle and the five text
 * sizes, so the founder can look at all of it (step file §3) and the
 * e2e design check can drive the same page.
 *
 * The one motion lives here too: the "heat settles" demo re-renders a
 * status pill on a status change, which is the only time a mark moves.
 */

import { HEAT_STATUSES } from './components/heat-mark.mjs';
import { statusPillHtml, renderStatusPill } from './components/status-pill.mjs';
import { buttonHtml } from './components/button.mjs';
import { bannerHtml } from './components/banner.mjs';
import { provenanceListHtml } from './components/provenance-line.mjs';
import { itemTableHtml } from './components/item-row.mjs';
import { proposalBlockHtml } from './components/proposal-block.mjs';
import { stateBlockHtml, bindStateBlock, errorHtml } from './components/state-block.mjs';
import { TEXT_STEPS, textStepNames } from './design/text-scale.mjs';

const content = document.querySelector('#content');
const root = document.documentElement;

/* ---------- the demo bar: theme + text size + re-run motion ---------- */

const themeToggle = document.querySelector('[data-testid="theme-toggle"]');
themeToggle.addEventListener('click', () => {
  const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
  root.dataset.theme = next;
  themeToggle.textContent = `Colours: ${next}`;
});

for (const step of textStepNames()) {
  document.querySelector(`[data-testid="size-${step.toLowerCase()}"]`).addEventListener('click', () => {
    root.style.fontSize = `${TEXT_STEPS[step]}px`;
  });
}

/* ---------- sections ---------- */

const heatRow = HEAT_STATUSES.map((s) => statusPillHtml(s)).join('');

content.innerHTML = `
  <h2>The heat mark</h2>
  <p class="hint">Full dot Active, half dot Challenged, ring Closed. The word always follows.</p>
  <p id="heat-row" data-testid="heat-row">${heatRow}</p>

  <h2>The one motion</h2>
  <p class="hint">A heat mark settles when its item's status changes — and never on load.</p>
  <p data-testid="settle-demo"><span id="settle-pill"></span></p>
  ${buttonHtml({ label: 'Change item 5: Active, then Challenged, then Closed', action: 'settle-cycle', variant: 'secondary', testid: 'settle-button' })}

  <h2>Buttons</h2>
  <div class="actions">
    ${buttonHtml({ label: 'Add text', action: 'demo-primary', variant: 'primary', testid: 'button-primary' })}
    ${buttonHtml({ label: 'Preview the sweep', action: 'demo-secondary', variant: 'secondary', testid: 'button-secondary' })}
    ${buttonHtml({ label: 'View the whole ledger', action: 'demo-text', variant: 'text', testid: 'button-text' })}
    ${buttonHtml({ label: 'Close item 3, superseded', action: 'demo-danger', variant: 'danger', testid: 'button-danger' })}
    ${buttonHtml({ label: 'Add text — needs the AI key first', variant: 'secondary', disabled: '', title: 'Set up the AI connection in Settings first', testid: 'button-disabled' })}
  </div>

  <h2>Banner</h2>
  ${bannerHtml({ text: 'Settings were repaired: the text size was not readable, so Default was used.', actionLabel: 'Review', action: 'demo-banner' })}

  <h2>Provenance</h2>
  ${provenanceListHtml([
    ['Source', 'Architecture chat, 3 Oct'],
    ['Why', 'Ember needs no server of its own.'],
    ['Challenged by', 'item 5 (contradicts)'],
    ['Replaced by', 'item 6'],
    ['Answered by', 'item 6'],
  ])}

  <h2>Item rows</h2>
  ${itemTableHtml([
    { id: 1, text: 'Use SQLite for local storage.', status: 'Active' },
    { id: 5, text: 'Two people edited the file on Monday.', status: 'Challenged' },
    { id: 7, text: 'Keep notes in a cloud database.', status: 'Closed' },
  ])}

  <h2>Proposal block</h2>
  ${proposalBlockHtml({
    type: 'Decision',
    statement: 'Use SQLite for local storage.',
    quote: 'We decided to use SQLite for local storage.',
    warn: 'Looks similar to item 1. Confirm it only if it adds something.',
  })}

  <h2>The five UI states</h2>
  <div class="gallery-grid">
    <div>
      <p class="label-sample">Normal</p>
      <p class="hint">The regular screen frame — content shows, no state block. Every other state below replaces only the answer area.</p>
    </div>
    <div>
      <p class="label-sample">Loading</p>
      <div id="state-loading"></div>
    </div>
    <div>
      <p class="label-sample">Empty</p>
      <div id="state-empty"></div>
    </div>
    <div>
      <p class="label-sample">Error</p>
      <div id="state-error"></div>
      <div class="details-out" id="error-details" data-testid="error-details" hidden>APP-008 BridgeTimeout: the AI service did not answer within its time limit. Your text is kept as a Source.</div>
    </div>
    <div>
      <p class="label-sample">No-key</p>
      <div id="state-no-key"></div>
    </div>
  </div>
`;

/* ---------- the state blocks render + wire ---------- */

document.querySelector('#state-loading').innerHTML = stateBlockHtml('loading');
document.querySelector('#state-empty').innerHTML = stateBlockHtml('empty', {
  title: 'Ember found nothing in this text. The text is kept as a Source.',
});
document.querySelector('#state-error').innerHTML = stateBlockHtml('error', {
  title: "Couldn't reach the AI service.",
  detail: 'APP-008 BridgeTimeout: the service did not answer within its time limit.',
  why: 'Your text is saved as a Source. No items were created. Last attempt just now.',
});
document.querySelector('#state-no-key').innerHTML = stateBlockHtml('noKey', { what: 'Adding text' });

bindStateBlock(content, {
  retry: () => {},
  'show-details': () => {
    const box = document.querySelector('[data-testid="error-details"]');
    box.hidden = !box.hidden;
  },
  'open-settings': () => {},
  'proposal-stop': () => {},
  'proposal-edit': () => {},
  'proposal-reject': () => {},
  'proposal-confirm': () => {},
  'demo-primary': () => {},
  'demo-secondary': () => {},
  'demo-text': () => {},
  'demo-danger': () => {},
  'demo-banner': () => {},
});

/* ---------- the settle motion, driven by a real status change ---------- */

const DEMO_CYCLE = ['Active', 'Challenged', 'Closed'];
let demoIndex = 0;
const settleHost = document.querySelector('#settle-pill');

function showSettle(from, to) {
  renderStatusPill(settleHost, to, { fromStatus: from, animate: true });
}

showSettle(null, 'Active'); // first render: no motion (Motion rule)

document.querySelector('[data-testid="settle-button"]').addEventListener('click', () => {
  const from = DEMO_CYCLE[demoIndex % DEMO_CYCLE.length];
  demoIndex += 1;
  const to = DEMO_CYCLE[demoIndex % DEMO_CYCLE.length];
  showSettle(from, to);
});

// The demo bar's "again" button replays the exact change last shown.
document.querySelector('[data-testid="motion-again"]').addEventListener('click', () => {
  const to = DEMO_CYCLE[demoIndex % DEMO_CYCLE.length];
  const from = DEMO_CYCLE[(demoIndex + DEMO_CYCLE.length - 1) % DEMO_CYCLE.length];
  showSettle(from, to);
});

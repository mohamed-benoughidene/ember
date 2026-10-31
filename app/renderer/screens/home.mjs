/**
 * Home (app step file §1, spec stories 10-15): attention first (10),
 * counts per status and total straight from `list-items` (11-12, D3:
 * never recomputed), the latest ledger lines (13), the main "Add text"
 * button (14), and a button on the attention message to the fix or the
 * sweep (15). Every block sits in a step-03 state component: loading,
 * empty, error with Retry and Details — no bare code on screen.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { bannerHtml } from '../components/banner.mjs';
import { emptyHtml } from '../components/state-block.mjs';
import { historyEventSentence } from '../../shared/plain-sentences.mjs';
import { showErrorBlock, showLoadingBlock, dataOrNull } from './blocks.mjs';

const COUNT_PAGE_SIZE = 1; // totals ride the envelope; the page content is not needed
const LEDGER_LIMIT = 5;

export function createHomeScreen(ctx) {
  const blocks = {
    attention: null,
    counts: null,
    ledger: null,
    gate: null,
  };
  let rootEl = null;
  let noKey = null;
  let kbGate = 'reading'; // 'ok' | 'nosuch' | 'invalid' | 'reading'

  async function load() {
    await Promise.all([loadGate(), loadKeyStatus()]);
  }

  async function loadKeyStatus() {
    const status = await ctx.api.keyStatus();
    noKey = !(status && (status.stored || status.sessionOnly));
    renderNotice();
  }
  /**
   * The knowledge-base gate (app step file §1): until the first Add the
   * file does not exist — the empty state shows WITHOUT calling any
   * read command. An existing file must be an Ember file (APP-006).
   */
  async function loadGate() {
    const status = await ctx.api.kbStatus();
    if (!status.exists) {
      kbGate = 'nosuch';
      renderGate();
      return;
    }
    if (!status.looksValid) {
      kbGate = 'invalid';
      renderGate();
      return;
    }
    kbGate = 'ok';
    renderGate();
    await Promise.all([loadAttention(), loadCounts(), loadLedger()]);
  }

  function renderNotice() {
    const host = rootEl ? rootEl.querySelector('[data-testid="home-notice"]') : null;
    if (!host) return;
    host.innerHTML =
      noKey && kbGate !== 'reading'
        ? bannerHtml({
            text: 'Ember has no AI key yet. Add and Link items wait for one. You can look around meanwhile.',
            actionLabel: 'Set up the AI connection',
            action: 'home-setup-key',
          })
        : '';
    host.querySelector('[data-action="home-setup-key"]')?.addEventListener('click', () => ctx.openSetup());
  }

  function renderGate() {
    const host = blocks.gate();
    renderNotice();
    if (kbGate === 'invalid') {
      showErrorBlock(host, { code: 'APP-006', name: 'KnowledgeBaseMissing', where: 'home', detail: 'the chosen knowledge base file is not an Ember file' }, {
        what: kbGate,
        onRetry: () => load(),
      });
      return;
    }
    if (kbGate === 'nosuch') {
      host.innerHTML = emptyHtml({
        title: 'No items yet. Your knowledge base file is created the first time you add text.',
        next: 'Add your first text',
        onNext: 'home-add',
      });
      host.querySelector('[data-action="home-add"]')?.addEventListener('click', () => ctx.navigate('add'));
      rootEl.querySelector('[data-testid="home-counts"]').innerHTML = '';
      rootEl.querySelector('[data-testid="attention"]').innerHTML = '';
      rootEl.querySelector('[data-testid="home-ledger"]').innerHTML = '';
    }
  }

  /** Stories 10 + 15: what needs attention first, with the way to act. */
  async function loadAttention() {
    const host = blocks.attention();
    showLoadingBlock(host, 'Checking what needs attention…');
    const challenged = await ctx.api.listItems({ status: 'Challenged', limit: COUNT_PAGE_SIZE, offset: 0 });
    const challengedData = dataOrNull(host, challenged, { what: 'attention', onRetry: loadAttention });
    if (challengedData === null) return;
    const challengedCount = challengedData.total;
    const live = await ctx.api.currentState();
    const stateData = dataOrNull(host, live, { what: 'attention', onRetry: loadAttention });
    if (stateData === null) return;
    const firstChallenged = stateData.items.find((it) => it.challenged === true) ?? null;
    // maintainDryRun answers {ok, pending} in its own shape.
    const sweep = await ctx.api.maintainDryRun();
    if (!sweep || !sweep.ok) {
      showErrorBlock(host, sweep ? sweep.error : null, { what: 'attention', onRetry: loadAttention });
      return;
    }
    const pendingCount = sweep.pending;
    if (pendingCount > 0) {
      host.innerHTML = `<div class="finding" data-testid="attention-finding"><div class="grow">
        <strong>${pendingCount} ${pendingCount === 1 ? 'item is' : 'items are'} out of date.</strong>
        <span>The links say their status should change. A sweep updates them. Nothing changes until you apply it.</span></div>
        ${buttonHtml({ label: 'Preview the sweep', action: 'attention-cleanup', variant: 'secondary' })}</div>`;
      host.querySelector('[data-action="attention-cleanup"]')?.addEventListener('click', () => ctx.navigate('cleanup'));
      return;
    }
    if (challengedCount > 0) {
      const name = firstChallenged ? `, "${firstChallenged.statement}"` : '';
      const idText = firstChallenged ? `Item ${firstChallenged.id}${name}` : 'A challenged item';
      host.innerHTML = `<div class="finding" data-testid="attention-finding"><div class="grow">
        <strong>${challengedCount} ${challengedCount === 1 ? 'item needs' : 'items need'} a second look.</strong>
        <span>${esc(idText)} is Challenged. Fix and close marks it Active or Closed.</span></div>
        ${buttonHtml({ label: 'Fix and close', action: 'attention-fix', variant: 'secondary' })}</div>`;
      host.querySelector('[data-action="attention-fix"]')?.addEventListener('click', () => ctx.navigate('fix'));
      return;
    }
    host.innerHTML = `<div class="finding" data-testid="attention-finding"><div class="grow">
      <strong>Nothing needs attention.</strong><span>Every status matches its links.</span></div></div>`;
  }

  /** Stories 11-12: counts per status and total, from list-items only. */
  async function loadCounts() {
    const host = blocks.counts();
    showLoadingBlock(host, 'Counting the items…');
    const [all, active, challenged, closed] = await Promise.all([
      ctx.api.listItems({ limit: COUNT_PAGE_SIZE, offset: 0 }),
      ctx.api.listItems({ status: 'Active', limit: COUNT_PAGE_SIZE, offset: 0 }),
      ctx.api.listItems({ status: 'Challenged', limit: COUNT_PAGE_SIZE, offset: 0 }),
      ctx.api.listItems({ status: 'Closed', limit: COUNT_PAGE_SIZE, offset: 0 }),
    ]);
    const results = { all, active, challenged, closed };
    for (const [name, result] of Object.entries(results)) {
      if (!result.ok) {
        showErrorBlock(host, result.error, { what: `the ${name} count`, onRetry: loadCounts });
        return;
      }
    }
    host.innerHTML = `<div class="panel split" data-testid="counts-panel" aria-label="Items by status">
      <div><span class="lbl-pill">Active</span><div class="fig" data-testid="count-active">${active.data.total}</div></div>
      <div><span class="lbl-pill">Challenged</span><div class="fig" data-testid="count-challenged">${challenged.data.total}</div></div>
      <div><span class="lbl-pill">Closed</span><div class="fig" data-testid="count-closed">${closed.data.total}</div></div>
      <div><span class="lbl-pill">All items</span><div class="fig" data-testid="count-total">${all.data.total}</div></div>
    </div>`;
  }

  /** Story 13: the latest ledger lines, from `history --limit`. */
  async function loadLedger() {
    const host = blocks.ledger();
    showLoadingBlock(host, 'Reading the latest ledger lines…');
    const result = await ctx.api.history({ limit: LEDGER_LIMIT, offset: 0 });
    const data = dataOrNull(host, result, { what: 'the latest ledger lines', onRetry: loadLedger });
    if (data === null) return;
    const events = data.events ?? [];
    if (events.length === 0) {
      host.innerHTML = emptyHtml({ title: 'The ledger is empty. Every change you make is written here.' });
      return;
    }
    const rows = events
      .map(
        (e) =>
          `<tr><td class="dim" class="nowrap">${esc(e.timestamp ?? '')}</td><td>${esc(historyEventSentence(e))}</td></tr>`,
      )
      .join('');
    host.innerHTML = `<div class="panel"><table data-testid="home-ledger-table"><tbody>${rows}</tbody></table></div>
      <div class="actions">${buttonHtml({ label: 'View the whole ledger', action: 'ledger-all', variant: 'text' })}</div>`;
    host.querySelector('[data-action="ledger-all"]')?.addEventListener('click', () => ctx.navigate('lookup', { tab: 'ledger' }));
  }

  function render() {
    ctx.renderFrame(
      `<div data-testid="home-pane">
        <div class="titlerow"><div class="grow"><h1>Home</h1>
          <p class="sub">What this knowledge base knows right now.</p></div>
          ${buttonHtml({ label: 'Add text', action: 'home-add-main', variant: 'primary', testid: 'home-add' })}
        </div>
        <div data-testid="home-notice"></div>
        <div data-testid="kb-gate"></div>
        <div data-testid="attention"></div>
        <div data-testid="home-counts"></div>
        <h2>Latest in the ledger</h2>
        <div data-testid="home-ledger"></div>
      </div>`,
      (root) => {
        rootEl = root;
        root.querySelector('[data-action="home-add-main"]')?.addEventListener('click', () => ctx.navigate('add'));
        blocks.attention = () => root.querySelector('[data-testid="attention"]');
        blocks.counts = () => root.querySelector('[data-testid="home-counts"]');
        blocks.ledger = () => root.querySelector('[data-testid="home-ledger"]');
        blocks.gate = () => root.querySelector('[data-testid="kb-gate"]');
        load();
      },
    );
  }

  return { render, load };
}

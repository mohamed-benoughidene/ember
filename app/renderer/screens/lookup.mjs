/**
 * Look up (app step file §1, spec stories 30-41 and 122): search box
 * with a visible label (30), status/type filters (31), the match count
 * (32), the item table with number, type, text and heat mark (33),
 * selecting an item for its provenance via `show-item` (34-36), the
 * Ledger tab with filtering and paging (37-38), "Clear filters" when
 * nothing matches (39), the "No items yet" empty state (40), and the
 * loading/error states with Retry (41). Ledger kinds read their plain
 * words ("Undone", "Redone") from the shared sentence table (122).
 *
 * Commands, exactly as the contract table pins them: no query ->
 * `list-items --status --type --limit --offset`; a query ->
 * `topic-search --query --status --type --limit` (the command has no
 * --offset); a selection -> `show-item --item N`; the Ledger ->
 * `history --item --limit --offset --since`.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { statusPillHtml } from '../components/status-pill.mjs';
import { emptyHtml, stateBlockHtml } from '../components/state-block.mjs';
import { historyEventSentence, historyKindLabel, humanLinkType } from '../../shared/plain-sentences.mjs';
import { showErrorBlock, showLoadingBlock, dataOrNull } from './blocks.mjs';

const PAGE_SIZE = 50;
const LEDGER_PAGE_SIZE = 10;
const NO_STATUS = 'Any status';
const NO_TYPE = 'Any type';

/** Provenance labels per link type and direction (approved prototype, story 36). */
const LINK_LABELS_OUT = {
  contradicts: 'Challenges',
  supersedes: 'Replaces',
  answers: 'Answers',
  depends_on: 'Depends on',
  supports: 'Supports',
};
const LINK_LABELS_IN = {
  contradicts: 'Challenged by',
  supersedes: 'Replaced by',
  answers: 'Answered by',
  depends_on: 'Needed by',
  supports: 'Supported by',
};

export function createLookupScreen(ctx) {  const view = {
    tab: (ctx.params && ctx.params.tab) || 'items',
    q: '',
    status: null,
    type: null,
    offset: 0,
    selectedItem: null,
    detail: { state: 'idle' },
    ledger: { item: null, sinceText: '', offset: 0 },
  };

  function render() {
    ctx.renderFrame(
      `<div data-testid="lookup-pane">
        <div class="titlerow"><div class="grow"><h1>Look up</h1>
          <p class="sub">Find what the project knows. Nothing here changes your data.</p></div></div>
        <div data-testid="lookup-gated"></div>
      </div>`,
      async (root) => {
        const gated = root.querySelector('[data-testid="lookup-gated"]');
        const gate = await ctx.gate();
        if (gate === 'nosuch') {
          gated.innerHTML = emptyHtml({
            title: 'No items yet. Your knowledge base file is created the first time you add text.',
            next: 'Add your first text',
            onNext: 'lookup-empty-add',
          });
          gated.querySelector('[data-action="lookup-empty-add"]')?.addEventListener('click', () => ctx.navigate('add'));
          return;
        }
        if (gate === 'invalid') {
          showErrorBlock(
            gated,
            { code: 'APP-006', name: 'KnowledgeBaseMissing', where: 'lookup', detail: 'the chosen knowledge base file is not an Ember file' },
            { what: 'the knowledge base', onRetry: render },
          );
          return;
        }
        gated.innerHTML = `
          <div class="tabs" role="tablist" aria-label="Look up tabs" data-testid="lookup-tabs">
            <button role="tab" data-tab="items" aria-selected="${view.tab === 'items'}" data-testid="tab-items">Items</button>
            <button role="tab" data-tab="ledger" aria-selected="${view.tab === 'ledger'}" data-testid="tab-ledger">Ledger</button>
          </div>
          <div data-testid="lookup-body"></div>`;
        root.querySelectorAll('[data-testid="lookup-tabs"] [role="tab"]').forEach((tab) => {
          tab.addEventListener('click', () => {
            view.tab = tab.dataset.tab;
            view.selectedItem = null;
            view.detail = { state: 'idle' };
            render();
          });
          tab.addEventListener('keydown', (event) => {
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
              event.preventDefault();
              const tabs = [...root.querySelectorAll('[role="tab"]')];
              const next = tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
              next.focus();
              next.click();
            }
          });
        });
        const body = root.querySelector('[data-testid="lookup-body"]');
        if (view.tab === 'items') renderItemsTab(body);
        else renderLedgerTab(body);
      },
    );
  }

  /* ---------------- items tab ---------------- */

  function renderItemsTab(body, root) {
    body.innerHTML = `
      <label for="lookup-q" style="margin-top:0">Search items</label>
      <div class="filters">
        <input type="text" id="lookup-q" data-testid="lookup-q" value="${esc(view.q)}" aria-label="Search items">
        <select data-testid="lookup-status" aria-label="Status">
          ${[['', NO_STATUS], ['Active', 'Active'], ['Challenged', 'Challenged'], ['Closed', 'Closed']]
            .map(([value, text]) => `<option value="${value}"${(view.status ?? '') === value ? ' selected' : ''}>${text}</option>`)
            .join('')}
        </select>
        <select data-testid="lookup-type" aria-label="Type">
          ${[['', NO_TYPE], ['Decision', 'Decision'], ['Assumption', 'Assumption'], ['Finding', 'Finding'], ['Question', 'Question']]
            .map(([value, text]) => `<option value="${value}"${(view.type ?? '') === value ? ' selected' : ''}>${text}</option>`)
            .join('')}
        </select>
        <span class="count-line" data-testid="lookup-count" role="status"></span>
      </div>
      <div data-testid="lookup-results"></div>`;
    const q = body.querySelector('[data-testid="lookup-q"]');
    let debounce = null;
    const setQuery = () => {
      view.q = q.value;
      view.offset = 0;
      view.selectedItem = null;
      view.detail = { state: 'idle' };
      loadItems();
    };
    q.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(setQuery, 220);
    });
    q.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        clearTimeout(debounce);
        setQuery();
      }
    });
    body.querySelector('[data-testid="lookup-status"]').addEventListener('change', (event) => {
      view.status = event.target.value || null;
      view.offset = 0;
      view.selectedItem = null;
      view.detail = { state: 'idle' };
      loadItems();
    });
    body.querySelector('[data-testid="lookup-type"]').addEventListener('change', (event) => {
      view.type = event.target.value || null;
      view.offset = 0;
      view.selectedItem = null;
      view.detail = { state: 'idle' };
      loadItems();
    });
    loadItems();
  }

  async function loadItems() {
    const body = ctx.paneEl().querySelector('[data-testid="lookup-body"]');
    if (!body) return;
    const results = body.querySelector('[data-testid="lookup-results"]');
    const countLine = body.querySelector('[data-testid="lookup-count"]');
    showLoadingBlock(results, 'Reading the items…');
    const filters = { status: view.status, type: view.type };
    const query = view.q.trim();
    const result = await (query !== ''
      ? ctx.api.topicSearch({ query, ...filters, limit: PAGE_SIZE })
      : ctx.api.listItems({ ...filters, limit: PAGE_SIZE, offset: view.offset }));
    if (countLine) countLine.textContent = '';
    const data = dataOrNull(results, result, { what: 'the item list', onRetry: loadItems });
    if (data === null) return;

    // list-items carries `items` + `total` (the count AFTER the filters,
    // BEFORE the page crop); topic-search carries `results` + `count`.
    const rows = (data.items ?? data.results ?? []).map((r) => ({
      id: r.id ?? r.item_id,
      type: r.type,
      statement: r.statement,
      status: r.status,
    }));
    const total = data.total ?? data.count ?? rows.length;
    if (countLine) {
      countLine.textContent =
        query !== ''
          ? `${total} ${total === 1 ? 'match' : 'matches'} for "${query}"`
          : `${Math.min(view.offset + rows.length, total)} of ${total} items`;
    }
    if (rows.length === 0) {
      const nothingMatched = query !== '' || view.status !== null || view.type !== null;
      results.innerHTML = emptyHtml({
        title: nothingMatched ? `No items match${query !== '' ? ` "${query}"` : ' these filters'}.` : 'No items yet.',
        next: nothingMatched ? 'Clear filters' : 'Add your first text',
        onNext: nothingMatched ? 'lookup-clear' : 'lookup-empty-add',
      });
      bindClear(results);
      results.querySelector('[data-action="lookup-empty-add"]')?.addEventListener('click', () => ctx.navigate('add'));
      return;
    }
    results.innerHTML = `<div class="panel"><table class="ember-table" data-testid="lookup-table">
      <thead><tr><th class="num nowrap">No.</th><th class="nowrap">Type</th><th>Item</th><th class="nowrap">Status</th></tr></thead>
      <tbody>${rows.map((it) => itemRowHtml(it, view.selectedItem === it.id)).join('')}
      ${view.selectedItem !== null ? `<tr class="detail-row"><td></td><td colspan="3" data-testid="item-detail">${detailHtml(view.detail)}</td></tr>` : ''}
      </tbody></table></div>
      <div class="pager" data-testid="lookup-pager">
        ${view.offset > 0 ? buttonHtml({ label: 'Newer items', action: 'page-newer', variant: 'secondary', testid: 'page-newer' }) : ''}
        ${view.offset + rows.length < total ? buttonHtml({ label: 'Older items', action: 'page-older', variant: 'secondary', testid: 'page-older' }) : ''}
      </div>`;
    bindClear(results);
    results.querySelectorAll('tr.row-click').forEach((row) => {
      row.addEventListener('click', () => selectItem(Number(row.dataset.id)));
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectItem(Number(row.dataset.id));
        }
      });
    });
    results.querySelector('[data-action="page-newer"]')?.addEventListener('click', () => {
      view.offset = Math.max(0, view.offset - PAGE_SIZE);
      loadItems();
    });
    results.querySelector('[data-action="page-older"]')?.addEventListener('click', () => {
      view.offset = view.offset + PAGE_SIZE;
      loadItems();
    });
  }

  function bindClear(host) {
    host.querySelector('[data-action="lookup-clear"]')?.addEventListener('click', () => {
      view.q = '';
      view.status = null;
      view.type = null;
      view.offset = 0;
      view.selectedItem = null;
      view.detail = { state: 'idle' };
      render();
    });
  }

  async function selectItem(id) {
    view.selectedItem = view.selectedItem === id ? null : id;
    view.detail = { state: 'loading' };
    await loadItems();
    if (view.selectedItem !== id) return; // a second click closed it
    const body = ctx.paneEl().querySelector('[data-testid="item-detail"]');
    if (!body) return;
    const result = await ctx.api.showItem(id);
    const data = dataOrNull(body, result, { what: "the item's provenance", onRetry: () => selectItem(id) });
    if (data === null) {
      view.detail = { state: 'error' };
      return;
    }
    view.detail = { state: 'ok', data };
    body.innerHTML = detailHtml(view.detail);
  }

  /* ---------------- the detail (provenance) view ---------------- */

  function detailHtml(detail) {
    if (detail.state === 'loading') {
      return stateBlockHtml('loading', { hint: 'Reading where this item came from…' });
    }
    if (detail.state !== 'ok') return '';
    const { item, source, links_out: linksOut, links_in: linksIn } = detail.data;
    const lineage = [];
    if (typeof source === 'string' && source.trim() !== '') {
      lineage.push(
        `<li><span class="k">Source</span><span><div class="source-verbatim" data-testid="item-source">${esc(source)}</div></span></li>`,
      );
    }
    if (item.rationale) {
      lineage.push(`<li><span class="k">Why</span><span data-testid="item-why">${esc(item.rationale)}</span></li>`);
    }
    for (const link of linksOut ?? []) lineage.push(linkLine(LINK_LABELS_OUT[link.type] ?? 'Relates to', link));
    for (const link of linksIn ?? []) lineage.push(linkLine(LINK_LABELS_IN[link.type] ?? 'Relates to', link));
    if ((linksOut ?? []).length === 0 && (linksIn ?? []).length === 0) {
      lineage.push('<li><span class="k">Links</span><span class="dim">None yet.</span></li>');
    }
    if (item.status === 'Closed' && item.close_reason) {
      lineage.push(`<li><span class="k">Closed because</span><span>${esc(item.close_reason)}</span></li>`);
    }
    return `<div class="pad" data-testid="provenance-panel">
      <p class="lbl-pill">${esc(item.type ?? '')}</p>
      <p style="margin:.15rem 0 var(--s3)">${esc(item.statement ?? '')} ${statusPillHtml(item.status)}</p>
      <ul class="lineage" data-testid="provenance">${lineage.join('')}</ul>
      <p class="help">Nothing here is deleted: links show as Rejected, items as Closed.</p>
    </div>`;
  }

  /** One link line: the label, the other item with its heat mark, the link's own status. */
  function linkLine(label, link) {
    const reversed = link.reversed_at ? ` (reversed ${esc(String(link.reversed_at).slice(0, 10))})` : '';
    return `<li><span class="k">${esc(label)}</span><span data-testid="provenance-link">
      ${statusPillHtml(link.other_item_status)}
      <span class="mono">${esc(String(link.other_item_id))}</span>
      ${esc(link.other_item_statement ?? '')}
      <span class="dim">(link ${esc(String(link.id))} ${esc(humanLinkType(link.type))}, ${esc(String(link.status ?? '').toLowerCase())}${reversed})</span>
    </span></li>`;
  }

  /* ---------------- ledger tab (stories 37-38, 122) ---------------- */

  function renderLedgerTab(body) {
    body.innerHTML = `
      <div class="filters">
        <label for="ledger-item" style="margin:0">Only item number</label>
        <input type="number" id="ledger-item" data-testid="ledger-item" min="1" value="${view.ledger.item ?? ''}" aria-label="Only item number" class="ledger-narrow">
        <label for="ledger-since" style="margin:0">Changes since</label>
        <input type="date" id="ledger-since" data-testid="ledger-since" value="${esc(view.ledger.sinceText)}" aria-label="Changes since">
        <button type="button" class="btn btn--text" data-testid="ledger-clear" title="Show every change">Clear filters</button>
      </div>
      <p class="help" data-testid="ledger-count" role="status"></p>
      <div data-testid="ledger-results"></div>`;
    body.querySelector('[data-testid="ledger-item"]').addEventListener('change', (event) => {
      const n = Number(event.target.value);
      view.ledger.item = Number.isInteger(n) && n > 0 ? n : null;
      view.ledger.offset = 0;
      loadLedger();
    });
    body.querySelector('[data-testid="ledger-since"]').addEventListener('change', (event) => {
      view.ledger.sinceText = event.target.value;
      view.ledger.offset = 0;
      loadLedger();
    });
    body.querySelector('[data-testid="ledger-clear"]').addEventListener('click', () => {
      view.ledger.item = null;
      view.ledger.sinceText = '';
      view.ledger.offset = 0;
      loadLedger();
    });
    loadLedger();
  }

  async function loadLedger() {
    const body = ctx.paneEl().querySelector('[data-testid="ledger-results"]');
    const countLine = ctx.paneEl().querySelector('[data-testid="ledger-count"]');
    if (!body) return;
    showLoadingBlock(body, 'Reading the ledger…');
    const result = await ctx.api.history({
      item: view.ledger.item,
      limit: LEDGER_PAGE_SIZE + 1, // one extra row is the "more lines" signal (Ledger paging, story 38)
      offset: view.ledger.offset,
      since: sinceIso(view.ledger.sinceText),
    });
    const data = dataOrNull(body, result, { what: 'the ledger', onRetry: loadLedger });
    if (countLine) countLine.textContent = '';
    if (data === null) return;
    const events = data.events ?? [];
    const shown = events.slice(0, LEDGER_PAGE_SIZE);
    const hasMore = events.length > LEDGER_PAGE_SIZE;
    if (countLine && shown.length > 0) {
      countLine.textContent = `${shown.length} ${shown.length === 1 ? 'line' : 'lines'} shown`;
    }
    if (shown.length === 0) {
      const filtered = view.ledger.item !== null || view.ledger.sinceText !== '';
      body.innerHTML = emptyHtml({
        title: filtered ? 'No ledger lines match these filters.' : 'The ledger is empty. Every change you make is written here.',
        next: filtered ? 'Clear filters' : null,
        onNext: filtered ? 'ledger-clear' : null,
      });
      body.querySelector('[data-action="ledger-clear"]')?.addEventListener('click', () => {
        view.ledger.item = null;
        view.ledger.sinceText = '';
        view.ledger.offset = 0;
        loadLedger();
      });
      return;
    }
    const rows = shown
      .map(
        (e) => `<tr data-testid="ledger-row">
          <td class="dim nowrap">${esc(e.timestamp ?? '')}</td>
          <td><span class="lbl-pill" data-testid="ledger-kind">${esc(historyKindLabel(e.kind))}</span> ${esc(historyEventSentence(e))}</td>
        </tr>`,
      )
      .join('');
    body.innerHTML = `<div class="panel"><table class="ember-table" data-testid="ledger-table">
      <thead><tr><th class="nowrap">When</th><th>What changed</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="pager">
        ${view.ledger.offset > 0 ? buttonHtml({ label: 'Newer lines', action: 'ledger-newer', variant: 'secondary', testid: 'ledger-newer' }) : ''}
        ${hasMore ? buttonHtml({ label: 'Older lines', action: 'ledger-older', variant: 'secondary', testid: 'ledger-older' }) : ''}
      </div>`;
    body.querySelector('[data-action="ledger-newer"]')?.addEventListener('click', () => {
      view.ledger.offset = Math.max(0, view.ledger.offset - LEDGER_PAGE_SIZE);
      loadLedger();
    });
    body.querySelector('[data-action="ledger-older"]')?.addEventListener('click', () => {
      view.ledger.offset = view.ledger.offset + LEDGER_PAGE_SIZE;
      loadLedger();
    });
  }

  function sinceIso(text) {
    if (typeof text !== 'string' || text.trim() === '') return null;
    const date = new Date(`${text.trim()}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date.toISOString();
  }

  return { render };
}

/* ---------- pure row helper (unit-testable) ---------- */

export function itemRowHtml(it, selected) {
  const label = `Item ${String(it.id)}, ${it.type ?? ''}: ${String(it.statement ?? '').replace(/\s+/g, ' ').trim()}, ${it.status}`;
  return `<tr class="row-click" data-id="${esc(String(it.id))}" tabindex="0" aria-selected="${selected ? 'true' : 'false'}"
    aria-label="${esc(label)}" data-testid="lookup-row-${esc(String(it.id))}">
    <td class="num dim">${esc(String(it.id))}</td>
    <td class="dim">${esc(it.type ?? '')}</td>
    <td>${esc(it.statement ?? '')}</td>
    <td>${statusPillHtml(it.status)}</td>
  </tr>`;
}

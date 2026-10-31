/**
 * Fix and close (app step 07): the write job over `runCommand`, exactly
 * as the contract table pins the commands (app step file §1).
 *
 * Stories, one by one:
 * - 49  the item comes from a list (`list-items`), never a typed id.
 * - 50  Mark Active / Mark Challenged (`set-status`).
 * - 51  the status buttons are off for a Closed item, reason shown.
 * - 52  Mark verified / Clear verified (`set-validated`/
 *       `clear-validated`, Assumption only); after EVERY write the app
 *       re-reads `show-item` — the screen never recomputes state (D3).
 * - 53  "verified" off elsewhere with the reason.
 * - 54  Edit rationale (Decision) / Edit source (Finding) with an
 *       `edit-item --dry-run` preview before the write (55 keeps the
 *       other edits off with the reason).
 * - 56-58  the close preview is `close-item --dry-run --format json`:
 *       the dependent count and list come straight from the dry-run
 *       `changes` (57); the reason is invalidated or expired (58).
 * - 59  the final confirmation names the item and offers Cancel (inline,
 *       DESIGN.md No Modal First Rule; spec decision 12.7 stays at its
 *       KEEP default — the founder may drop the second confirm at this
 *       step's review; recorded in the ticket build notes).
 * - 60  Remove a link: `remove-link --dry-run` preview, then apply —
 *       marked Rejected, never deleted (Reject/Close words, no Delete).
 * - 61  Undo a replacement: `reverse-supersedes` (the command has no
 *       --dry-run), the older item comes back as Active.
 * - 62  every change ends with ONE plain confirming sentence.
 * - 111-119, 123  the Undo/Redo controls: the label comes from
 *       `undo --dry-run --format json` through the pure helper
 *       shared/undo-labels.mjs ("Undo Close item 3", 121/113); the
 *       NothingToUndo/NothingToRedo refusals render as honest DISABLED
 *       buttons with their visible reason (111/112/123); every other
 *       refusal shows at the click as a plain sentence with Try again
 *       (118: MAINTAIN-025); the story-119 note says what Undo does
 *       NOT reverse and how to reverse each. Ctrl/Cmd+Z and
 *       Shift+Cmd/Ctrl+Z work while this pane is open; the Edit MENU
 *       itself is step 12, which reuses the same pure helpers.
 *
 * Five states: normal, loading (list and detail blocks), empty (no
 * items yet), error (per block with Retry and the code behind
 * Details). The no-key state cannot occur on this screen: every Fix
 * and close command runs without an AI key (docs/commands.md), so no
 * no-key block is shown here — Home owns the app-wide banner.
 *
 * Motion (step-03 rules): the heat mark settles only where an item's
 * status REALLY changed between two renders — which includes every
 * status change made through Undo and Redo; nothing animates on load
 * or revisit; Reduce Motion disables it in components.css.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { statusPillHtml } from '../components/status-pill.mjs';
import { settleClass } from '../components/heat-mark.mjs';
import { emptyHtml } from '../components/state-block.mjs';
import { maintainSentenceFor, undoNoteFor } from '../../shared/maintain-sentences.mjs';
import { undoRedoLabel, undoDoneSentence, undoDisabledReason } from '../../shared/undo-labels.mjs';
import { showErrorBlock, showLoadingBlock } from './blocks.mjs';

const CLOSE_REASONS = [
  ['invalidated', 'It was wrong (invalidated)'],
  ['expired', 'It ran out (expired)'],
];

const LINK_TYPE_OUT = { contradicts: 'challenges', supersedes: 'replaces', answers: 'answers', depends_on: 'depends on', supports: 'supports' };
const LINK_TYPE_IN = { contradicts: 'is challenged by', supersedes: 'is replaced by', answers: 'is answered by', depends_on: 'is needed by', supports: 'is supported by' };

const IS_MAC = /Mac/i.test(navigator.platform ?? '');

/**
 * One Ctrl/Cmd+Z listener for the whole app lifetime; it acts only
 * while a Fix and close pane is mounted (the prototype's rule; the
 * menu copy is step 12). Rebinding per screen render would stack
 * listeners — one bound listener with swapped handlers cannot.
 */
const undoKeys = { bound: false, handlers: null };

function bindUndoKeys(handlers) {
  undoKeys.handlers = handlers;
  if (undoKeys.bound) return;
  undoKeys.bound = true;
  document.addEventListener('keydown', (event) => {
    if (undoKeys.handlers === null) return;
    if (!document.querySelector('[data-testid="fix-pane"]')) return; // pane unmounted
    if (event.key !== 'z' && event.key !== 'Z') return;
    if (!(event.ctrlKey || event.metaKey)) return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
    event.preventDefault();
    if (event.shiftKey) undoKeys.handlers.redo();
    else undoKeys.handlers.undo();
  });
}

export function createFixCloseScreen(ctx) {
  const view = {
    selectedItem: null,
    close: { reason: 'invalidated', preview: null, asking: false },
    edit: { field: null, value: '', preview: null },
    unLink: { linkId: null, preview: null, asking: false },
    undoBar: { undo: { kind: 'idle' }, redo: { kind: 'idle' } },
    prevStatus: new Map(), // item id -> status at the previous render (the settle source)
    settleMap: new Map(), // item id -> settle class for the current render
  };
  let busy = false; // one write in flight at a time (writes are never auto-retried)

  /* ---------------- frame and states ---------------- */

  function render() {
    bindUndoKeys({ undo: () => applyUndoRedo('undo'), redo: () => applyUndoRedo('redo') });
    ctx.renderFrame(
      `<div data-testid="fix-pane">
        <div class="titlerow">
          <div class="grow"><h1>Fix and close</h1>
            <p class="sub">Change an item or a link. Every change is written to the ledger, and Undo adds a new line instead of erasing one. Closing needs a preview first.</p></div>
          <div class="actions" data-testid="undo-bar"></div>
        </div>
        <p class="help" data-testid="undo-note" style="margin-top:calc(-1 * var(--s4))">Adding text, confirming links and applying the sweep are not undone by Undo. To reverse an add, close the item here; to reverse a link, remove it below (it is marked Rejected, never deleted); the sweep follows the links, so the next sweep redraws its own results.</p>
        <div data-testid="fix-message-region" role="status" aria-live="polite"></div>
        <div data-testid="fix-gated"></div>
      </div>`,
      async (root) => {
        const gated = root.querySelector('[data-testid="fix-gated"]');
        const gate = await ctx.gate();
        if (gate === 'nosuch') {
          gated.innerHTML = emptyHtml({
            title: 'No items yet. Your knowledge base file is created the first time you add text.',
            next: 'Add your first text',
            onNext: 'fix-empty-add',
          });
          gated.querySelector('[data-action="fix-empty-add"]')?.addEventListener('click', () => ctx.navigate('add'));
          return;
        }
        if (gate === 'invalid') {
          showErrorBlock(
            gated,
            { code: 'APP-006', name: 'KnowledgeBaseMissing', where: 'fix', detail: 'the chosen knowledge base file is not an Ember file' },
            { what: 'the knowledge base', onRetry: render },
          );
          return;
        }
        await Promise.all([refreshUndoBar(), loadList()]);
      },
    );
  }

  /* ---------------- the Undo / Redo bar (stories 111-114, 123) ---------------- */

  async function refreshUndoBar() {
    const [undoResult, redoResult] = await Promise.all([ctx.api.undoPlan('undo'), ctx.api.undoPlan('redo')]);
    view.undoBar.undo = planState(undoResult);
    view.undoBar.redo = planState(redoResult);
    renderUndoBar();
  }

  /** One dry-run result -> that side's bar state. */
  function planState(result) {
    if (result && result.ok) {
      return { kind: 'plan', plan: result.data.summary, label: undoRedoLabel(result.data.summary) };
    }
    const error = result ? result.error : null;
    const reason = undoDisabledReason(error);
    if (reason) return { kind: 'disabled', reason };
    // MAINTAIN-025 and transport errors: the button stays usable — the
    // click is where the refusal shows with Try again (story 118).
    return { kind: 'refused', error };
  }

  function renderUndoBar() {
    const bar = ctx.paneEl().querySelector('[data-testid="undo-bar"]');
    if (!bar) return;
    const one = (side) => {
      const state = view.undoBar[side];
      const isUndo = side === 'undo';
      const enabled = state.kind === 'plan' || state.kind === 'refused';
      const text = state.kind === 'plan' ? state.label : isUndo ? 'Undo' : 'Redo';
      const kbd = isUndo
        ? IS_MAC ? 'Command+Z' : 'Ctrl+Z'
        : IS_MAC ? 'Shift+Command+Z' : 'Shift+Ctrl+Z';
      const title = state.kind === 'disabled' ? ` title="${esc(state.reason)}"` : '';
      return `<button type="button" class="btn" data-action="fix-${side}" data-testid="fix-${side}-btn"${enabled ? '' : ' disabled'}${title}>${esc(text)}<span class="kbd">${esc(kbd)}</span></button>`;
    };
    const disabledReason =
      view.undoBar.undo.kind === 'disabled' ? view.undoBar.undo.reason
      : view.undoBar.redo.kind === 'disabled' ? view.undoBar.redo.reason
      : null;
    const refusedState = view.undoBar.undo.kind === 'refused' ? view.undoBar.undo : view.undoBar.redo.kind === 'refused' ? view.undoBar.redo : null;
    bar.innerHTML = `${one('undo')} ${one('redo')}` +
      (disabledReason ? `<p class="help" data-testid="undo-reason" style="flex-basis:100%;max-width:26rem">${esc(disabledReason)}</p>` : '') +
      (refusedState ? `<p class="help" data-testid="undo-bar-hint" style="flex-basis:100%;max-width:26rem">${esc(refusalLine(refusedState.error))}</p>` : '');
    bar.querySelector('[data-action="fix-undo"]')?.addEventListener('click', () => applyUndoRedo('undo'));
    bar.querySelector('[data-action="fix-redo"]')?.addEventListener('click', () => applyUndoRedo('redo'));
  }

  function refusalLine(error) {
    const sentence = maintainSentenceFor(error && error.code ? error.code : null);
    const note = undoNoteFor(error?.code ?? '', error?.detail ?? '');
    return `${sentence.title} ${note ?? sentence.what}`;
  }

  async function applyUndoRedo(direction) {
    if (busy) return;
    // Re-derive first: a keystroke can arrive while a previous write's
    // refresh is still in flight, and the engine — not a stale bar —
    // decides what is undoable right now. A genuinely disabled state
    // stays an honest no-op.
    await refreshUndoBar();
    const state = view.undoBar[direction];
    if (state.kind === 'disabled') return;
    busy = true;
    setMessage(null);
    const result = await ctx.api.fixAction({ action: direction, args: {} });
    busy = false;
    if (!result.ok) {
      showWriteError(result.error, `the ${direction}`, () => applyUndoRedo(direction));
      return;
    }
    setMessage({ kind: 'ok', html: esc(undoDoneSentence(result.data.summary)) });
    await reloadAll();
  }

  /* ---------------- the items list (story 49) ---------------- */

  function listRegion() {
    const gated = ctx.paneEl().querySelector('[data-testid="fix-gated"]');
    if (!gated) return null;
    let region = gated.querySelector('[data-testid="fix-list"]');
    if (!region) {
      region = document.createElement('div');
      region.dataset.testid = 'fix-list';
      gated.prepend(region);
    }
    return region;
  }

  function detailRegion() {
    const gated = ctx.paneEl().querySelector('[data-testid="fix-gated"]');
    if (!gated) return null;
    let region = gated.querySelector('[data-testid="fix-detail"]');
    if (!region) {
      region = document.createElement('div');
      region.dataset.testid = 'fix-detail';
      gated.append(region);
    }
    return region;
  }

  async function loadList() {
    const region = listRegion();
    if (!region) return;
    showLoadingBlock(region, 'Reading the items…');
    const result = await ctx.api.listItems({});
    if (!region.isConnected) return;
    if (!result || !result.ok) {
      showErrorBlock(region, result ? result.error : null, { what: 'the item list', onRetry: loadList });
      return;
    }
    const rows = result.data.items ?? [];
    if (rows.length === 0) {
      region.innerHTML = emptyHtml({
        title: 'No items yet. Your knowledge base file is created the first time you add text.',
        next: 'Add your first text',
        onNext: 'fix-empty-add',
      });
      region.querySelector('[data-action="fix-empty-add"]')?.addEventListener('click', () => ctx.navigate('add'));
      if (view.selectedItem !== null) view.selectedItem = null;
      renderDetailEmpty();
      return;
    }
    if (view.selectedItem !== null && !rows.some((it) => it.id === view.selectedItem)) {
      view.selectedItem = null; // the list is the one source of ids
    }

    // The heat mark settles only where the status REALLY changed since
    // the previous render: the settle map is captured against the OLD
    // statuses BEFORE the new ones are remembered (nothing animates on
    // load or revisit).
    const prevStatus = view.prevStatus;
    const settleMap = new Map();
    const nextStatus = new Map();
    for (const row of rows) {
      const before = prevStatus.get(row.id) ?? null;
      settleMap.set(row.id, before !== null && before !== row.status ? settleClass(before, row.status) : '');
      nextStatus.set(row.id, row.status);
    }
    view.prevStatus = nextStatus;
    view.settleMap = settleMap; // the class per item for THIS render

    region.innerHTML = `<div class="panel"><table class="ember-table" data-testid="fix-table">
      <thead><tr><th class="num nowrap">No.</th><th>Item</th><th class="nowrap">Status</th></tr></thead>
      <tbody>${rows.map((it) => fixRowHtml(it, view.selectedItem === it.id, settleMap.get(it.id) ?? '')).join('')}</tbody>
    </table></div>
    <p class="help" data-testid="fix-countline">${rows.length} ${rows.length === 1 ? 'item' : 'items'}</p>`;
    region.querySelectorAll('tr.row-click').forEach((row) => {
      row.addEventListener('click', () => selectItem(Number(row.dataset.id)));
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectItem(Number(row.dataset.id));
        }
      });
    });
    await loadDetail();
  }

  function settleFor(id, _status) {
    return view.settleMap.get(id) ?? '';
  }

  async function selectItem(id) {
    if (view.selectedItem === id) return;
    view.selectedItem = id;
    resetPanels();
    await loadList();
  }

  function resetPanels() {
    view.close = { reason: 'invalidated', preview: null, asking: false };
    view.edit = { field: null, value: '', preview: null };
    view.unLink = { linkId: null, preview: null, asking: false };
    setMessage(null);
  }

  /* ---------------- the item panel (stories 50-55) ---------------- */

  async function loadDetail() {
    const region = detailRegion();
    if (!region) return;
    if (view.selectedItem === null) {
      renderDetailEmpty();
      return;
    }
    const id = view.selectedItem;
    showLoadingBlock(region, 'Reading the item…');
    const result = await ctx.api.showItem(id);
    if (!region.isConnected || view.selectedItem !== id) return;
    if (!result || !result.ok) {
      showErrorBlock(region, result ? result.error : null, { what: 'the item', onRetry: () => { view.selectedItem = id; loadDetail(); } });
      return;
    }
    renderDetail(region, result.data);
  }

  function renderDetailEmpty() {
    const region = detailRegion();
    if (region) region.innerHTML = '<p class="help" data-testid="fix-no-selection">Select an item above to change it. Every change is written to the ledger.</p>';
  }

  function renderDetail(region, data) {
    const { item, links_out: linksOut = [], links_in: linksIn = [] } = data;
    const closed = item.status === 'Closed';
    const isAssumption = item.type === 'Assumption';
    const settle = settleFor(item.id, item.status);

    // Story 50 on top of 51: same-value moves are engine no-ops, so the
    // button is off with its own reason (story 103).
    const markActiveOn = !closed && item.status === 'Challenged';
    const markChallengedOn = !closed && item.status === 'Active';

    const whys = [];
    if (closed) whys.push('Status buttons are off because a Closed item cannot change status; it reopens only by undoing its close.');
    else if (item.status === 'Active') whys.push('Mark Active is off because the item is already Active.');
    else whys.push('Mark Challenged is off because the item is already Challenged.');
    if (!isAssumption) whys.push('Verified applies to assumptions only.');
    if (item.type !== 'Decision') whys.push('Rationale can be edited on a Decision.');
    if (item.type !== 'Finding') whys.push('Source can be edited on a Finding.');

    region.innerHTML = `
      <div data-testid="item-panel">
        <h2 style="margin-top:var(--s5)">Item ${esc(String(item.id))}</h2>
        <div class="panel tone"><div class="pad">
          <p class="lbl-pill">${esc(item.type ?? '')}${item.validated ? ' (verified)' : ''}</p>
          <p style="margin:.15rem 0 var(--s3)"><strong>${esc(item.statement ?? '')}</strong> ${statusPillHtml(item.status, { settle })}</p>
          ${closed && item.close_reason ? `<p class="help">Closed because: ${esc(item.close_reason)}.</p>` : ''}
          <div class="actions">
            ${fixButtonHtml({ label: 'Mark Active', action: 'fix-status-active', testid: 'mark-active', enabled: markActiveOn })}
            ${fixButtonHtml({ label: 'Mark Challenged', action: 'fix-status-challenged', testid: 'mark-challenged', enabled: markChallengedOn })}
            ${fixButtonHtml({ label: item.validated ? 'Clear verified' : 'Mark verified', action: 'fix-toggle-verified', testid: 'toggle-verified', enabled: isAssumption })}
            ${fixButtonHtml({ label: 'Edit rationale', action: 'fix-edit-rationale', testid: 'edit-rationale', enabled: item.type === 'Decision' })}
            ${fixButtonHtml({ label: 'Edit source', action: 'fix-edit-source', testid: 'edit-source', enabled: item.type === 'Finding' })}
          </div>
          <p class="help" id="fix-why" data-testid="fix-why">${esc(whys.join(' '))}</p>
          ${editorHtml(item)}
        </div></div>
        <h2>Close this item</h2>
        ${closeHtml(item)}
        <h2>Links</h2>
        ${linksHtml(item, linksOut, linksIn)}
        ${unlinkPreviewHtml()}
        ${unlinkConfirmHtml()}
        <p class="help">Removing a link marks it Rejected. Ember never deletes it.</p>
      </div>`;
    wireDetail(region, item, linksOut, linksIn);
  }

  /** A disabled action stays readable and points at its reason (story 103). */
  function fixButtonHtml({ label, action, testid = null, enabled = true }) {
    return `<button type="button" class="btn" data-action="${esc(action)}"${testid ? ` data-testid="${esc(testid)}"` : ''}${enabled ? '' : ' disabled aria-describedby="fix-why"'}>${esc(label)}</button>`;
  }

  async function setStatus(id, to) {
    if (busy) return;
    busy = true;
    setMessage(null);
    const result = await ctx.api.fixAction({ action: 'set-status', args: { item: id, to } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the status change', () => setStatus(id, to));
    setMessage({ kind: 'ok', html: esc(`Item ${id} is now ${to}. Ember notes you set it, so the sweep leaves it alone until newer link evidence arrives.`) });
    await reloadAll();
  }

  async function toggleVerified(item) {
    if (busy) return;
    const action = item.validated ? 'clear-validated' : 'set-validated';
    busy = true;
    setMessage(null);
    const result = await ctx.api.fixAction({ action, args: { item: item.id } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the verified mark', () => toggleVerified(item));
    setMessage({ kind: 'ok', html: esc(item.validated ? `The verified mark on item ${item.id} is cleared.` : `Item ${item.id} is marked as verified.`) });
    await reloadAll(); // after a write the app re-reads show-item (story 52)
  }

  /* ---------------- the inline editor (stories 54-55) ---------------- */

  async function openEditor(item, field) {
    view.edit = { field, value: field === 'rationale' ? item.rationale ?? '' : item.source ?? '', preview: null };
    await loadDetail();
    ctx.paneEl().querySelector('[data-testid="edit-input"]')?.focus();
  }

  function editorHtml(item) {
    if (view.edit.field === null) return '';
    const field = view.edit.field;
    if (view.edit.preview) {
      const change = (view.edit.preview.changes ?? [])[0] ?? {};
      return `<div data-testid="edit-preview"><p class="help" style="margin-top:var(--s3)" data-testid="edit-preview-line"><strong>What changes.</strong> The ${esc(field)} of item ${esc(String(item.id))}: ${sideText(change.old_value)} -> ${sideText(change.new_value)}. Nothing has changed yet.</p>
        <div class="actions">${buttonHtml({ label: `Save ${field}`, action: 'fix-edit-apply', variant: 'primary', testid: 'edit-apply' })}${buttonHtml({ label: 'Cancel', action: 'fix-edit-cancel', testid: 'edit-cancel' })}</div></div>`;
    }
    return `<label for="fix-edit-input" style="margin-top:var(--s3)">Edit ${esc(field)}</label>
      <input type="text" id="fix-edit-input" data-testid="edit-input" value="${esc(view.edit.value)}">
      <div class="actions">${buttonHtml({ label: 'Preview', action: 'fix-edit-preview', variant: 'primary', testid: 'edit-preview-btn' })}${buttonHtml({ label: 'Cancel', action: 'fix-edit-cancel', testid: 'edit-cancel' })}</div>
      <p class="help">Preview first: Ember shows the old and the new text before anything is written.</p>`;
  }

  /** Verbatim old/new text in quotes; an empty side reads "(empty)". */
  function sideText(value) {
    const text = value === null || value === undefined || String(value).trim() === '' ? '(empty)' : String(value);
    return `"${text.length > 60 ? `${text.slice(0, 60)}…` : text}"`;
  }

  function wireDetail(region, item, linksOut, linksIn) {
    region.querySelector('[data-action="fix-status-active"]')?.addEventListener('click', () => setStatus(item.id, 'Active'));
    region.querySelector('[data-action="fix-status-challenged"]')?.addEventListener('click', () => setStatus(item.id, 'Challenged'));
    region.querySelector('[data-action="fix-toggle-verified"]')?.addEventListener('click', () => toggleVerified(item));
    region.querySelector('[data-action="fix-edit-rationale"]')?.addEventListener('click', () => openEditor(item, 'rationale'));
    region.querySelector('[data-action="fix-edit-source"]')?.addEventListener('click', () => openEditor(item, 'source'));

    const input = region.querySelector('[data-testid="edit-input"]');
    if (input) {
      input.addEventListener('input', () => {
        view.edit.value = input.value;
      });
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          previewEdit(item);
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          view.edit = { field: null, value: '', preview: null };
          loadDetail();
        }
      });
    }
    region.querySelector('[data-action="fix-edit-preview"]')?.addEventListener('click', () => previewEdit(item));
    region.querySelector('[data-action="fix-edit-apply"]')?.addEventListener('click', () => applyEdit(item));
    region.querySelector('[data-action="fix-edit-cancel"]')?.addEventListener('click', () => {
      view.edit = { field: null, value: '', preview: null };
      loadDetail();
    });

    wireClose(region, item);
    wireLinks(region, item, linksOut, linksIn);
  }

  async function previewEdit(item) {
    if (busy) return;
    const value = view.edit.value.trim();
    if (value === '') return; // the engine refuses empty text; stay honest
    busy = true;
    const result = await ctx.api.fixAction({ action: 'edit-item', args: { item: item.id, field: view.edit.field, value, dryRun: true } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the edit preview', () => previewEdit(item));
    view.edit.preview = result.data;
    await loadDetail();
  }

  async function applyEdit(item) {
    if (busy) return;
    const field = view.edit.field;
    const value = view.edit.value.trim();
    busy = true;
    const result = await ctx.api.fixAction({ action: 'edit-item', args: { item: item.id, field, value } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the edit', () => applyEdit(item));
    view.edit = { field: null, value: '', preview: null };
    setMessage({ kind: 'ok', html: esc(`Saved. The ${field} of item ${item.id} is changed; the old text stays in the ledger.`) });
    await reloadAll();
  }

  /* ---------------- closing (stories 56-59) ---------------- */

  function closeHtml(item) {
    if (item.status === 'Closed') {
      return `<p class="help" data-testid="close-state">Already closed${item.close_reason ? ` (${esc(item.close_reason)})` : ''}.</p>`;
    }
    const preview = view.close.preview !== null ? closePreviewHtml(item) : '';
    const ask = view.close.preview !== null && !view.close.asking
      ? `<div class="actions">${buttonHtml({ label: `Close item ${item.id}…`, action: 'fix-close-ask', variant: 'danger', testid: 'close-ask' })}</div>`
      : '';
    return `<div class="filters" data-testid="close-row" style="margin-bottom:var(--s3)">
        <label for="fix-close-reason" style="margin:0">Reason</label>
        <select id="fix-close-reason" data-testid="close-reason" aria-label="Close reason">
          ${CLOSE_REASONS.map(([value, text]) => `<option value="${value}"${view.close.reason === value ? ' selected' : ''}>${esc(text)}</option>`).join('')}
        </select>
        ${buttonHtml({ label: 'Preview closing', action: 'fix-close-preview', testid: 'close-preview-btn' })}
      </div>
      ${preview}${ask}${view.close.asking ? closeConfirmHtml(item) : ''}`;
  }

  function closePreviewHtml(item) {
    const changes = view.close.preview.changes ?? [];
    const close = changes.find((c) => c.trigger_cause === 'user_closed') ?? { item_id: item.id, close_reason: view.close.reason };
    const dependents = changes.filter((c) => c.trigger_cause === 'dependency_closed');
    const reason = close.close_reason ?? view.close.reason;
    const dependentWords = dependents.length === 0
      ? 'No other item depends on it, so nothing else changes.'
      : `${dependents.length} ${dependents.length === 1 ? 'item that depends' : 'items that depend'} on it would become Challenged: ${dependents.map((d) => `item ${d.item_id}`).join(', ')}.`;
    return `<div class="panel" data-testid="close-preview"><div class="pad">
      <p><strong>Preview.</strong> Item ${esc(String(close.item_id))} would close as ${esc(reason)}. ${esc(dependentWords)} Nothing has changed yet.</p>
    </div></div>`;
  }

  /** Story 59: names the item, offers Cancel (inline, No Modal First). */
  function closeConfirmHtml(item) {
    return `<div class="panel tone" data-testid="close-confirm" role="group" aria-label="Close item ${esc(String(item.id))}: final confirmation"><div class="pad">
      <p><strong>Close item ${esc(String(item.id))}, "${esc((item.statement ?? '').replace(/\s+/g, ' '))}?"</strong></p>
      <p class="help">Ember writes the close to the ledger; Undo can bring the item back.</p>
      <div class="actions">
        ${buttonHtml({ label: `Close item ${item.id}`, action: 'fix-close-apply', variant: 'danger', testid: 'close-apply' })}
        ${buttonHtml({ label: 'Cancel', action: 'fix-close-cancel', testid: 'close-cancel' })}
      </div>
    </div></div>`;
  }

  function wireClose(region, item) {
    region.querySelector('[data-testid="close-reason"]')?.addEventListener('change', (event) => {
      view.close.reason = event.target.value;
      view.close.preview = null; // a new reason needs a new preview
      view.close.asking = false;
      loadDetail();
    });
    region.querySelector('[data-action="fix-close-preview"]')?.addEventListener('click', () => previewClose(item));
    region.querySelector('[data-action="fix-close-ask"]')?.addEventListener('click', async () => {
      view.close.asking = true;
      await loadDetail();
      region.querySelector('[data-testid="close-apply"]')?.focus();
    });
    region.querySelector('[data-action="fix-close-apply"]')?.addEventListener('click', () => applyClose(item));
    region.querySelector('[data-action="fix-close-cancel"]')?.addEventListener('click', () => {
      view.close.asking = false;
      loadDetail();
    });
  }

  async function previewClose(item) {
    if (busy) return;
    busy = true;
    const result = await ctx.api.fixAction({ action: 'close-item', args: { item: item.id, reason: view.close.reason, dryRun: true } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the close preview', () => previewClose(item));
    view.close.preview = result.data;
    view.close.asking = false;
    await loadDetail();
  }

  async function applyClose(item) {
    if (busy) return;
    const reason = view.close.reason;
    busy = true;
    const result = await ctx.api.fixAction({ action: 'close-item', args: { item: item.id, reason } });
    busy = false;
    view.close = { reason, preview: null, asking: false };
    if (!result.ok) return showWriteError(result.error, 'the close', () => applyClose(item));
    const dependents = (result.data.changes ?? []).filter((c) => c.trigger_cause === 'dependency_closed');
    setMessage({
      kind: 'ok',
      html: esc(`Item ${item.id} is closed (${reason}).${dependents.length > 0 ? ` Item${dependents.length === 1 ? '' : 's'} ${dependents.map((c) => c.item_id).join(', ')} became Challenged because of it.` : ''} The ledger keeps the close; Undo can bring the item back.`),
    });
    await reloadAll();
  }

  /* ---------------- links (stories 60-61) ---------------- */

  function linksHtml(item, linksOut, linksIn) {
    const rows = [...linksOut.map((l) => ({ link: l, direction: 'out' })), ...linksIn.map((l) => ({ link: l, direction: 'in' }))];
    const body = rows.length > 0 ? rows.map(({ link, direction }) => linkRowHtml(item, link, direction)).join('') : '<tr><td class="dim" colspan="3">No links.</td></tr>';
    return `<div class="panel"><table class="ember-table" data-testid="fix-links">
      <thead><tr><th class="nowrap">Link</th><th>What it says</th><th class="nowrap">Actions</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }

  function linkRowHtml(item, link, direction) {
    const typeWords = direction === 'out' ? LINK_TYPE_OUT[link.type] ?? 'relates to' : LINK_TYPE_IN[link.type] ?? 'is linked to';
    const fromId = direction === 'out' ? item.id : link.other_item_id;
    const toId = direction === 'out' ? link.other_item_id : item.id;
    const reversed = link.reversed_at ? ' (reversed)' : '';
    const canRemove = link.status === 'Confirmed';
    // Story 61: the closed (superseded) item is the link's target side.
    const canReverse = link.type === 'supersedes' && link.status === 'Confirmed' && !link.reversed_at;
    return `<tr data-testid="fix-link-${esc(String(link.id))}">
      <td class="num dim nowrap">${esc(String(link.id))}</td>
      <td>Item ${esc(String(fromId))} <strong>${esc(typeWords)}</strong> item ${esc(String(toId))}
        <span class="dim">(${esc(String(link.status ?? '').toLowerCase())}${reversed})</span></td>
      <td class="nowrap">
        ${canRemove ? buttonHtml({ label: 'Remove', action: `fix-unlink-${link.id}`, variant: 'text', testid: `unlink-${link.id}` }) : ''}
        ${canReverse ? buttonHtml({ label: 'Undo replacement', action: `fix-reverse-${link.id}`, variant: 'text', testid: `reverse-${link.id}` }) : ''}
      </td>
    </tr>`;
  }

  function wireLinks(region, item, linksOut, linksIn) {
    const rows = [...linksOut.map((l) => ({ link: l, direction: 'out' })), ...linksIn.map((l) => ({ link: l, direction: 'in' }))];
    for (const { link, direction } of rows) {
      if (link.status === 'Confirmed') {
        region.querySelector(`[data-action="fix-unlink-${link.id}"]`)?.addEventListener('click', () => previewUnlink(link));
      }
      if (link.type === 'supersedes' && link.status === 'Confirmed' && !link.reversed_at) {
        const targetId = direction === 'out' ? link.other_item_id : item.id;
        region.querySelector(`[data-action="fix-reverse-${link.id}"]`)?.addEventListener('click', () => applyReverse(targetId, link));
      }
    }
    region.querySelector('[data-action="fix-unlink-apply"]')?.addEventListener('click', () => applyUnlink());
    region.querySelector('[data-action="fix-unlink-cancel"]')?.addEventListener('click', () => {
      view.unLink = { linkId: null, preview: null, asking: false };
      loadDetail();
    });
  }

  function unlinkPreviewHtml() {
    if (view.unLink.preview === null) return '';
    const change = (view.unLink.preview.changes ?? [])[0] ?? { link_id: view.unLink.linkId };
    return `<div class="panel" data-testid="unlink-preview"><div class="pad">
      <p><strong>Preview.</strong> Link ${esc(String(change.link_id))} would be marked Rejected. Nothing is deleted; the history stays complete. Nothing has changed yet.</p>
    </div></div>`;
  }

  function unlinkConfirmHtml() {
    if (!view.unLink.asking) return '';
    return `<div class="panel tone" data-testid="unlink-confirm" role="group" aria-label="Remove link ${esc(String(view.unLink.linkId))}: final confirmation"><div class="pad">
      <p><strong>Remove link ${esc(String(view.unLink.linkId))}?</strong></p>
      <p class="help">The link is marked Rejected, never deleted; the ledger keeps both lines, and Undo can bring it back.</p>
      <div class="actions">
        ${buttonHtml({ label: `Remove link ${view.unLink.linkId}`, action: 'fix-unlink-apply', variant: 'danger', testid: 'unlink-apply' })}
        ${buttonHtml({ label: 'Cancel', action: 'fix-unlink-cancel', testid: 'unlink-cancel' })}
      </div>
    </div></div>`;
  }

  async function previewUnlink(link) {
    if (busy) return;
    busy = true;
    const result = await ctx.api.fixAction({ action: 'remove-link', args: { link: link.id, dryRun: true } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the removal preview', () => previewUnlink(link));
    view.unLink = { linkId: link.id, preview: result.data, asking: true };
    await loadDetail();
    ctx.paneEl().querySelector('[data-testid="unlink-confirm"]')?.scrollIntoView({ block: 'nearest' });
    ctx.paneEl().querySelector('[data-testid="unlink-apply"]')?.focus();
  }

  async function applyUnlink() {
    if (busy) return;
    const linkId = view.unLink.linkId;
    busy = true;
    const result = await ctx.api.fixAction({ action: 'remove-link', args: { link: linkId } });
    busy = false;
    view.unLink = { linkId: null, preview: null, asking: false };
    if (!result.ok) return showWriteError(result.error, 'the removal', () => applyUnlinkRetry(linkId));
    setMessage({ kind: 'ok', html: esc(`Link ${linkId} is removed: marked Rejected, never deleted. The ledger keeps both lines.`) });
    await reloadAll();
  }

  /** Try again after a refused removal: the confirm state is already
   * cleared, so retry straight from the saved link id. */
  async function applyUnlinkRetry(linkId) {
    if (busy) return;
    busy = true;
    const result = await ctx.api.fixAction({ action: 'remove-link', args: { link: linkId } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the removal', () => applyUnlinkRetry(linkId));
    setMessage({ kind: 'ok', html: esc(`Link ${linkId} is removed: marked Rejected, never deleted. The ledger keeps both lines.`) });
    await reloadAll();
  }

  /** Story 61: this command has no --dry-run; the engine refuses it in
   * plain words when a precondition moved (MAINTAIN-005). */
  async function applyReverse(targetId, link) {
    if (busy) return;
    busy = true;
    setMessage(null);
    const result = await ctx.api.fixAction({ action: 'reverse-supersedes', args: { item: targetId, link: link.id } });
    busy = false;
    if (!result.ok) return showWriteError(result.error, 'the reversal', () => applyReverse(targetId, link));
    setMessage({ kind: 'ok', html: esc(`Replacement undone: item ${targetId} is Active again. Ember keeps the link on record.`) });
    await reloadAll();
  }

  /* ---------------- messages and errors (stories 62, 102, 118) ---------------- */

  function setMessage(msg) {
    const region = ctx.paneEl().querySelector('[data-testid="fix-message-region"]');
    if (!region) return;
    if (!msg) {
      region.innerHTML = '';
      return;
    }
    region.innerHTML = msg.kind === 'error' ? msg.html : `<div class="ok" data-testid="fix-message">${msg.html}</div>`;
  }

  /** One write refused or failed: plain words first, the code behind
   * Details, Try again repeats the SAME user action (a new deliberate
   * click — this is the manual retry the write rule allows). */
  function showWriteError(error, what, retry) {
    const info = error ?? {};
    const sentence = maintainSentenceFor(info.code ?? null);
    const note = undoNoteFor(info.code ?? '', info.detail ?? '');
    const region = ctx.paneEl().querySelector('[data-testid="fix-message-region"]');
    if (!region) return;
    region.innerHTML = `<div class="errbox" data-testid="fix-error" role="alert">
        <strong>${esc(sentence.title)}</strong>
        <span class="detail">${esc(sentence.what)} (${esc(what)} was not done.)</span>
        ${note ? `<span class="hint">${esc(note)}</span>` : `<span class="hint">${esc(sentence.next)}</span>`}
        <div class="actions">
          <button type="button" class="btn" data-action="fix-error-retry" data-testid="fix-error-retry">Try again</button>
          <button type="button" class="btn btn--text" data-action="fix-error-details" data-testid="fix-error-details">Details</button>
        </div>
      </div>
      <p class="help" data-testid="error-code" hidden>${esc(`${info.code ?? ''} ${info.name ?? ''} | ${info.detail ?? ''}`)}</p>`;
    region.querySelector('[data-action="fix-error-retry"]').addEventListener('click', () => retry());
    region.querySelector('[data-action="fix-error-details"]').addEventListener('click', () => {
      const line = region.querySelector('[data-testid="error-code"]');
      if (line) line.hidden = !line.hidden;
    });
    region.scrollIntoView({ block: 'nearest' });
  }

  /** After every write: re-read the list (which re-reads the item
   * through it) and refresh the Undo/Redo labels. */
  async function reloadAll() {
    await Promise.all([refreshUndoBar(), loadList()]);
  }

  return { render };
}

/* ---------- pure row helper (unit-testable, mirrors lookup's) ---------- */

export function fixRowHtml(it, selected, settle) {
  const label = `Item ${String(it.id)}, ${it.type ?? ''}: ${String(it.statement ?? '').replace(/\s+/g, ' ').trim()}, ${it.status}`;
  return `<tr class="row-click" data-id="${esc(String(it.id))}" tabindex="0" aria-selected="${selected ? 'true' : 'false'}"
    aria-label="${esc(label)}" data-testid="fix-row-${esc(String(it.id))}">
    <td class="num dim">${esc(String(it.id))}</td>
    <td>${esc(it.statement ?? '')}</td>
    <td>${statusPillHtml(it.status, { settle })}</td>
  </tr>`;
}

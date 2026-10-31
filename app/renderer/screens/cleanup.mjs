/**
 * The Clean up screen (L3 app step 08, ticket A37; spec stories
 * 63-69). One job: draw the sweep and relay it, nothing more (B1/B3 —
 * every rule lives in the engine; this screen reads `maintain`'s own
 * data and sends back only the engine's own answers).
 *
 * - Preview: `maintain --dry-run` and the ONE document it prints — the
 *   table of which item becomes what and why (with heat marks before →
 *   after), the counts, and the `stale: N` shortlist summary (64).
 * - Apply: a REAL `maintain --confirm json` session through the step-02
 *   bridge client. The loop is rendered from the REAL events the child
 *   emits: one proposal block per stale question, the prompt's own
 *   choices (y/n/q -> Confirm/Reject/Stop; Stop = closing the input via
 *   stop(), never a written answer), the engine's report lines as
 *   inline messages, and the final document as the summary (67).
 * - Apply stays off until a preview has been shown in this window
 *   session (65); its label says how many changes the preview carried
 *   (66). Nothing to update -> a calm message (69). The badge on the
 *   sidebar shows only a real dry-run count > 0 (68).
 * - A sweep is not undoable (spec 12.2): the screen says so in one
 *   line.
 *
 * Five states everywhere: normal, loading, empty, error (inside the
 * block that failed, Retry + code on request), and a no-key state is
 * NOT this screen's — the sweep needs no key; the stale-question loop
 * is the engine's own decision (the step's deferred-settings contract).
 * The proposal panel keeps the pinned button order (Stop, Reject,
 * Confirm) with the step-03 look; `maintain` offers no Edit, so no
 * Edit button is drawn.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { statusPillHtml } from '../components/status-pill.mjs';
import { settleClass } from '../components/heat-mark.mjs';
import { emptyHtml } from '../components/state-block.mjs';
import { showErrorBlock, showLoadingBlock } from './blocks.mjs';
import { sentenceFor } from '../../shared/plain-sentences.mjs';
import {
  applyLabel,
  candidateLine,
  causeSentence,
  maintainDocumentFromMessage,
  phaseOutcomeSentence,
  resultHeadline,
  staleCapSentence,
  staleIntroSentence,
  sweepAnswerFor,
  sweepCountsSentence,
} from '../../shared/maintain-words.mjs';

const NOT_UNDOABLE =
  'A sweep cannot be undone. To reverse one result, fix the cause and sweep again.';
const APPLY_DISABLED_WHY =
  'Preview the sweep first. Apply stays off until you have seen what it would do.';

export function createCleanupScreen(ctx) {
  const model = {
    phase: 'idle', // idle | previewing | previewed | applying | result
    preview: null, // the dry-run document (D3: the engine's own data)
    names: null, // item number -> statement/type, from list-items
    namesNote: null, // a visible one-liner when the names read failed
    previewedOnce: false, // story 65: Apply unlocks on the first preview in this window session
    apply: null, // the live loop's collected state
    applyError: null, // the last failed session's error info
  };
  let rootEl = null;
  let handle = null; // the maintainApply session handle
  let keyHandler = null;

  /* ---------- frame ---------- */

  function render() {
    // A re-render replaces this screen: the loop's keys go with it, and
    // an abandoned loop is STOPPED (close the input; the engine treats
    // it as a quit — what was written before stays in the ledger).
    if (model.phase === 'applying' && handle) {
      handle.stop();
      handle = null;
    }
    disarmKeys();
    ctx.renderFrame(
      `<div data-testid="pane-cleanup">
        <div class="titlerow"><div class="grow"><h1>Clean up</h1>
          <p class="sub">A sweep checks every confirmed link and updates item statuses by fixed rules. Preview first, then apply.</p></div>
        </div>
        <p class="help" data-testid="cleanup-not-undoable">${esc(NOT_UNDOABLE)}</p>
        <div class="actions" data-testid="cleanup-actions"></div>
        <div data-testid="cleanup-body" style="margin-top:var(--s5)"></div>
      </div>`,
      (root) => {
        rootEl = root;
        renderActions();
        renderBody();
      },
    );
  }

  function renderActions() {
    if (!rootEl) return;
    const host = rootEl.querySelector('[data-testid="cleanup-actions"]');
    const count = model.preview ? model.preview.changes.length : null;
    const busy = model.phase === 'previewing' || model.phase === 'applying';
    const applyEnabled = model.previewedOnce && !busy;
    host.innerHTML = `${buttonHtml({ label: 'Preview the sweep', action: 'cleanup-preview', variant: 'secondary', disabled: busy ? 'The sweep is busy right now.' : null })}
      ${buttonHtml({
        label: count === null ? 'Apply changes' : applyLabel(count),
        action: 'cleanup-apply',
        variant: 'primary',
        disabled: applyEnabled ? null : APPLY_DISABLED_WHY,
        title: applyEnabled ? null : APPLY_DISABLED_WHY,
        testid: 'cleanup-apply',
      })}`;
    host.querySelector('[data-action="cleanup-preview"]')?.addEventListener('click', () => loadPreview());
    host.querySelector('[data-action="cleanup-apply"]')?.addEventListener('click', () => startApply());
  }

  function renderBody() {
    if (model.phase === 'previewing') {
      showLoadingBlock(body(), 'Checking every confirmed link…');
      return;
    }
    if (model.phase === 'idle') {
      body().innerHTML = `<p class="help">Apply stays off until you preview. Previewing changes nothing.</p>`;
      return;
    }
    if (model.phase === 'applying') {
      renderLoop();
      return;
    }
    if (model.phase === 'result') {
      renderResult();
      return;
    }
    if (model.phase === 'error') {
      // The error block was already drawn in place; nothing to redraw.
      return;
    }
    renderPreview();
  }

  function body() {
    return rootEl.querySelector('[data-testid="cleanup-body"]');
  }

  /* ---------- the preview (stories 63, 64, 66, 69 + the badge) ---------- */

  async function loadPreview() {
    disarmKeys();
    model.phase = 'previewing';
    model.preview = null;
    model.names = null;
    model.namesNote = null;
    renderActions();
    renderBody();
    showLoadingBlock(body(), 'Checking every confirmed link…');
    const [namesRes, previewRes] = await Promise.all([ctx.api.listItems({}), ctx.api.maintainPreview()]);
    if (namesRes && namesRes.ok) {
      const byId = {};
      for (const item of namesRes.data.items ?? []) byId[item.id] = item;
      model.names = byId;
    } else if (namesRes && namesRes.error) {
      // The preview itself can still run: the table falls back to item
      // numbers, and the failure is said out loud, never swallowed.
      model.namesNote = sentenceFor(namesRes.error.code).what;
    }
    if (!previewRes || !previewRes.ok) {
      model.phase = 'error';
      showErrorBlock(body(), previewRes ? previewRes.error : null, {
        what: 'the sweep preview',
        onRetry: () => loadPreview(),
      });
      renderActions();
      return;
    }
    model.preview = previewRes.document;
    model.previewedOnce = true;
    model.phase = 'previewed';
    renderActions();
    renderBody();
    // Story 68: the sidebar badge carries the real dry-run count.
    ctx.setCleanupBadge?.(model.preview.changes.length);
  }

  function itemName(id) {
    const item = model.names ? model.names[id] : null;
    return item && typeof item.statement === 'string' && item.statement !== '' ? item.statement : `Item ${id}`;
  }

  function renderPreview() {
    const document = model.preview;
    if (!document) return;
    const summary = document.summary ?? {};
    const changes = document.changes ?? [];
    const parts = [];
    parts.push(`<div class="ok" data-testid="cleanup-counts"><strong>${esc(staleIntroSentence(summary.stale) || 'What the sweep would change.')}</strong><span>${esc(sweepCountsSentence(summary, 'would'))}</span></div>`);
    if (namesNoteHtml()) parts.push(namesNoteHtml());
    if (changes.length === 0) {
      parts.push(`<div data-testid="cleanup-empty">${emptyHtml({ title: 'Nothing to update. Every status matches its links.' })}</div>`);
    } else {
      const rows = changes
        .map((change) => {
          const before = statusPillHtml(change.old_status);
          const after = statusPillHtml(change.new_status);
          return `<tr data-testid="cleanup-row-${esc(String(change.item_id))}">
            <td class="num dim">${esc(String(change.item_id))}</td>
            <td>${esc(itemName(change.item_id))}</td>
            <td data-testid="cleanup-move-${esc(String(change.item_id))}">${before}<span class="dim" aria-hidden="true"> → </span>${after}</td>
            <td class="dim">${esc(causeSentence(change))}${change.new_status === 'Closed' && change.close_reason ? ` (reason: ${esc(change.close_reason)})` : ''}</td>
          </tr>`;
        })
        .join('');
      parts.push(`<div class="panel"><table class="ember-table" data-testid="cleanup-table">
        <thead><tr><th class="num">No.</th><th>Item</th><th>Becomes</th><th>Because</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`);
    }
    const stale = summary.stale_candidates ?? null;
    if (stale && Array.isArray(stale.candidates) && stale.candidates.length > 0) {
      const cap = staleCapSentence(stale.truncated);
      parts.push(`<div class="panel" data-testid="cleanup-stale"><div class="pad">
        <p class="hint" data-testid="cleanup-stale-cap">${esc(cap)}</p>
        <ul class="lineage" data-testid="cleanup-stale-list">
          ${stale.candidates.map((candidate) => `<li>${esc(candidateLine(candidate))}</li>`).join('')}
        </ul>
      </div></div>`);
    }
    body().innerHTML = parts.join('');
  }

  function namesNoteHtml() {
    if (!model.namesNote) return '';
    return `<div class="panel" data-testid="cleanup-names-note"><div class="pad"><p class="hint">Item names could not be read just now, so the table shows numbers only. ${esc(model.namesNote)}</p></div></div>`;
  }

  /* ---------- the apply session (stories 63, 67 + the loop) ---------- */

  function startApply() {
    if (!model.previewedOnce || model.phase === 'applying') return;
    model.phase = 'applying';
    model.apply = { messages: [], pending: null, awaiting: false, result: null, stopped: false, error: null };
    renderActions();
    renderBody();
    armKeys();
    handle = ctx.api.maintainApply((payload) => onSessionPayload(payload));
    handle.done.then((result) => {
      if (!result || !result.ok) {
        // The session never started (the gate refused, or a sweep was
        // already running): end the loop with the plain words.
        model.apply.error = result && result.error ? result.error : null;
        finishApply();
      }
    });
  }

  function onSessionPayload(payload) {
    if (!model.apply || model.phase !== 'applying') return;
    if (payload.kind === 'event') {
      onSessionEvent(payload.event);
      return;
    }
    if (payload.kind === 'error') {
      model.apply.error = payload.info;
      return;
    }
    if (payload.kind === 'exit') {
      finishApply();
    }
  }

  function onSessionEvent(event) {
    const state = model.apply;
    if (event.event === 'message' && typeof event.text === 'string') {
      const doc = maintainDocumentFromMessage(event.text);
      if (doc !== null) {
        state.result = doc;
        return;
      }
      // The engine's own report lines (the accepted-close writes), as
      // inline messages — name by name.
      state.messages.push(event.text);
      renderLoop();
      return;
    }
    if (event.event === 'block' && event.kind === 'close') {
      const fields = event.fields && typeof event.fields === 'object' ? event.fields : null;
      if (fields === null) {
        // Drift: the raw block is kept visible, no data is lost (D4).
        state.messages.push(event.text);
        renderLoop();
        return;
      }
      if (typeof fields.reason !== 'string') {
        state.messages.push(`Ember proposed no close for item ${fields.item_id}; it stays as it is.`);
        renderLoop();
        return;
      }
      state.pending = { fields, awaiting: false };
      state.awaiting = false;
      renderLoop();
      return;
    }
    if (event.event === 'prompt') {
      // The REAL prompt arrived: the loop is open, the pinned answers
      // map onto this prompt's own choices.
      if (state.pending) state.pending.awaiting = true;
      state.awaiting = true;
      renderLoop();
      return;
    }
  }

  function renderLoop() {
    const state = model.apply;
    if (!state) return;
    const messages = state.messages
      .map((line) => `<li class="dim" data-testid="sweep-message">${esc(line)}</li>`)
      .join('');
    let proposalHtml = `<p class="hint" data-testid="sweep-working">Applying the sweep. This runs one command; the ledger gets every change.</p>`;
    if (state.pending) {
      const fields = state.pending.fields;
      const head = `Old question ${esc(String(fields.index))} of ${esc(String(fields.total))} · item ${esc(String(fields.item_id))} [${esc(String(fields.item_type))}]`;
      const meta = `Newest answers link ${esc(String(fields.newest_answers_link_id))}, confirmed ${esc(String(fields.newest_answer_created_at ?? ''))}.`;
      const judge = `Ember proposes closing it as <strong>${esc(String(fields.reason))}</strong> (confidence ${esc(String(fields.confidence))}).`;
      const rationale = fields.rationale ? esc(String(fields.rationale)) : 'none given';
      const buttons = state.pending.awaiting
        ? `<div class="actions">
            ${buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'sweep-stop', variant: 'text', testid: 'sweep-stop' })}
            ${buttonHtml({ label: 'Reject', kbd: 'n', action: 'sweep-reject', variant: 'secondary', testid: 'sweep-reject' })}
            ${buttonHtml({ label: 'Confirm', kbd: 'Return', action: 'sweep-confirm', variant: 'primary', testid: 'sweep-confirm' })}
          </div>
          <p class="hint">Stop closes the session after what was already written. Reject keeps the question open. Confirm closes it and writes the ledger line.</p>`
        : `<p class="hint" data-testid="sweep-waiting">Waiting for the sweep…</p>`;
      proposalHtml = `<div class="panel tone" data-testid="sweep-proposal"><div class="pad">
        <p class="lbl">${head}</p>
        <p class="statement"><strong>${esc(itemName(fields.item_id))}</strong></p>
        <p class="hint">${esc(meta)}</p>
        <p class="hint" data-testid="sweep-judgment">${judge} Rationale: ${rationale}.</p>
        ${buttons}
      </div></div>`;
    }
    body().innerHTML = `<div data-testid="sweep-loop">
      ${proposalHtml}
      ${messages ? `<ul class="lineage" data-testid="sweep-messages" style="margin-top:var(--s4)">${messages}</ul>` : ''}
    </div>`;
    body().querySelector('[data-action="sweep-confirm"]')?.addEventListener('click', () => loopAct('confirm'));
    body().querySelector('[data-action="sweep-reject"]')?.addEventListener('click', () => loopAct('reject'));
    body().querySelector('[data-action="sweep-stop"]')?.addEventListener('click', () => loopAct('stop'));
  }

  async function loopAct(action) {
    const state = model.apply;
    if (!state || !state.awaiting || !handle) return;
    state.awaiting = false;
    if (state.pending) state.pending.awaiting = false;
    renderLoop();
    if (action === 'stop') {
      state.stopped = true;
      handle.stop(); // close the input; the engine reads that as a quit
      return;
    }
    const answer = sweepAnswerFor(action);
    const asked = state.pending ? state.pending.fields.item_id : null;
    if (action === 'reject' && asked !== null) {
      state.messages.push(`You declined the close for item ${asked}; nothing was written.`);
      renderLoop();
    } else if (action === 'confirm' && asked !== null) {
      state.messages.push(`You confirmed the close for item ${asked}; the engine writes it now.`);
      renderLoop();
    }
    const sent = await handle.answer(answer);
    if (sent && !sent.ok && sent.error) {
      state.error = sent.error;
    }
  }

  function finishApply() {
    disarmKeys();
    handle = null;
    const state = model.apply;
    if (!state) return;
    // A write happened (or was attempted): the next Apply needs a fresh
    // preview, and the badge gets the fresh count (plan: refreshed
    // after any write).
    model.previewedOnce = false;
    model.preview = null;
    refreshBadge();
    if (state.result) {
      model.phase = 'result';
      renderActions();
      renderResult();
      return;
    }
    if (state.error) {
      model.phase = 'error';
      renderActions();
      showErrorBlock(body(), state.error, {
        what: 'the sweep',
        onRetry: () => loadPreview(),
      });
      body().insertAdjacentHTML(
        'beforeend',
        `<p class="help">The changes written before this stop are in the ledger. The sweep above stopped; nothing more will change before you preview again.</p>`,
      );
      return;
    }
    model.phase = 'error';
    renderActions();
    showErrorBlock(body(), null, { what: 'the sweep', onRetry: () => loadPreview() });
  }

  /** The result (story 67): what changed, with the new heat marks —
    * the ONE settle motion runs here, at the visible moment of change
    * (DESIGN.md Motion: "the changed items after a sweep"). */
  function renderResult() {
    const state = model.apply;
    const document = state && state.result ? state.result : null;
    if (!document) return;
    const summary = document.summary ?? {};
    const changes = document.changes ?? [];
    const stopped = summary.aborted === true || (state && state.stopped);
    const rows = changes
      .map((change) => {
        const settle = settleClass(change.old_status, change.new_status);
        const pill = statusPillHtml(change.new_status, { settle });
        return `<tr data-testid="cleanup-result-row-${esc(String(change.item_id))}">
          <td class="num dim">${esc(String(change.item_id))}</td>
          <td>${esc(itemName(change.item_id))}</td>
          <td data-testid="cleanup-result-now-${esc(String(change.item_id))}">${pill}</td>
          <td class="dim">${esc(causeSentence(change))}${change.new_status === 'Closed' && change.close_reason ? ` (reason: ${esc(change.close_reason)})` : ''}</td>
        </tr>`;
      })
      .join('');
    const transcript = state.messages
      .map((line) => `<li class="dim">${esc(line)}</li>`)
      .join('');
    body().innerHTML = `<div data-testid="sweep-result">
      <div class="ok" data-testid="sweep-result-headline"><strong>${esc(stopped ? 'Stopped. ' : '')}${esc(resultHeadline(summary))}</strong>
        <span>${esc(sweepCountsSentence(summary, 'did'))}</span>
        <span>${esc(phaseOutcomeSentence(summary))}</span>
      </div>
      ${rows ? `<div class="panel" style="margin-top:var(--s4)"><table class="ember-table" data-testid="cleanup-result-table">
        <thead><tr><th class="num">No.</th><th>Item</th><th>Now</th><th>Because</th></tr></thead>
        <tbody>${rows}</tbody></table></div>` : ''}
      ${transcript ? `<ul class="lineage" data-testid="sweep-result-messages" style="margin-top:var(--s4)">${transcript}</ul>` : ''}
      <p class="help">Preview again to see what is left. ${esc(NOT_UNDOABLE)}</p>
    </div>`;
  }

  async function refreshBadge() {
    // Best effort: the plan's "refreshed after any write". A failed
    // refresh leaves the old badge in place; the next preview on this
    // screen or Home's own check corrects it.
    try {
      const res = await ctx.api.maintainPreview();
      if (res && res.ok) ctx.setCleanupBadge?.(res.document.changes.length);
    } catch (err) {
      // The refresh is background, but never silent: the renderer log
      // carries it (no key, no raw child output in this error).
      console.warn('sweep-badge-refresh-failed:', err instanceof Error ? err.message : String(err));
    }
  }

  /* ---------- the loop's keyboard (the engine's own prompt) ---------- */

  function armKeys() {
    disarmKeys();
    keyHandler = (event) => {
      const state = model.apply;
      if (!state || !state.awaiting) return;
      const onButton = document.activeElement && document.activeElement.tagName === 'BUTTON';
      if (event.key === 'Escape') {
        event.preventDefault();
        loopAct('stop');
      } else if (event.key === 'n' || event.key === 'N') {
        event.preventDefault();
        loopAct('reject');
      } else if (event.key === 'y' || event.key === 'Y') {
        event.preventDefault();
        loopAct('confirm');
      } else if (event.key === 'Enter' && !onButton) {
        // Enter confirms; on a focused button the click event already
        // carries the same answer, so do not answer twice.
        event.preventDefault();
        loopAct('confirm');
      }
    };
    // The loop owns the whole page while it is open, so the keys are
    // bound at the document level (focus moves: buttons, the frame).
    document.addEventListener('keydown', keyHandler);
  }

  function disarmKeys() {
    if (keyHandler) {
      document.removeEventListener('keydown', keyHandler);
      keyHandler = null;
    }
  }

  return { render, loadPreview };
}

/**
 * Link items (app step 06, spec stories 42-48): pick the item to
 * relate from the list `list-items` returns (never a typed id, step
 * file §1), then the REAL `ember relate --item N --confirm json --db
 * <kb>` session (or `--latest`) — link proposals rendered from the
 * pinned `link-preview` blocks (both items and the relationship in
 * ONE proposal, 43), choices Confirm / Skip / Reject with Stop (y /
 * s / n / q, Return / Esc, 44), the accepted link block shown after y,
 * the engine's gatekeeper rejections (`relate rejected: ...` lines)
 * inline in plain words, the summary event as the final state with the
 * engine's own counts (47), the honest "not undone by Undo" note (the
 * rollback is Fix and close -> Remove link, step file §5), the calm
 * preparing state with Stop when no event has arrived (45), the
 * no-unrelated-items empty state (46), and the no-key path (48) — the
 * same as Add's.
 *
 * Every state is a step-03 five-state state (loading, empty, error,
 * no-key, normal). The screen talks ONLY through the window.ember
 * preload list (B5). Buttons in the pinned order for link proposals:
 * Stop (Esc), Skip (s), Reject (n), Confirm (Return) — DESIGN.md.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { statusPillHtml } from '../components/status-pill.mjs';
import { errorHtml, emptyHtml, loadingHtml, noKeyHtml, bindStateBlock } from '../components/state-block.mjs';
import { dataOrNull, showLoadingBlock } from './blocks.mjs';
import {
  initialRelateView,
  applyRelateEvent,
  pickRowFor,
  recordConfirm,
  relateSummarySentence,
} from '../../shared/relate-view.mjs';
import { humanLinkType } from '../../shared/plain-sentences.mjs';
import { relateErrorSentence, relateRejectionLine } from '../../shared/relate-words.mjs';

export function createLinkScreen(ctx) {
  const state = {
    phase: 'pick', // pick | session | done | error
    stage: null, // done's own stage: summary | empty | stopped | ended-early
    view: initialRelateView(),
    keyMissing: false,
    kbInvalid: false,
    pick: { state: 'idle', rows: [], total: 0 }, // the list-items page
    pickedItem: null, // {id, type, statement} — the run's own item
    error: null,
    exitCode: null,
    busy: false, // one answer in flight
    preparing: false, // no event yet after the first second (story 45)
    unsub: [],
    prepareTimer: null,
    keydownHandler: null,
    renderedLinkCount: 0, // accepted rows already rendered (motion pin)
  };

  let rootEl = null;
  let flowEl = null;
  let pickEl = null;

  function unlisten() {
    for (const off of state.unsub) {
      try {
        off();
      } catch {
        /* already gone */
      }
    }
    state.unsub = [];
  }

  /* ---------------- the pick list ---------------- */

  const NO_ITEMS_YET = {
    title: 'No items yet. Your knowledge base file is created the first time you add text.',
    next: 'Add your first text',
    onNext: 'link-empty-add',
  };

  function emptyPickHtml() {
    return emptyHtml(NO_ITEMS_YET);
  }

  async function loadPick() {
    if (!pickEl) return;
    showLoadingBlock(pickEl, 'Reading the items…');
    const result = await ctx.api.listItems({});
    const data = dataOrNull(pickEl, result, { what: 'the item list', onRetry: loadPick });
    if (data === null) return;
    if (state.phase !== 'pick') return;
    state.pick = { state: 'ok', rows: data.items ?? [], total: data.total ?? 0 };
    renderPane();
  }

  function renderPick() {
    if (!pickEl) return;
    if (state.pick.rows.length === 0) {
      pickEl.innerHTML = emptyPickHtml();
      bindStateBlock(pickEl, { 'link-empty-add': () => ctx.navigate('add') });
      return;
    }
    const rows = state.pick.rows.map((it) => pickRowHtml(it)).join('');
    pickEl.innerHTML = `<p class="help" style="margin-top:0">Pick the item Ember should relate to the rest of your knowledge base. Ember proposes how it links to other items; you confirm each link.</p>
      <div class="panel"><table class="ember-table" data-testid="link-table">
      <thead><tr><th class="num nowrap">No.</th><th class="nowrap">Type</th><th>Item</th><th class="nowrap">Status</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <div class="actions">${buttonHtml({
        label: 'Use the newest item instead',
        action: 'link-latest',
        variant: 'secondary',
        testid: 'link-latest',
        title: 'Ember picks the newest Active item with no link yet',
      })}</div>`;
    pickEl.querySelector('[data-action="link-latest"]')?.addEventListener('click', () => startSession({ latest: true }));
    pickEl.querySelectorAll('tr.row-click').forEach((row) => {
      row.addEventListener('click', () => startSession({ item: Number(row.dataset.id) }));
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          startSession({ item: Number(row.dataset.id) });
        }
      });
    });
  }

  /* ---------------- the running session ---------------- */

  function itemWords(id) {
    const row = pickRowFor(state.pick.rows, id);
    if (row.statement === null) return `item ${row.id}`;
    return `item ${row.id} (${row.statement})`;
  }

  function proposalHtml() {
    const view = state.view;
    if (!view.proposal) return '';
    const f = view.proposal.fields;
    if (!f) {
      // Drift (fields null): fail loud, the raw block stays the evidence.
      return `<div class="panel"><div class="pad"><p class="lbl">A proposal Ember could not read as data</p>
        <pre class="source-verbatim">${esc(view.proposal.text)}</pre></div></div>`;
    }
    const type = typeof f.link_type === 'string' ? f.link_type : '';
    const rationale =
      typeof f.rationale === 'string' && f.rationale.trim() !== ''
        ? `<p class="help" data-testid="link-rationale">Ember's reason: ${esc(f.rationale)}</p>`
        : '<p class="help" data-testid="link-rationale">Ember gave no reason.</p>';
    const progress =
      Number.isInteger(f.index) && Number.isInteger(f.total)
        ? `<p class="help" style="margin:0 0 var(--s3)" data-testid="link-progress">Proposal ${f.index} of ${f.total}.</p>`
        : '';
    return `<div class="panel tone" data-testid="link-proposal"><div class="pad">${progress}
      <div><span class="dim">${esc(itemWords(f.source_item_id))}</span></div>
      <div style="margin:var(--s2) 0"><strong>${esc(humanLinkType(type))}</strong></div>
      <div><span class="dim">${esc(itemWords(f.target_item_id))}</span></div>
      ${rationale}
    </div></div>`;
  }

  function choiceButtonsHtml() {
    // The pinned link order (DESIGN.md): Stop (Esc), Skip (s),
    // Reject (n), Confirm (Return).
    const buttons = [
      buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text' }),
      buttonHtml({ label: 'Skip', kbd: 's', action: 'proposal-skip', variant: 'secondary' }),
      buttonHtml({ label: 'Reject', kbd: 'n', action: 'proposal-reject', variant: 'secondary' }),
      buttonHtml({ label: 'Confirm', kbd: 'Return', action: 'proposal-confirm', variant: 'primary' }),
    ].join('');
    return `<div class="actions" data-testid="link-choice">${buttons}</div>`;
  }

  function unknownPromptHtml() {
    const view = state.view;
    return `<div class="errbox" role="alert" data-testid="link-unknown-prompt"><strong>Ember asked something this app does not know.</strong>
      <span class="detail">${esc(view.unknownPrompt ? view.unknownPrompt.text : '')}</span>
      <div class="actions">
        <label for="link-raw-answer" class="help" style="margin:0">Answer with exactly the text Ember asked for</label>
        <input type="text" id="link-raw-answer" data-testid="link-raw-answer">
        <button type="button" class="btn btn--primary" data-testid="link-raw-submit">Send the answer</button>
        ${buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text' })}
      </div></div>`;
  }

  function preparingHtml() {
    return `<div class="panel tone" data-testid="link-preparing"><div class="pad">
      <p style="margin:0"><strong>Ember is preparing to link.</strong></p>
      <p class="help" style="margin:var(--s2) 0 0">The first time, this can take minutes while a language model is downloaded.
      The window is working; nothing is frozen, and nothing is changed yet.</p>
      <div class="actions">${buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text', testid: 'link-preparing-stop' })}</div>
    </div></div>`;
  }

  function linksSoFarHtml() {
    const view = state.view;
    if (view.links.length === 0) return '';
    const rows = view.links
      .map((link, index) => {
        // DESIGN.md Motion: only the rows that appeared since the last
        // render animate, so a later re-render never replays the mark.
        const isNew = index >= state.renderedLinkCount;
        return `<tr data-testid="linked-row"><td class="num dim">${link.linkId ?? '—'}</td>
          <td>${esc(itemWords(link.sourceItemId))}</td>
          <td class="nowrap"><strong>${esc(humanLinkType(link.linkType))}</strong></td>
          <td>${esc(itemWords(link.targetItemId))}</td>
          <td class="nowrap">${statusPillHtml('Active', { settle: isNew ? 'heat--settle-heat' : '' })}</td></tr>`;
      })
      .join('');
    state.renderedLinkCount = view.links.length;
    return `<h2>Linked so far</h2><div class="panel"><table class="ember-table" data-testid="link-linked">
      <thead><tr><th class="num">Link</th><th>From</th><th class="nowrap">Relationship</th><th>To</th><th class="nowrap">Status</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }

  function logHtml() {
    const view = state.view;
    if (view.log.length === 0) return '';
    const lines = view.log.map((line) => `<li>${esc(relateRejectionLine(line))}</li>`).join('');
    return `<ul class="help" data-testid="link-log" role="log" aria-label="Messages from Ember while linking" style="margin:var(--s2) 0 0">${lines}</ul>`;
  }

  function sessionHtml() {
    let inner = '';
    if (state.preparing) {
      // Story 45: calm words while the engine prepares (the first run
      // may download a language model); Stop stays reachable.
      inner = preparingHtml();
    } else if (!state.view.seenAny) {
      inner = loadingHtml({ hint: 'Ember is reading the candidate items… Nothing is changed yet.' });
    } else {
      const body =
        state.view.awaiting === 'unknown'
          ? unknownPromptHtml()
          : `${proposalHtml()}${state.view.awaiting === 'choice' ? choiceButtonsHtml() : ''}`;
      inner = `<div aria-live="polite">${logHtml()}${body}</div>${linksSoFarHtml()}`;
    }
    return `<div data-testid="link-flow">${inner}</div>`;
  }

  /* ---------------- the end states ---------------- */

  function endHtml() {
    const view = state.view;
    if (state.stage === 'summary') {
      const note = `<p class="help" data-testid="link-undo-note" style="margin:0 0 var(--s4)">Links made here are not undone by the Undo button.
        To change one, open Fix and close: removing a link marks it Rejected, and nothing is ever deleted.</p>`;
      return `<h2>Done</h2><div class="panel"><div class="pad">
        <p class="help" data-testid="link-summary-line" style="margin:0 0 var(--s3)">${esc(relateSummarySentence(view.summary))}</p>
        <div aria-live="polite">${logHtml()}</div>
        ${note}
        <div class="actions">${buttonHtml({ label: 'Link another item', action: 'link-again', variant: 'primary', testid: 'link-again' })}
        ${buttonHtml({ label: 'Go to Home', action: 'link-home', variant: 'secondary', testid: 'link-home' })}</div>
      </div></div>${linksSoFarHtml()}`;
    }
    if (state.stage === 'empty') {
      const about = state.pickedItem
        ? `No unrelated items are left to link for item ${state.pickedItem.id}.`
        : 'No unrelated items are left to link.';
      const extra = view.emptyText && view.emptyText !== 'no unrelated items' ? ' Ember found no candidates worth proposing for it.' : '';
      return `<h2>Done</h2><div class="panel"><div class="pad">
        <p class="help" data-testid="link-empty-line" style="margin:0">${esc(about)}${esc(extra)}</p>
        <div class="actions">${buttonHtml({ label: 'Link another item', action: 'link-again', variant: 'primary', testid: 'link-again' })}</div>
      </div></div>`;
    }
    if (state.stage === 'stopped') {
      const a = view.links.length;
      const what = view.summary
        ? `You stopped early. ${a} ${a === 1 ? 'link was' : 'links were'} confirmed; nothing is half-written.`
        : 'You stopped before Ember finished preparing. Nothing was changed.';
      return `<h2>Stopped</h2><div class="panel"><div class="pad"><p class="help" data-testid="link-stopped-line" style="margin:0">${esc(what)}</p>
        <div class="actions">${buttonHtml({ label: 'Link another item', action: 'link-again', variant: 'primary', testid: 'link-again' })}</div>
      </div></div>${linksSoFarHtml()}`;
    }
    // 'ended-early': the run stopped without its report and without
    // the engine's documented empty-pool print (APP-002, I5/I7).
    const err = {
      code: 'APP-002',
      name: 'BridgeOutputInvalid',
      where: 'link',
      detail: `the link run ended without its report (exit ${state.exitCode ?? 'unknown'}); links already confirmed are kept, and you can check them in Look up`,
    };
    return errorBlockHtml(err);
  }

  /* ---------------- the error state ---------------- */

  function errorBlockHtml(err) {
    const s = relateErrorSentence(err);
    const setupButton = s.openSetup
      ? buttonHtml({ label: 'Set up the AI connection', action: 'link-open-setup', variant: 'secondary', testid: 'link-open-setup' })
      : '';
    return `<div data-testid="link-error">${errorHtml({
      title: s.title,
      detail: s.what,
      why: s.next,
      onRetry: s.retry ? 'link-retry' : 'link-again',
    })}${setupButton}
      <p class="help" data-testid="error-code" hidden>${esc(`${err ? `${err.code} ${err.name} | ${err.detail}` : 'no details'}`)}</p></div>`;
  }

  function wireErrorBlock(host) {
    bindStateBlock(host, {
      'link-retry': () => restartLast(),
      'link-again': () => backToPick(),
      'link-open-setup': () => ctx.openSetup(),
      'show-details': () => {
        const code = host.querySelector('[data-testid="error-code"]');
        if (code) code.hidden = !code.hidden;
      },
    });
  }

  /* ---------------- render the pane ---------------- */

  function renderPane() {
    if (!rootEl) return;
    const gate = rootEl.querySelector('[data-testid="link-gate"]');
    if (state.kbInvalid) {
      const err = {
        code: 'APP-006',
        name: 'KnowledgeBaseMissing',
        where: 'link',
        detail: 'the chosen knowledge base file is not an Ember file',
      };
      pickEl.innerHTML = '';
      flowEl.innerHTML = '';
      gate.innerHTML = errorBlockHtml(err);
      wireErrorBlock(gate);
      return;
    }
    if (state.keyMissing) {
      // Story 48: without a key, Link says it needs the connection,
      // the same path as Add (story 29).
      gate.innerHTML = noKeyHtml({ what: 'Linking items', onOpenSettings: 'link-open-setup' });
      gate.querySelector('[data-action="link-open-setup"]')?.addEventListener('click', () => ctx.openSetup());
      return;
    }
    gate.innerHTML = '';
    if (state.phase === 'pick') {
      flowEl.innerHTML = '';
      renderPick();
      return;
    }
    if (state.phase === 'session' || state.phase === 'done') {
      flowEl.innerHTML = state.phase === 'done' ? endHtml() : sessionHtml();
      wireFlow();
      // A re-render drops the focus to the page body (story 96: the
      // keyboard never dead-ends).
      ctx.paneEl().focus({ preventScroll: true });
      return;
    }
    // error
    pickEl.innerHTML = '';
    flowEl.innerHTML = errorBlockHtml(state.error);
    wireErrorBlock(flowEl);
  }

  function wireFlow() {
    if (state.phase === 'session') {
      bindStateBlock(flowEl, {
        'proposal-confirm': () => answerChoice('y'),
        'proposal-skip': () => answerChoice('s'),
        'proposal-reject': () => answerChoice('n'),
        'proposal-stop': () => stopSession(),
      });
      flowEl.querySelector('[data-testid="link-raw-submit"]')?.addEventListener('click', () => submitRawAnswer());
      flowEl.querySelector('[data-testid="link-raw-answer"]')?.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          submitRawAnswer();
        }
      });
      if (state.view.awaiting === 'unknown') flowEl.querySelector('[data-testid="link-raw-answer"]')?.focus();
      return;
    }
    flowEl.querySelector('[data-action="link-again"]')?.addEventListener('click', () => backToPick());
    flowEl.querySelector('[data-action="link-home"]')?.addEventListener('click', () => ctx.navigate('home'));
  }

  /* ---------------- the session itself ---------------- */

  function beginPrepareTimer() {
    clearTimeout(state.prepareTimer);
    state.prepareTimer = setTimeout(() => {
      if (state.phase === 'session' && !state.view.seenAny) {
        state.preparing = true;
        renderPane();
      }
    }, 1000);
  }

  async function startSession(ask) {
    // Subscriptions FIRST, attach after relateStart resolves: a child
    // that refuses instantly must still reach the screen (the App 05
    // pattern; the app core buffers until attachRelate).
    unlisten();
    state.unsub = [
      ctx.api.onRelateEvent((ev) => {
        clearTimeout(state.prepareTimer);
        state.busy = false;
        state.preparing = false;
        state.view = applyRelateEvent(state.view, ev);
        renderPane();
      }),
      ctx.api.onRelateExit(({ exitCode, error }) => {
        clearTimeout(state.prepareTimer);
        unlisten();
        finishSession({ exitCode, error });
      }),
    ];
    state.phase = 'session';
    state.stage = null;
    state.view = initialRelateView();
    state.busy = false;
    state.preparing = false;
    state.error = null;
    state.exitCode = null;
    state.renderedLinkCount = 0;
    state.pickedItem =
      ask.latest === true
        ? null
        : ask.item !== undefined && ask.item !== null
          ? pickRowFor(state.pick.rows, ask.item)
          : state.pickedItem;
    renderPane();
    beginPrepareTimer();
    const res = await ctx.api.startRelate(ask);
    if (!res || !res.ok) {
      clearTimeout(state.prepareTimer);
      unlisten();
      state.phase = 'error';
      state.error = res ? res.error : null;
      renderPane();
      return;
    }
    await ctx.api.attachRelate();
  }

  /** Retry after a mid-run failure: the same item again. */
  function restartLast() {
    if (state.pickedItem) startSession({ item: state.pickedItem.id });
    else startSession({ latest: true });
  }

  function finishSession({ exitCode, error }) {
    state.exitCode = exitCode;
    if (error) {
      state.phase = 'error';
      state.stage = null;
      state.error = error;
      renderPane();
      return;
    }
    const view = state.view;
    if (view.summary) {
      // The engine's own summary event is THE final state (D3, 47);
      // its aborted flag says the user stopped (22's link twin).
      state.phase = 'done';
      state.stage = view.summary.aborted ? 'stopped' : 'summary';
    } else if (view.emptySignal) {
      state.phase = 'done';
      state.stage = 'empty';
    } else if (exitCode === 2) {
      state.phase = 'done';
      state.stage = 'stopped';
    } else {
      state.phase = 'error';
      state.stage = null;
      state.error = {
        code: 'APP-002',
        name: 'BridgeOutputInvalid',
        where: 'link',
        detail: `the link run ended without its report (exit ${exitCode ?? 'unknown'}); links already confirmed are kept, and you can check them in Look up`,
      };
    }
    renderPane();
  }

  async function answerChoice(letter) {
    if (state.phase !== 'session' || state.busy || state.view.awaiting !== 'choice') return;
    state.busy = true; // one answer in flight; the next event or the exit clears it
    if (letter === 'y') state.view = recordConfirm(state.view);
    renderPane();
    const sent = await ctx.api.answerRelate(letter);
    if (!sent || !sent.ok) {
      state.phase = 'error';
      state.error = sent ? sent.error : null;
      state.busy = false;
      renderPane();
    }
  }

  async function submitRawAnswer() {
    if (state.phase !== 'session' || state.busy) return;
    const field = flowEl.querySelector('[data-testid="link-raw-answer"]');
    state.busy = true;
    const sent = await ctx.api.answerRelate(field ? field.value : '');
    if (!sent || !sent.ok) {
      state.phase = 'error';
      state.error = sent ? sent.error : null;
      state.busy = false;
      renderPane();
    }
  }

  async function stopSession() {
    if (state.phase !== 'session') return;
    clearTimeout(state.prepareTimer);
    const stopped = await ctx.api.stopRelate();
    if (!stopped || !stopped.ok) {
      state.phase = 'error';
      state.error = stopped ? stopped.error : null;
      renderPane();
    }
  }

  function backToPick() {
    unlisten();
    clearTimeout(state.prepareTimer);
    state.phase = 'pick';
    state.stage = null;
    state.view = initialRelateView();
    state.error = null;
    state.busy = false;
    state.preparing = false;
    state.pickedItem = null;
    state.exitCode = null;
    state.renderedLinkCount = 0;
    renderPane();
    loadPick();
  }

  /* ---------------- keyboard (story 44; the Add pattern, 23) ---------------- */

  function installKeyboard() {
    const pane = ctx.paneEl();
    if (state.keydownHandler) return;
    state.keydownHandler = (ev) => {
      if (state.phase !== 'session' || !flowEl) return;
      if (ev.key === 'Escape') {
        ev.preventDefault();
        void stopSession();
        return;
      }
      const el = document.activeElement;
      // A control has the focus: its own activation covers Enter, and
      // the single-letter keys must never fire while the user types.
      if (el && el !== document.body && /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(el.tagName)) return;
      if (state.busy || state.view.awaiting !== 'choice') return;
      if (ev.key === 'Enter' || ev.key === 'y') void answerChoice('y');
      else if (ev.key === 's') void answerChoice('s');
      else if (ev.key === 'n') void answerChoice('n');
      else if (ev.key === 'q') void stopSession();
    };
    pane.addEventListener('keydown', state.keydownHandler);
  }

  /* ---------------- the five-state gate ---------------- */

  async function render() {
    ctx.renderFrame(
      `<div data-testid="link-pane">
        <div class="titlerow"><div class="grow"><h1>Link items</h1>
          <p class="sub">Ember proposes how items relate: supports, contradicts, supersedes, answers or depends on. You confirm each link.</p></div></div>
        <div data-testid="link-gate"></div>
        <div data-testid="link-pick"></div>
        <div data-testid="link-flow-host"></div>
      </div>`,
      () => {
        rootEl = ctx.paneEl();
        pickEl = rootEl.querySelector('[data-testid="link-pick"]');
        flowEl = rootEl.querySelector('[data-testid="link-flow-host"]');
        installKeyboard();
      },
    );
    const gate = await ctx.gate();
    if (gate === 'nosuch') {
      pickEl.innerHTML = emptyPickHtml();
      bindStateBlock(pickEl, { 'link-empty-add': () => ctx.navigate('add') });
      return;
    }
    if (gate === 'invalid') {
      state.kbInvalid = true;
      renderPane();
      return;
    }
    const status = await ctx.api.keyStatus();
    state.keyMissing = !(status && (status.stored || status.sessionOnly));
    renderPane();
    if (!state.keyMissing) loadPick();
  }

  return { render, state };
}

/* ---------- pure row helper (unit-testable; the lookup pattern) ---------- */

export function pickRowHtml(it) {
  const label = `Item ${String(it.id)}, ${it.type ?? ''}: ${String(it.statement ?? '').replace(/\s+/g, ' ').trim()}, ${it.status}`;
  return `<tr class="row-click" data-id="${esc(String(it.id))}" tabindex="0" aria-selected="false"
    aria-label="${esc(label)}" data-testid="link-row-${esc(String(it.id))}">
    <td class="num dim">${esc(String(it.id))}</td>
    <td class="dim">${esc(it.type ?? '')}</td>
    <td>${esc(it.statement ?? '')}</td>
    <td>${statusPillHtml(it.status)}</td>
  </tr>`;
}

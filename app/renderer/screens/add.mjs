/**
 * Add (app step 05, spec stories 16-29): paste text and press one
 * button (16); the notice that the text is kept word for word and sent
 * to the AI service (17); the confirm loop rendered from the REAL
 * `ember capture --file <temp> --confirm json --db <kb>` events —
 * blocks with parsed fields, prompts (choice and the edit sub-prompts
 * type/statement/metadata), message lines (drops, gatekeeper
 * rejections) shown inline, and the summary event as the final state
 * with a one-click path to Link items (18, 20, 21, 25, 26).
 *
 * Return confirms, Esc stops, e/n/y/q work (23); a "Saved so far" list
 * while working (24); zero proposals shows the empty state (28); the
 * no-key state points at the connection (29); a failed session shows
 * the plain error words with Retry (27, and the decision 5-A key
 * refusal at the first Add). Every state is a step-03 five-state
 * state (loading, empty, error, no-key, normal). The screen talks ONLY
 * through the window.ember preload list (B5).
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { proposalBlockHtml, PROPOSAL_TYPES } from '../components/proposal-block.mjs';
import { statusPillHtml } from '../components/status-pill.mjs';
import { errorHtml, emptyHtml, loadingHtml, noKeyHtml, bindStateBlock } from '../components/state-block.mjs';
import { initialAddView, applyAddEvent, addStage, recordConfirm } from '../../shared/confirm-view.mjs';
import { addErrorSentence } from '../../shared/capture-words.mjs';

export function createAddScreen(ctx) {
  const state = {
    phase: 'form', // form | session | done | error
    text: '',
    view: initialAddView(),
    error: null, // {code, name, where, detail}
    keyMissing: false,
    kbInvalid: false,
    unsub: [],
    busy: false, // an answer is on its way to the engine; one at a time
  };

  let rootEl = null;
  let flowEl = null;
  let formEl = null;
  let keydownHandler = null;
  let renderedSavedCount = 0; // the Saved so far rows already rendered (motion pin)

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

  function boardMessage(kind, text) {
    return kind === 'error'
      ? `<div class="errbox" role="alert" data-testid="add-message"><strong>${esc(text)}</strong></div>`
      : `<div class="ok" role="status" data-testid="add-message">${esc(text)}</div>`;
  }

  /* ---------------- the draft (input) form ---------------- */

  function formHtml() {
    return `<div class="panel tone"><div class="pad"><p class="help" style="margin:0" data-testid="add-notice">
      Your text is kept word for word as a source on this computer, and it is sent to the AI service to get proposals.
      Only the items you confirm are saved.</p></div></div>
      <label for="add-text">Text to add</label>
      <textarea id="add-text" data-testid="add-text-input" aria-label="Text to add" aria-describedby="add-text-help"></textarea>
      <p class="help" id="add-text-help">Paste or type the raw note. Ember proposes items from it; you confirm each one.</p>
      <div class="actions">${buttonHtml({ label: 'Add text', action: 'add-start', variant: 'primary', testid: 'add-start' })}</div>`;
  }

  /* ---------------- the running session ---------------- */

  function proposalHtml() {
    const view = state.view;
    if (view.proposal && view.proposal.fields) {
      const f = view.proposal.fields;
      const type = typeof f.type === 'string' && PROPOSAL_TYPES.includes(f.type) ? f.type : 'Decision';
      return proposalBlockHtml({
        type,
        statement: typeof f.statement === 'string' ? f.statement : '',
        quote: typeof f.source_quote === 'string' ? f.source_quote : '',
        warn: view.proposal.warn,
      });
    }
    if (view.proposal) {
      // Drift (fields null): fail loud, the raw block stays the evidence.
      return `<div class="panel"><div class="pad"><p class="lbl">A proposal Ember could not read as data</p>
        <pre class="source-verbatim">${esc(view.proposal.text)}</pre></div></div>`;
    }
    return '';
  }

  function choiceButtonsHtml() {
    // The pinned ProposalBlock order: Stop (Esc), Edit (e), Reject (n),
    // Confirm (Return); these answer the open choice prompt. proposal
    // blocks WITH parsed fields carry the same four buttons inside the
    // block's own actions row, so this standalone row appears only in
    // the fields:null drift case, where Stop stays reachable.
    const buttons = [
      buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text' }),
      buttonHtml({ label: 'Edit', kbd: 'e', action: 'proposal-edit', variant: 'secondary' }),
      buttonHtml({ label: 'Reject', kbd: 'n', action: 'proposal-reject', variant: 'secondary' }),
      buttonHtml({ label: 'Confirm', kbd: 'Return', action: 'proposal-confirm', variant: 'primary' }),
    ].join('');
    return `<div class="actions" data-testid="add-choice">${buttons}</div>`;
  }

  function editHtml() {
    const view = state.view;
    const step = view.awaiting;
    const values = view.editValues ?? { type: '', statement: '', metadata: '' };
    const msg = view.editMessage
      ? `<p class="hint" role="status" data-testid="add-edit-message">${esc(view.editMessage)}</p>`
      : '';
    let field = '';
    if (step === 'type') {
      const options = PROPOSAL_TYPES.map(
        (t) =>
          `<label style="font-weight:400;margin:var(--s1) 0"><input type="radio" name="add-edit-type" value="${esc(t)}" ${
            values.type === t ? 'checked' : ''
          }> ${esc(t)}</label>`,
      ).join('');
      field = `<fieldset style="border:0;padding:0;margin:0 0 var(--s2)"><legend class="help">New type for this item</legend>${options}
        <p class="help">The type the proposal already has is preselected. Leave it as it is to keep it.</p></fieldset>`;
    } else if (step === 'statement') {
      field = `<label for="add-edit-statement">New statement</label>
        <textarea id="add-edit-statement" data-testid="add-edit-statement">${esc(values.statement)}</textarea>
        <p class="help">Leave it exactly as it is to keep the proposal's statement.</p>`;
    } else {
      field = `<label for="add-edit-metadata">New project label</label>
        <input type="text" id="add-edit-metadata" data-testid="add-edit-metadata" value="${esc(values.metadata)}">
        <p class="help">A short label such as <span class="mono">auth</span>. Leave the box as it is to keep the current one.</p>`;
    }
    const promptWord = step === 'type' ? 'the type' : step === 'statement' ? 'the statement' : 'the project label';
    return `<div class="panel" data-testid="add-edit"><div class="pad">
      <p class="lbl">Editing the proposal: ${esc(promptWord)}</p>
      ${field}${msg}
      <div class="actions"><button type="button" class="btn btn--primary" data-testid="add-edit-submit">Use this answer</button>
      ${buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text' })}</div>
    </div></div>`;
  }

  function unknownPromptHtml() {
    const view = state.view;
    return `<div class="errbox" role="alert" data-testid="add-unknown-prompt"><strong>Ember asked something this app does not know.</strong>
      <span class="detail">${esc(view.unknownPrompt ? view.unknownPrompt.text : '')}</span>
      <div class="actions">
        <label for="add-raw-answer" class="help" style="margin:0">Answer with exactly the text Ember asked for</label>
        <input type="text" id="add-raw-answer" data-testid="add-raw-answer">
        <button type="button" class="btn btn--primary" data-testid="add-raw-submit">Send the answer</button>
        ${buttonHtml({ label: 'Stop', kbd: 'Esc', action: 'proposal-stop', variant: 'text' })}
      </div></div>`;
  }

  function savedHtml() {
    const view = state.view;
    if (view.saved.length === 0) return '';
    const rows = view.saved
      .map((item, index) => {
        // DESIGN.md Motion: in the Saved so far list the new item's
        // mark lights up — only the rows that appeared since the last
        // render animate, so a later re-render never replays it.
        // Reduce Motion turns the animation off in CSS.
        const isNew = index >= renderedSavedCount;
        return `<tr data-testid="saved-row"><td class="num dim">${item.id ?? '—'}</td><td>${esc(item.statement)}</td>
          <td class="nowrap">${statusPillHtml('Active', { settle: isNew ? 'heat--settle-heat' : '' })}</td></tr>`;
      })
      .join('');
    renderedSavedCount = view.saved.length;
    return `<h2>Saved so far</h2><div class="panel"><table class="ember-table" data-testid="add-saved">
      <thead><tr><th class="num">No.</th><th>Item</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function logHtml() {
    const view = state.view;
    if (view.log.length === 0) return '';
    const lines = view.log.map((line) => `<li>${esc(line)}</li>`).join('');
    return `<ul class="help" data-testid="add-log" role="log" aria-label="Messages from Ember while adding" style="margin:var(--s2) 0 0">${lines}</ul>`;
  }

  function sessionHtml() {
    const stage = addStage(state.view);
    const view = state.view;
    let inner = '';
    if (stage === 'loading') {
      inner = loadingHtml({ hint: 'Reading your text and asking the AI service for proposals… Nothing is saved yet.' });
    } else if (stage === 'session') {
      const body =
        view.awaiting === 'unknown'
          ? unknownPromptHtml()
          : view.awaiting && view.awaiting !== 'choice'
            ? editHtml()
            : `${proposalHtml()}${
                view.awaiting === 'choice' && view.proposal && !view.proposal.fields ? choiceButtonsHtml() : ''
              }`;
      inner = `<div aria-live="polite">${logHtml()}${body}</div>${savedHtml()}`;
    }
    return `<div data-testid="add-flow">${inner}</div>${endActionsHtml(stage)}`;
  }

  /* ---------------- the end states ---------------- */

  function endActionsHtml(stage) {
    const view = state.view;
    if (stage === 'summary') {
      const accepted = Number(view.summary?.accepted ?? 0);
      const rejected = Number(view.summary?.rejected ?? 0);
      const counts = `<p class="help" data-testid="add-summary-line" style="margin:0 0 var(--s4)">${accepted} ${
        accepted === 1 ? 'item' : 'items'
      } confirmed, ${rejected} rejected.</p>`;
      return `<h2>Done</h2><div class="panel"><div class="pad">${counts}
        <div class="actions">
          ${accepted > 0 ? buttonHtml({ label: 'Link the new items', action: 'add-to-link', variant: 'primary', testid: 'add-to-link' }) : ''}
          ${buttonHtml({ label: 'Add more text', action: 'add-reset', variant: 'secondary', testid: 'add-reset' })}
        </div></div></div>`;
    }
    if (stage === 'empty') {
      return emptyHtml({
        title: 'Ember found nothing to propose in this text. Your text is kept as a source.',
        next: 'Add other text',
        onNext: 'add-reset-empty',
      });
    }
    if (stage === 'stopped') {
      const accepted = Number(view.summary?.accepted ?? 0);
      const what =
        accepted > 0
          ? `You stopped early. ${accepted} ${accepted === 1 ? 'item was' : 'items were'} saved; nothing is half-written.`
          : 'You stopped early. Nothing was saved; your text is kept as a source.';
      return `<h2>Stopped</h2><div class="panel"><div class="pad"><p class="help" data-testid="add-stopped-line" style="margin:0">${esc(what)}</p>
        <div class="actions">${buttonHtml({ label: 'Add more text', action: 'add-reset', variant: 'primary', testid: 'add-reset' })}</div>
      </div></div>`;
    }
    return '';
  }

  /* ---------------- the error state ---------------- */

  function errorBlockHtml(err) {
    const s = addErrorSentence(err);
    const setupButton = s.openSetup
      ? buttonHtml({ label: 'Set up the AI connection', action: 'add-open-setup', variant: 'secondary', testid: 'add-open-setup' })
      : '';
    return `${errorHtml({ title: s.title, detail: s.what, why: s.next, onRetry: 'add-retry' })}${setupButton}
      <p class="help" data-testid="error-code" hidden>${esc(`${err ? `${err.code} ${err.name} | ${err.detail}` : 'no details'}`)}</p>`;
  }

  function wireErrorBlock(container, err) {
    bindStateBlock(container, {
      'add-retry': () => startSession(),
      'show-details': () => {
        const code = container.querySelector('[data-testid="error-code"]');
        if (code) code.hidden = !code.hidden;
      },
      'add-open-setup': () => ctx.openSetup(),
    });
  }

  /* ---------------- rendering ---------------- */

  function renderFrameShell() {
    ctx.renderFrame(
      `<div data-testid="add-pane">
        <div class="titlerow"><div class="grow"><h1>Add</h1>
          <p class="sub">Paste text. Ember proposes items: a decision, assumption, finding or question. Only the ones you confirm are saved.</p></div></div>
        <div data-testid="add-gate"></div>
        <div data-testid="add-input"></div>
        <div data-testid="add-flow-host"></div>
      </div>`,
      (root) => {
        rootEl = root;
        flowEl = root.querySelector('[data-testid="add-flow-host"]');
        formEl = root.querySelector('[data-testid="add-input"]');
        renderGateAndForm();
        installKeyboard();
      },
    );
  }

  function renderGateAndForm() {
    const gate = rootEl.querySelector('[data-testid="add-gate"]');
    if (state.kbInvalid) {
      const err = {
        code: 'APP-006',
        name: 'KnowledgeBaseMissing',
        where: 'add',
        detail: 'the chosen knowledge base file is not an Ember file',
      };
      state.phase = 'error';
      state.error = err;
      formEl.innerHTML = '';
      gate.innerHTML = '';
      flowEl.innerHTML = `<div data-testid="add-error">${errorBlockHtml(err)}</div>`;
      wireErrorBlock(flowEl, err);
      return;
    }
    if (state.keyMissing) {
      // Story 29: without a key, Add says it needs the connection and
      // takes the user to the setting.
      formEl.innerHTML = '';
      gate.innerHTML = noKeyHtml({ what: 'Adding text', onOpenSettings: 'add-open-setup' });
      gate.querySelector('[data-action="add-open-setup"]')?.addEventListener('click', () => ctx.openSetup());
      return;
    }
    gate.innerHTML = '';
    formEl.innerHTML = formHtml();
    const textarea = formEl.querySelector('[data-testid="add-text-input"]');
    textarea.value = state.text;
    textarea.addEventListener('input', () => {
      state.text = textarea.value;
    });
    formEl.querySelector('[data-action="add-start"]')?.addEventListener('click', () => startSession());
  }

  /** Re-renders only the flow region, so the draft text is never lost. */
  function renderFlow() {
    if (!flowEl) return;
    let editFocused = false;
    if (state.phase === 'session' || state.phase === 'done') {
      flowEl.innerHTML = sessionHtml();
      editFocused = wireSession();
      if (state.phase === 'done') {
        flowEl.querySelector('[data-action="add-to-link"]')?.addEventListener('click', () => ctx.navigate('link'));
        flowEl.querySelector('[data-action="add-reset"]')?.addEventListener('click', () => resetToForm());
        flowEl.querySelector('[data-action="add-reset-empty"]')?.addEventListener('click', () => resetToForm());
      }
    } else if (state.phase === 'error') {
      flowEl.innerHTML = `<div data-testid="add-error">${errorBlockHtml(state.error)}</div>`;
      wireErrorBlock(flowEl, state.error);
    } else {
      flowEl.innerHTML = '';
    }
    // A re-render drops the focus to the page body (story 96: the
    // keyboard never dead-ends). The edit form keeps its own focus.
    if (!editFocused && ctx.paneEl()) ctx.paneEl().focus({ preventScroll: true });
  }

  /** @returns {boolean} true when the edit form focused its own field */
  function wireSession() {
    const root = flowEl;
    bindStateBlock(root, {
      'proposal-confirm': () => answerChoice('y'),
      'proposal-reject': () => answerChoice('n'),
      'proposal-edit': () => answerChoice('e'),
      'proposal-stop': () => stopSession(),
    });
    root.querySelector('[data-testid="add-edit-submit"]')?.addEventListener('click', () => submitEdit());
    root.querySelector('[data-testid="add-raw-submit"]')?.addEventListener('click', () => submitRawAnswer());
    const textarea = root.querySelector('[data-testid="add-edit-statement"]');
    if (textarea) {
      textarea.addEventListener('input', () => {
        state.view.editValues = { ...state.view.editValues, statement: textarea.value };
      });
    }
    const metadata = root.querySelector('[data-testid="add-edit-metadata"]');
    if (metadata) {
      metadata.addEventListener('input', () => {
        state.view.editValues = { ...state.view.editValues, metadata: metadata.value };
      });
      metadata.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          submitEdit();
        }
      });
    }
    root.querySelector('[data-testid="add-raw-answer"]')?.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        submitRawAnswer();
      }
    });
    const step = state.view.awaiting;
    if (step === 'statement') {
      root.querySelector('[data-testid="add-edit-statement"]')?.focus();
      return true;
    }
    if (step === 'metadata') {
      root.querySelector('[data-testid="add-edit-metadata"]')?.focus();
      return true;
    }
    if (step === 'unknown') {
      root.querySelector('[data-testid="add-raw-answer"]')?.focus();
      return true;
    }
    return false;
  }

  /* ---------------- the session itself ---------------- */

  async function startSession() {
    if (typeof state.text !== 'string' || state.text.trim() === '') {
      flowEl.innerHTML = boardMessage('error', 'The text box is empty. Paste or type some text first.');
      formEl?.querySelector('[data-testid="add-text-input"]')?.focus();
      return;
    }
    state.phase = 'session';
    state.view = initialAddView();
    state.error = null;
    state.busy = false;
    renderedSavedCount = 0;
    formEl.innerHTML = '';
    renderFlow();
    // Subscribe FIRST, attach right after startAdd resolves: a child
    // that dies (or refuses) instantly must still reach the screen —
    // the app core buffers every push until ember:addAttach.
    unlisten();
    state.unsub = [
      ctx.api.onAddEvent((ev) => {
        state.busy = false;
        // Any event after a staged confirm proves the write landed.
        state.view = applyAddEvent(state.view, ev);
        renderFlow();
      }),
      ctx.api.onAddExit(({ exitCode, error }) => {
        unlisten();
        if (error) {
          state.phase = 'error';
          state.error = error;
          renderFlow();
          return;
        }
        state.phase = 'done'; // exit 0 or the quiet stop (2); the summary event already told the story
        renderFlow();
      }),
    ];
    const res = await ctx.api.startAdd(state.text);
    if (!res || !res.ok) {
      state.phase = 'error';
      state.error = res ? res.error : null;
      unlisten();
      renderFlow();
      return;
    }
    await ctx.api.attachAdd();
  }

  async function answerChoice(letter) {
    if (state.phase !== 'session' || state.busy || state.view.awaiting !== 'choice') return;
    state.busy = true; // one answer in flight; the next event or the exit clears it
    if (letter === 'y') state.view = recordConfirm(state.view);
    renderFlow();
    const sent = await ctx.api.answerAdd(letter);
    if (!sent || !sent.ok) {
      state.phase = 'error';
      state.error = sent ? sent.error : null;
      state.busy = false;
      renderFlow();
    }
  }

  async function submitEdit() {
    if (state.phase !== 'session' || state.busy) return;
    const step = state.view.awaiting;
    if (!step || step === 'choice' || step === 'unknown') return;
    state.busy = true;
    const values = state.view.editValues ?? {};
    let answer;
    if (step === 'type') {
      const chosen = flowEl.querySelector('input[name="add-edit-type"]:checked');
      const value = chosen ? chosen.value : '';
      // The engine keeps its default on an empty answer: answering ''
      // for the type the proposal already has says "keep it" exactly.
      answer = value === values.type ? '' : value;
    } else if (step === 'statement') {
      answer = values.statement ?? '';
    } else {
      answer = values.metadata ?? '';
    }
    const sent = await ctx.api.answerAdd(answer);
    if (!sent || !sent.ok) {
      state.phase = 'error';
      state.error = sent ? sent.error : null;
      state.busy = false;
      renderFlow();
    }
  }

  async function submitRawAnswer() {
    if (state.phase !== 'session' || state.busy) return;
    const field = flowEl.querySelector('[data-testid="add-raw-answer"]');
    state.busy = true;
    const sent = await ctx.api.answerAdd(field ? field.value : '');
    if (!sent || !sent.ok) {
      state.phase = 'error';
      state.error = sent ? sent.error : null;
      state.busy = false;
      renderFlow();
    }
  }

  async function stopSession() {
    if (state.phase !== 'session') return;
    const stopped = await ctx.api.stopAdd();
    if (!stopped || !stopped.ok) {
      state.phase = 'error';
      state.error = stopped ? stopped.error : null;
      renderFlow();
    }
  }

  function resetToForm() {
    unlisten();
    // The engine already cleaned its own temp file on exit (the app
    // keeps no Ember data of its own; the source stays in the file).
    state.phase = 'form';
    state.view = initialAddView();
    state.error = null;
    state.busy = false;
    state.text = '';
    renderGateAndForm();
    flowEl.innerHTML = '';
  }

  /* ---------------- keyboard (story 23) ---------------- */

  function installKeyboard() {
    const pane = ctx.paneEl();
    if (!pane || keydownHandler) return;
    keydownHandler = (ev) => {
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
      else if (ev.key === 'n') void answerChoice('n');
      else if (ev.key === 'e') void answerChoice('e');
      else if (ev.key === 'q') void stopSession();
    };
    pane.addEventListener('keydown', keydownHandler);
  }

  /* ---------------- the five-state gate ---------------- */

  async function render() {
    renderFrameShell();
    const gate = await ctx.gate();
    if (gate === 'invalid') {
      state.kbInvalid = true;
      renderGateAndForm();
      return;
    }
    const status = await ctx.api.keyStatus();
    state.keyMissing = !(status && (status.stored || status.sessionOnly));
    renderGateAndForm();
  }

  return { render, state };
}

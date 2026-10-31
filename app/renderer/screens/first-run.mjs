/**
 * First run (app step file §1, spec stories 1-9): the setup screen that
 * opens on first launch. Three steps and "about two minutes" (2), the
 * knowledge-base file with a sensible default (3) and one sentence on
 * what the file holds (4), the AI key (5-8: shape check at save per
 * decision 5-A — the real refusal shows at the first Add; skip allowed,
 * 7), and the first action "Add your first text" (9).
 *
 * The step list sits on the left, the step form on the right (DESIGN.md
 * Layout). All reads/writes go through the window.ember preload list.
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { checkKeyShape } from '../../shared/key-shape.mjs';

const STEPS = ['Knowledge base file', 'AI connection', 'Ready'];

export function createFirstRunScreen(ctx) {
  const state = {
    // A knowledge base already chosen (the no-key banner re-opens the
    // setup): start at the key step; a fresh install starts at step 1.
    step: ctx.state.effectiveKbPath ? 2 : 1,
    dbPath: ctx.state.effectiveKbPath || ctx.state.defaultKbPath,
    keySaved: false,
    keySessionOnly: false,
    offerSession: false, // the APP-003 offer, shown until used or replaced
    showKey: false,
    key: '', // the pasted text, kept across re-renders
    message: null, // {kind: 'error'|'ok', text} inside the current step
  };

  const refresh = () => ctx.renderFrame(firstRunHtml(state), wire);

  function showMessage(kind, text) {
    state.message = { kind, text };
    refresh();
  }

  async function wire(root) {
    const dbInput = root.querySelector('[data-testid="setup-db-input"]');
    const keyInput = root.querySelector('[data-testid="setup-key-input"]');

    if (keyInput) {
      keyInput.value = state.key;
      keyInput.addEventListener('input', () => {
        state.key = keyInput.value;
      });
    }
    if (dbInput) {
      dbInput.value = state.dbPath;
      dbInput.addEventListener('input', () => {
        state.dbPath = dbInput.value;
      });
    }

    bind(root, 'setup-browse', async () => {
      const chosen = await ctx.api.pickKnowledgeBaseFile();
      if (chosen && chosen.ok && typeof chosen.path === 'string') {
        state.dbPath = chosen.path;
        state.message = null;
        refresh();
      } else if (chosen && chosen.error) {
        showMessage('error', `${chosen.error.detail} (code ${chosen.error.code})`);
      }
    });

    bind(root, 'setup-file-continue', async () => {
      const path = state.dbPath.trim();
      if (path === '') {
        showMessage('error', 'Choose where the knowledge base file goes. The suggested place is fine for most people.');
        return;
      }
      const saved = await ctx.api.saveSettings({ knowledgeBasePath: path });
      if (!saved.ok) {
        showMessage('error', 'The choice could not be saved. Try again.');
        return;
      }
      state.dbPath = path;
      // The file may simply not exist yet — that is the normal
      // before-the-first-Add state (app step file §1 fact). An existing
      // file must be an Ember knowledge base (APP-006 path).
      const status = await ctx.api.kbStatus();
      if (status.exists && !status.looksValid) {
        showMessage('error', 'That file exists but is not an Ember knowledge base. Choose a different file, or pick a new name.');
        return;
      }
      state.step = 2;
      state.message = null;
      refresh();
    });

    bind(root, 'setup-show-key', () => {
      state.showKey = !state.showKey;
      refresh();
    });

    bind(root, 'setup-save-key', async () => {
      const key = state.key;
      // Stories 5-8, decision 5-A: the shape and length check here;
      // the real test happens at the first Add (step 05 shows the
      // refusal). No AI call happens on this screen.
      const shape = checkKeyShape(key);
      if (!shape.ok) {
        showMessage('error', keyShapeMessage(shape.reason));
        return;
      }
      const saved = await ctx.api.setKey(key);
      if (saved.ok) {
        state.keySaved = true;
        state.keySessionOnly = false;
        state.offerSession = false;
        showMessage(
          'ok',
          'The key is saved on this computer, in the system keyring. The real test happens at your first Add: if the AI service refuses it there, you will see a clear message.',
        );
        return;
      }
      if (saved.error && saved.error.code === 'APP-003') {
        // The keyring is weak or missing: refuse to write the key to
        // disk, offer the session-only path (plan §5.4, APP-003).
        state.keySaved = false;
        state.offerSession = true;
        showMessage('error', `${saved.error.detail} You can keep the key for this session only: it stays in memory and is gone when you close Ember.`);
        return;
      }
      showMessage('error', saved.error ? saved.error.detail : 'The key could not be saved. Try again.');
    });

    bind(root, 'setup-session-key', async () => {
      const key = state.key;
      const kept = await ctx.api.setSessionKey(key);
      if (kept.ok) {
        state.keySaved = true;
        state.keySessionOnly = true;
        state.offerSession = false;
        showMessage('ok', 'The key is kept for this session only.');
      } else {
        showMessage('error', kept.error ? kept.error.detail : 'The key could not be kept even for this session. Try pasting it again.');
      }
    });

    bind(root, 'setup-skip-key', () => {
      state.step = 3;
      state.message = null;
      state.offerSession = false;
      refresh();
    });

    bind(root, 'setup-ready', () => {
      state.step = 3;
      state.message = null;
      refresh();
    });

    bind(root, 'setup-finish', () => {
      ctx.firstRunDone();
      ctx.navigate('add');
    });
  }

  return { state, refresh };
}

function bind(root, action, fn) {
  const el = root.querySelector(`[data-action="${action}"]`);
  if (el) el.addEventListener('click', fn);
}

function keyShapeMessage(reason) {
  if (reason === 'empty') return 'The key box is empty. Paste your key, then save it.';
  if (reason === 'whitespace') return 'A key is one unbroken line of characters. This one has a space or a line break inside; copy it again completely.';
  return 'This key is too short. A real key has at least 20 characters with no spaces; copy it again completely.';
}

function firstRunHtml(state) {
  const n = state.step;
  const pct = Math.round(((n - 1) / 3) * 100);
  const bar = `<div class="progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="Setup progress: step ${n} of 3"><i style="width:${pct}%"></i></div>`;
  const steps = STEPS.map(
    (name, i) =>
      `<li ${i + 1 === n ? 'aria-current="step"' : ''}><span class="n">${i + 1 < n ? 'Done' : i + 1}</span><span>${esc(name)}</span></li>`,
  ).join('');
  let body = '';
  if (n === 1) body = stepFileHtml(state);
  else if (n === 2) body = stepKeyHtml(state);
  else body = stepReadyHtml(state);
  const message =
    state.message && state.message.kind === 'error'
      ? `<div class="errbox" role="alert" data-testid="setup-message"><strong>${esc(state.message.text)}</strong></div>`
      : state.message
        ? `<div class="ok" role="status" data-testid="setup-message">${esc(state.message.text)}</div>`
        : '';
  return `<div class="setup">
    <h1>Set up Ember</h1>
    <p class="sub">Step ${n} of 3. About two minutes.</p>
    ${bar}
    <div class="setup-grid">
      <ol class="steps" aria-label="Setup steps">${steps}</ol>
      <div class="form">${body}${message}</div>
    </div>
  </div>`;
}

/** Stories 3-4: where the file lives, with a default, plus what it holds. */
function stepFileHtml(state) {
  return `<h2 style="margin-top:0">Where should Ember keep your knowledge?</h2>
    <p class="help" style="margin:0 0 var(--s3)">One file holds everything: your items, their links and the ledger. You can back it up later.</p>
    <label for="setup-db">Knowledge base file</label>
    <input type="text" id="setup-db" data-testid="setup-db-input" value="${esc(state.dbPath)}" aria-label="Knowledge base file location" aria-describedby="setup-db-help">
    <p class="help" id="setup-db-help">The file is created the first time you add text. Until then the app knows it does not exist yet.</p>
    <div class="actions">
      ${buttonHtml({ label: 'Choose a different file…', action: 'setup-browse', variant: 'secondary' })}
      ${buttonHtml({ label: 'Continue', action: 'setup-file-continue', variant: 'primary' })}
    </div>`;
}

/** Stories 5-8: paste the key, plain explanation, skip allowed. */
function stepKeyHtml(state) {
  const savedMsg =
    state.keySaved && !state.message
      ? `<div class="ok" role="status">The key is saved${
          state.keySessionOnly ? ' for this session only' : ' on this computer'
        }.</div>`
      : '';
  const sessionButton = state.offerSession
    ? buttonHtml({ label: 'Use for this session only', action: 'setup-session-key', variant: 'secondary', testid: 'setup-session-key' })
    : '';
  const continueButton = state.keySaved
    ? buttonHtml({ label: 'Continue', action: 'setup-ready', variant: 'primary', testid: 'setup-continue' })
    : '';
  return `<h2 style="margin-top:0">Connect an AI service</h2>
    <p class="help" style="margin:0 0 var(--s3)">Ember asks an AI service you choose to propose items and links. It only proposes; you confirm. When you use Add or Link items, your text is sent to that service. Nothing else about your work leaves this computer.</p>
    <label for="setup-key">Your AI key</label>
    <input type="${state.showKey ? 'text' : 'password'}" id="setup-key" data-testid="setup-key-input" autocomplete="off" aria-label="Your AI key" aria-describedby="setup-key-help" value="${esc(state.key)}">
    <p class="help" id="setup-key-help">A key is a long password that lets Ember use the AI service. Ember stores it on this computer only — in the operating system keyring, never in a plain file.</p>
    <div class="actions">
      ${buttonHtml({ label: state.showKey ? 'Hide' : 'Show', action: 'setup-show-key', variant: 'secondary' })}
      ${state.keySaved ? continueButton : buttonHtml({ label: 'Save the key', action: 'setup-save-key', variant: 'primary' })}
      ${sessionButton}
      ${buttonHtml({ label: 'Skip for now', action: 'setup-skip-key', variant: 'text' })}
    </div>
    <p class="help">Ember checks the key's shape now. The real test happens at your first Add: if the service refuses the key, you will see a clear message there.</p>
    <p class="help">If you skip, you can still look things up, fix items, clean up and back up. Add and Link items wait for a key.</p>
    ${savedMsg}`;
}

/** Story 9: the first action is Add your first text. */
function stepReadyHtml(state) {
  return `<h2 style="margin-top:0">Ember is ready</h2>
    <p class="help" style="margin:0 0 var(--s3)">Knowledge base file: ${esc(state.dbPath)}. AI connection: ${
      state.keySaved ? (state.keySessionOnly ? 'kept for this session' : 'connected') : 'not connected yet'
    }.</p>
    <div class="actions">
      ${buttonHtml({ label: 'Add your first text', action: 'setup-finish', variant: 'primary', testid: 'setup-finish' })}
    </div>`;
}

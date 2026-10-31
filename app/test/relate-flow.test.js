'use strict';

/**
 * Unit tests for the Link items pieces (app step 06):
 *
 * - shared/relate-view.mjs — the PURE session view fold, driven with
 *   the SAME event shapes tests/bridge/test_json_confirm.py pins
 *   (link-preview before the prompt, the link block after the write,
 *   message events for `relate rejected: ...`, the summary event with
 *   accepted/rejected/skipped/aborted);
 * - shared/relate-words.mjs — the plain words (no bare code on screen);
 * - main/relate-args.js + main/relate-session.js — the argv builder
 *   and the ipc channel composition against a fake session factory
 *   and a fake ipc (no Electron; the App 05 harness pattern).
 */

const test = require('node:test');
const assert = require('node:assert/strict');

/** The .mjs pure modules, loaded once (node's module cache does the rest). */
const loadView = () => import('../shared/relate-view.mjs');
const loadWords = () => import('../shared/relate-words.mjs');
const { wireRelateChannels } = require('../main/relate-session');
const { relateArgs } = require('../main/relate-args');

/* ---------- the pinned event shapes (contract, relate) ---------- */

const PREVIEW_TEXT = 'Proposal 1/3: item 1 -> item 4 [depends_on]\n  rationale: copy before every upgrade';
const PREVIEW_EVENT = {
  event: 'block',
  kind: 'link-preview',
  fields: { index: 1, total: 3, source_item_id: 1, target_item_id: 4, link_type: 'depends_on', rationale: 'copy before every upgrade' },
  text: PREVIEW_TEXT,
};
const PROMPT_EVENT = { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [s]kip / [q]uit', choices: ['y', 'n', 's', 'q'] };
const LINK_TEXT = [
  '- link_id: 3',
  '  source_item_id: 1',
  '  target_item_id: 4',
  '  link_type: "depends_on"',
  '  status: "Confirmed"',
  '  rationale: null',
].join('\n');
const LINK_EVENT = {
  event: 'block',
  kind: 'link',
  fields: { link_id: 3, source_item_id: 1, target_item_id: 4, link_type: 'depends_on', status: 'Confirmed', rationale: null },
  text: LINK_TEXT,
};
const REJECTION_EVENT = { event: 'message', text: 'relate rejected: RELATE-009 | duplicate of link 1' };
const SUMMARY_EVENT = { event: 'summary', accepted: 1, rejected: 1, skipped: 1, aborted: false };

/* ---------- relate-view (the pure fold) ---------- */

test('a link-preview block opens the proposal and the choice prompt waits', async () => {
  const { initialRelateView, applyRelateEvent } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, PREVIEW_EVENT);
  assert.equal(view.proposal.fields.link_type, 'depends_on');
  assert.equal(view.awaiting, null);
  view = applyRelateEvent(view, PROMPT_EVENT);
  assert.equal(view.awaiting, 'choice');
});

test('recordConfirm stages the confirm; only the link block fills the list (nothing half-proven)', async () => {
  const { initialRelateView, applyRelateEvent, recordConfirm } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, PREVIEW_EVENT);
  view = applyRelateEvent(view, PROMPT_EVENT);
  view = recordConfirm(view);
  assert.equal(view.confirming, true);
  assert.equal(view.proposal, null); // hidden while the answer is in flight
  assert.equal(view.links.length, 0);
  view = applyRelateEvent(view, LINK_EVENT);
  assert.equal(view.confirming, false);
  assert.equal(view.links.length, 1);
  assert.equal(view.links[0].linkId, 3);
  assert.equal(view.links[0].status, 'Confirmed');
});

test('a confirm whose child dies before the block leaves NO link row', async () => {
  const { initialRelateView, applyRelateEvent, recordConfirm } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, PREVIEW_EVENT);
  view = applyRelateEvent(view, PROMPT_EVENT);
  view = recordConfirm(view);
  view = applyRelateEvent(view, { event: 'message', text: 'exiting' }); // a later event is not the proof
  assert.equal(view.links.length, 0);
});

test('skip or reject fills no accepted-link row; the run just moves on', async () => {
  const { initialRelateView, applyRelateEvent } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, PREVIEW_EVENT);
  view = applyRelateEvent(view, PROMPT_EVENT);
  // The screen answers 's'; the engine's next event is the NEXT preview.
  view = applyRelateEvent(view, PREVIEW_EVENT);
  assert.equal(view.links.length, 0);
  assert.equal(view.awaiting, null);
});

test('gatekeeper rejections ride message events into the log, in order', async () => {
  const { initialRelateView, applyRelateEvent } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, REJECTION_EVENT);
  view = applyRelateEvent(view, { event: 'message', text: 'reading' });
  assert.deepEqual(view.log, [REJECTION_EVENT.text, 'reading']);
});

test('the summary event lands with the engine counts; aborted says stopped', async () => {
  const { initialRelateView, applyRelateEvent } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, PREVIEW_EVENT);
  view = applyRelateEvent(view, SUMMARY_EVENT);
  assert.deepEqual(view.summary, { accepted: 1, rejected: 1, skipped: 1, aborted: false });
  const aborted = applyRelateEvent(view, { event: 'summary', accepted: 0, rejected: 0, skipped: 0, aborted: true });
  assert.equal(aborted.summary.aborted, true);
});

test('the two documented empty-pool prints set the empty signal, with the raw line kept', async () => {
  const { initialRelateView, applyRelateEvent, relateEmptySignal } = await loadView();
  assert.equal(relateEmptySignal('no unrelated items'), true);
  assert.equal(relateEmptySignal('{"phase": 2, "pool_size": 0, "signals": {}}'), true);
  assert.equal(relateEmptySignal('{"phase": 3, "pool_size": 0}'), false);
  assert.equal(relateEmptySignal('reading'), false);
  assert.equal(relateEmptySignal(null), false);
  let view = initialRelateView();
  view = applyRelateEvent(view, { event: 'message', text: 'no unrelated items' });
  assert.equal(view.emptySignal, true);
  assert.equal(view.emptyText, 'no unrelated items');
});

test('an unparseable proposal block fails loud in the log, never silently', async () => {
  const { initialRelateView, applyRelateEvent } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, { event: 'block', kind: 'item', fields: null, text: '- id: 1' });
  assert.ok(view.log.length > 0 && view.log[0].includes('"item"'));
  assert.equal(view.proposal, null);
});

test('a non-choice prompt is drift: the unknown state keeps the raw text', async () => {
  const { initialRelateView, applyRelateEvent } = await loadView();
  let view = initialRelateView();
  view = applyRelateEvent(view, { event: 'prompt', kind: 'type', text: 'New type?', choices: [] });
  assert.equal(view.awaiting, 'unknown');
  assert.equal(view.unknownPrompt.text, 'New type?');
});

test('relateSummarySentence reads the engine numbers, never recomputed', async () => {
  const { relateSummarySentence } = await loadView();
  assert.equal(relateSummarySentence({ accepted: 1, rejected: 0, skipped: 2 }), 'Done. 1 link confirmed, 2 skipped, 0 rejected.');
  assert.equal(relateSummarySentence({ accepted: 2, rejected: 1, skipped: 0 }), 'Done. 2 links confirmed, 0 skipped, 1 rejected.');
  assert.equal(relateSummarySentence(null), 'The run ended.');
});

test('pickRowFor reads statements only back from the list-items document (D3)', async () => {
  const { pickRowFor } = await loadView();
  const list = [{ id: 1, type: 'Decision', statement: 'Use SQLite.' }];
  assert.deepEqual(pickRowFor(list, 1), { id: 1, type: 'Decision', statement: 'Use SQLite.' });
  assert.deepEqual(pickRowFor(list, 9), { id: 9, type: null, statement: null });
  assert.deepEqual(pickRowFor(null, 1), { id: 1, type: null, statement: null });
});

/* ---------- relate-words ---------- */

test('the missing-package refusal tells what to install, no bare code', async () => {
  const { relateErrorSentence } = await loadWords();
  const words = relateErrorSentence({ code: 'RELATE-017', name: 'EmbedderLoadFailed', where: 'x', detail: 'sentence_transformers is not installed' });
  assert.match(words.title, /not installed/);
  assert.match(words.next, /pip install -e "\.\[relate\]"/);
  assert.equal(words.openSetup, false);
  assert.equal(words.retry, false);
});

test('the missing key at the first relate opens the setup (the story-48 twin)', async () => {
  const { relateErrorSentence } = await loadWords();
  const words = relateErrorSentence({ code: 'RELATE-035', name: 'ConfigMissing', where: 'x', detail: 'ai api key missing' });
  assert.match(words.title, /AI connection/);
  assert.equal(words.openSetup, true);
  assert.equal(words.retry, true);
});

test('every error branch keeps "nothing changed" and never a bare code', async () => {
  const { relateErrorSentence } = await loadWords();
  for (const err of [
    { code: 'RELATE-012', name: 'DbOpenFailed', where: 'x', detail: 'db missing' },
    { code: 'RELATE-032', name: 'AiCallFailed', where: 'x', detail: 'unreachable' },
    null,
  ]) {
    const s = relateErrorSentence(err);
    assert.ok(s.title.length > 0 && s.what.length > 0 && s.next.length > 0);
    assert.ok(!/[A-Z]+-\d{3}/.test(`${s.title} ${s.what} ${s.next}`));
    assert.match(s.what, /untouched|No link was added|nothing was changed/i);
  }
});

test('a relate rejected line becomes plain words with the engine detail', async () => {
  const { relateRejectionLine } = await loadWords();
  const withDetail = relateRejectionLine('relate rejected: RELATE-009 | duplicate of link 1');
  assert.match(withDetail, /rules rejected/);
  assert.match(withDetail, /duplicate of link 1/);
  assert.ok(!/RELATE-009/.test(withDetail));
  const bare = relateRejectionLine('relate rejected: RELATE-009');
  assert.match(bare, /rules rejected/);
  assert.ok(!/RELATE-009/.test(bare));
  // Any other message line is shown as written.
  assert.equal(relateRejectionLine('reading items'), 'reading items');
});

/* ---------- relate-session wiring (fake ipc, fake session) ---------- */

function fakeSession() {
  return {
    answers: [],
    stopped: false,
    handlers: { event: [], error: [], exit: [] },
    on(channel, cb) {
      this.handlers[channel].push(cb);
      return this;
    },
    emit(channel, payload) {
      for (const cb of this.handlers[channel]) cb(payload);
    },
    answer(text) {
      this.answers.push(text);
    },
    stop() {
      this.stopped = true;
    },
  };
}

function fakeIpc() {
  return { handlers: {}, handle(name, fn) { this.handlers[name] = fn; } };
}

function fakeSender() {
  return { sent: [], destroyed: false, send(channel, data) { this.sent.push({ channel, data }); }, isDestroyed() { return this.destroyed; } };
}

function harness({ validate = () => ({ ok: true }) } = {}) {
  const ipc = fakeIpc();
  const sessions = [];
  const started = [];
  wireRelateChannels(ipc, {
    startSession: () => {
      const session = fakeSession();
      sessions.push(session);
      return session;
    },
    validateRelateTarget: validate,
    onCommand: (name, args) => started.push({ name, args }),
  });
  return { ipc, sessions, started, attach: () => ipc.handlers['ember:relateAttach']({ sender: null }) };
}

test('relateStart builds the argv through relate-args and starts the session', () => {
  const h = harness();
  const res = h.ipc.handlers['ember:relateStart']({ sender: fakeSender() }, { item: 2 });
  assert.deepEqual(res, { ok: true });
  assert.deepEqual(h.started, [{ name: 'relate', args: relateArgs({ item: 2 }) }]);
});

test('a bad item id never reaches a child (APP-002 at the edge)', () => {
  const h = harness();
  const res = h.ipc.handlers['ember:relateStart']({ sender: fakeSender() }, { item: 0 });
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'APP-002');
  assert.deepEqual(h.started, []);
});

test('a broken knowledge base refuses before any child (APP-006)', () => {
  const h = harness({ validate: () => ({ ok: false, error: { code: 'APP-006', name: 'KnowledgeBaseMissing', where: 'x', detail: 'no' } }) });
  const res = h.ipc.handlers['ember:relateStart']({ sender: fakeSender() }, { latest: true });
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'APP-006');
  assert.deepEqual(h.started, []);
});

test('events and the exit reach the sender after attach; a dying child loses nothing', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:relateStart']({ sender }, { item: 1 });
  const session = h.sessions[0];
  session.emit('event', PREVIEW_EVENT); // BEFORE attach: buffered
  assert.deepEqual(sender.sent, []); // nothing lost, nothing delivered yet
  h.attach();
  assert.deepEqual(sender.sent.map((s) => s.channel), ['ember:relateEvent']);
  assert.deepEqual(sender.sent[0].data, PREVIEW_EVENT);
  session.emit('exit', { exitCode: 0 });
  const exit = sender.sent.find((s) => s.channel === 'ember:relateExit');
  assert.deepEqual(exit.data, { exitCode: 0, error: null });
});

test('an answer must be text (the BRIDGE-001 pin), one session at a time', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:relateStart']({ sender }, { item: 1 });
  const res = h.ipc.handlers['ember:relateAnswer']({}, 42);
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'APP-002');
  h.ipc.handlers['ember:relateAnswer']({}, 'y');
  assert.deepEqual(h.sessions[0].answers, ['y']);
  const second = h.ipc.handlers['ember:relateStart']({ sender: fakeSender() }, { item: 1 });
  assert.equal(second.ok, false);
});

test('stop closes stdin and a second run works after the exit', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:relateStart']({ sender }, { item: 1 });
  h.ipc.handlers['ember:relateStop']({}, null);
  assert.equal(h.sessions[0].stopped, true);
  h.sessions[0].emit('exit', { exitCode: 2 });
  const again = h.ipc.handlers['ember:relateStart']({ sender: fakeSender() }, { item: 1 });
  assert.deepEqual(again, { ok: true });
  assert.equal(h.sessions.length, 2);
});

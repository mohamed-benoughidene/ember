'use strict';

/**
 * Unit tests for the Add flow's pure parts (app step 05): the
 * confirm-session view reducer (shared/confirm-view.mjs) driven with
 * the SAME event streams the Python contract suite pins
 * (tests/bridge/test_confirm_json_cli.py), and the Add error words
 * (shared/capture-words.mjs).
 */

const test = require('node:test');
const assert = require('node:assert/strict');

/** The .mjs pure modules, loaded once (node's module cache does the rest). */
const loadView = () => import('../shared/confirm-view.mjs');
const loadWords = () => import('../shared/capture-words.mjs');

/* ---------- helpers: the pinned contract streams ---------- */

const BLOCK_ITEM_1 = {
  event: 'block',
  kind: 'item',
  fields: {
    id: 1,
    type: 'Decision',
    statement: 'Use SQLite',
    source_quote: 'use SQLite',
    confidence: 0.9,
    metadata: 'auth-network',
    near_dup_warning: null,
  },
  text: '- id: 1\n  type: "Decision"\n  statement: "Use SQLite"\n  source_quote: "use SQLite"\n  confidence: 0.9\n  metadata: "auth-network"\n  near_dup_warning: null',
};

const BLOCK_ITEM_2 = {
  event: 'block',
  kind: 'item',
  fields: {
    id: 2,
    type: 'Assumption',
    statement: 'Team ships weekly',
    source_quote: 'ships weekly',
    confidence: 0.8,
    metadata: null,
    near_dup_warning: null,
  },
  text: '- id: 2\n  type: "Assumption"\n  statement: "Team ships weekly"\n  source_quote: "ships weekly"\n  confidence: 0.8\n  metadata: null\n  near_dup_warning: null',
};

const PROMPT_CHOICE = { event: 'prompt', kind: 'choice', text: '[y]es / [n]o / [e]dit / [q]uit', choices: ['y', 'n', 'e', 'q'] };
const PROMPT_TYPE = { event: 'prompt', kind: 'type', text: 'new type? (default Decision)', choices: [] };
const PROMPT_STATEMENT = { event: 'prompt', kind: 'statement', text: 'new statement? (default Use SQLite)', choices: [] };
const PROMPT_METADATA = { event: 'prompt', kind: 'metadata', text: 'new metadata? (default auth-network)', choices: [] };
const SUMMARY_Y_N = { event: 'summary', accepted: 1, rejected: 1, warnings: 0, aborted: false };

const view = async (...events) => {
  const { initialAddView, applyAddEvent } = await loadView();
  return events.reduce(applyAddEvent, initialAddView());
};

/* ---------- the reducer over the pinned streams ---------- */

test('the accept-then-reject stream lands on a summary of confirmed/rejected', async () => {
  const { addStage } = await loadView();
  const v = await view(
    { event: 'message', text: 'dropped proposal: type' },
    BLOCK_ITEM_1,
    PROMPT_CHOICE,
    BLOCK_ITEM_2,
    PROMPT_CHOICE,
    SUMMARY_Y_N,
  );
  assert.equal(addStage(v), 'summary');
  assert.deepEqual(v.log, ['dropped proposal: type']);
  assert.equal(v.proposal.fields.id, 2);
  assert.deepEqual(v.summary, SUMMARY_Y_N);
});

test('a choice prompt waits for the choice; the next block clears it', async () => {
  const { applyAddEvent } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE);
  assert.equal(v.awaiting, 'choice');
  const afterBlock = applyAddEvent(v, BLOCK_ITEM_2);
  assert.equal(afterBlock.awaiting, null);
  assert.equal(afterBlock.proposal.fields.id, 2);
});

test('the edit sub-prompts open the form step by step with the proposal values', async () => {
  const { applyAddEvent } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE, PROMPT_TYPE);
  assert.equal(v.awaiting, 'type');
  assert.equal(v.editValues.type, 'Decision'); // prefilled from the block
  const step2 = applyAddEvent(v, PROMPT_STATEMENT);
  assert.equal(step2.awaiting, 'statement');
  assert.equal(step2.editValues.statement, 'Use SQLite');
  assert.equal(step2.editValues.type, 'Decision'); // the draft is kept
  const step3 = applyAddEvent(step2, PROMPT_METADATA);
  assert.equal(step3.awaiting, 'metadata');
  assert.equal(step3.editValues.metadata, 'auth-network');
});

test('the engine re-ask line becomes the edit message and keeps the draft', async () => {
  const { applyAddEvent } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE, PROMPT_TYPE);
  const afterMessage = applyAddEvent(v, { event: 'message', text: 'invalid type' });
  assert.equal(afterMessage.awaiting, 'type'); // the same sub-prompt is re-asked
  assert.equal(afterMessage.editMessage, 'invalid type');
  assert.equal(afterMessage.editValues.type, 'Decision');
});

test('a revalidated edit arrives as a new block with the new id', async () => {
  const { applyAddEvent } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE, PROMPT_TYPE, PROMPT_STATEMENT, PROMPT_METADATA);
  const newBlock = {
    event: 'block',
    kind: 'item',
    fields: { ...BLOCK_ITEM_1.fields, id: 3, statement: 'Use SQLite for sure' },
    text: '- id: 3 ...',
  };
  const v2 = applyAddEvent(v, newBlock);
  assert.equal(v2.awaiting, null);
  assert.equal(v2.proposal.fields.id, 3);
  assert.equal(v2.editValues, null);
});

test('a confirm is staged until the engine proves the write (the Saved so far list)', async () => {
  const { applyAddEvent, recordConfirm } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE);
  const confirmed = recordConfirm(v);
  assert.deepEqual(confirmed.saved, []); // not yet proven
  assert.equal(confirmed.pendingConfirm.id, 1);
  const afterNextBlock = applyAddEvent(confirmed, BLOCK_ITEM_2);
  assert.deepEqual(afterNextBlock.saved, [{ id: 1, type: 'Decision', statement: 'Use SQLite' }]);
  assert.equal(afterNextBlock.pendingConfirm, null);
});

test('a staged confirm also lands on the summary (single-proposal add)', async () => {
  const { applyAddEvent, recordConfirm } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE);
  const confirmed = recordConfirm(v);
  const done = applyAddEvent(confirmed, { event: 'summary', accepted: 1, rejected: 0, warnings: 0, aborted: false });
  assert.deepEqual(
    done.saved.map((s) => s.id),
    [1],
  );
});

test('an abort summary lands on the stopped stage', async () => {
  const { addStage } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE, { event: 'summary', accepted: 0, rejected: 0, warnings: 0, aborted: true });
  assert.equal(addStage(v), 'stopped');
});

test('zero confirmed and zero rejected at a normal end is the empty stage', async () => {
  const { addStage } = await loadView();
  const v = await view(
    { event: 'message', text: '0 valid proposals' },
    { event: 'summary', accepted: 0, rejected: 0, warnings: 0, aborted: false },
  );
  assert.equal(addStage(v), 'empty');
  assert.deepEqual(v.log, ['0 valid proposals']);
});

test('the stop with one confirmed item stays stopped, with the saved list', async () => {
  const { addStage, applyAddEvent, recordConfirm } = await loadView();
  const v = await view(BLOCK_ITEM_1, PROMPT_CHOICE);
  const confirmed = recordConfirm(v);
  const v2 = applyAddEvent(confirmed, BLOCK_ITEM_2);
  const v3 = applyAddEvent(v2, PROMPT_CHOICE);
  const v4 = applyAddEvent(v3, { event: 'summary', accepted: 1, rejected: 0, warnings: 0, aborted: true });
  assert.equal(addStage(v4), 'stopped');
  assert.deepEqual(
    v4.saved.map((s) => s.id),
    [1],
  );
});

test('an unknown prompt kind stays fail-loud with its raw text', async () => {
  const v = await view({ event: 'prompt', kind: 'something-new', text: 'ice cream? [p]ick / [q]uit', choices: ['p', 'q'] });
  assert.equal(v.awaiting, 'unknown');
  assert.equal(v.unknownPrompt.text, 'ice cream? [p]ick / [q]uit');
});

test('a non-item block is drift: it lands in the log, the view keeps going', async () => {
  const v = await view({ event: 'block', kind: 'link', fields: null, text: 'x' });
  assert.equal(v.proposal, null);
  assert.equal(v.log.length, 1);
  assert.match(v.log[0], /link/);
});

test('the near-duplicate warning becomes one plain sentence (story 19)', async () => {
  const { proposalWarnText } = await loadView();
  const text = proposalWarnText({ near_dup_warning: { matching_item_id: 3, similarity: 0.91 } });
  assert.match(text, /item 3/);
  assert.match(text, /91%/);
  assert.equal(proposalWarnText({ near_dup_warning: null }), null);
  assert.equal(proposalWarnText(null), null);
});

test('the reducer never mutates the view it was given', async () => {
  const { initialAddView, applyAddEvent, recordConfirm } = await loadView();
  const before = initialAddView();
  const frozen = JSON.parse(JSON.stringify(before));
  applyAddEvent(before, BLOCK_ITEM_1);
  applyAddEvent(before, PROMPT_CHOICE);
  recordConfirm(before);
  assert.deepEqual(before, frozen);
});

/* ---------- the Add error words ---------- */

test('CAPTURE-008 without a key: the plain refusal names the connection and the facts', async () => {
  const { addErrorSentence } = await loadWords();
  const s = addErrorSentence({ code: 'CAPTURE-008', name: 'AiCallFail', where: 'x', detail: 'ai api key missing' });
  assert.match(s.title, /connection/i);
  assert.match(s.what, /kept word for word/);
  assert.match(s.what, /nothing was created/);
  assert.equal(s.openSetup, true); // story 29: the path to the setting
  assert.equal(s.retry, true);
});

test('CAPTURE-008 from an unreachable or refusing service: retry with the same facts', async () => {
  const { addErrorSentence } = await loadWords();
  const s = addErrorSentence({
    code: 'CAPTURE-008',
    name: 'AiCallFail',
    where: 'x',
    detail: 'ai call fail reason=APIConnectionError status=? detail=connection refused',
  });
  assert.match(s.title, /could not answer/i);
  assert.match(s.what, /refused the key/); // decision 5-A's plain refusal wording
  assert.match(s.what, /kept word for word/);
  assert.equal(s.retry, true);
  assert.equal(s.openSetup, true);
});

test('every other code rides the shared plain-sentence table (family fallback)', async () => {
  const { addErrorSentence } = await loadWords();
  // CAPTURE-002 has the table's generic family sentence, never a blank,
  // and the App keeps its own "nothing changed" honesty line.
  const s = addErrorSentence({ code: 'CAPTURE-002', name: 'FileTooLarge', where: 'x', detail: 'too large' });
  assert.equal(s.title, 'A problem in the capture engine (adding text) was reported.');
  assert.match(s.what, /Nothing of yours was changed\./);
  assert.equal(s.retry, true);
  assert.equal(s.openSetup, false);
  const unknown = addErrorSentence({ code: 'CAPTURE-016', name: 'NotAnAssumption', where: 'x', detail: 'nope' });
  assert.match(unknown.title, /capture engine/); // the family sentence, never blank
});

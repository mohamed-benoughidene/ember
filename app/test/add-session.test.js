'use strict';

/**
 * Unit tests for the Add session wiring (app step 05): the ipc
 * channel composition in main/add-session.js and the pasted-text temp
 * file in main/capture-temp.js, against a fake session factory and a
 * fake ipc (no Electron).
 *
 * The BRIDGE-001 pin lives here: the app can only ever write
 * exactly `{"answer": "<text>"}` stdin lines, because answer(text)
 * refuses anything that is not a string at this edge — the engine's
 * re-ask-once rule can never be triggered by a client bug.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { wireAddChannels } = require('../main/add-session');
const { TEMP_PREFIX, tempName, writeTempText, removeTempFile, cleanStaleTempFiles } = require('../main/capture-temp');

/* ---------- fakes ---------- */

function fakeSession() {
  return {
    events: [],
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

/** Wire the channels with a fake session factory + real temp-dir fakes. */
function harness({ validate = () => ({ ok: true }), writeTemp = null } = {}) {
  const ipc = fakeIpc();
  const sessions = [];
  const started = [];
  let tempCalls = [];
  const wiring = wireAddChannels(ipc, {
    startSession: (args) => {
      const session = fakeSession();
      sessions.push(session);
      return session;
    },
    validateAddTarget: validate,
    writeTempText:
      writeTemp ??
      ((text) => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-addsess-'));
        const filePath = path.join(dir, 't.txt');
        fs.writeFileSync(filePath, text, 'utf8');
        tempCalls.push(filePath);
        return { ok: true, path: filePath };
      }),
    removeTempFile: (p) => {
      if (p === null) return;
      tempCalls = tempCalls.filter((x) => x !== p);
      try {
        fs.unlinkSync(p);
      } catch {
        /* gone */
      }
    },
    cleanStaleTempFiles: () => 0,
    onCommand: (name, args) => started.push({ name, args }),
  });
  return { ipc, sessions, started, wiring, remainingTemps: () => [...tempCalls], attach: () => ipc.handlers['ember:addAttach']({ sender: null }) };
}

/* ---------- ember:addStart ---------- */

test('start writes the text to the temp file and starts capture with --file', () => {
  const h = harness();
  const sender = fakeSender();
  const res = h.ipc.handlers['ember:addStart']({ sender }, { text: 'We decided to use SQLite.\n' });
  assert.deepEqual(res, { ok: true });
  assert.deepEqual(h.started, [{ name: 'capture', args: ['--file', h.remainingTemps()[0]] }]);
  assert.equal(fs.existsSync(h.remainingTemps()[0]), true);
  assert.equal(fs.readFileSync(h.remainingTemps()[0], 'utf8'), 'We decided to use SQLite.\n');
});

test('a not-yet-existing knowledge base is fine; a broken one refuses (APP-006)', () => {
  const hBroken = harness({ validate: () => ({ ok: false, error: { code: 'APP-006', name: 'KnowledgeBaseMissing', where: 'x', detail: 'nope' } }) });
  const res = hBroken.ipc.handlers['ember:addStart']({ sender: fakeSender() }, { text: 'hello' });
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'APP-006');
  assert.deepEqual(hBroken.started, []);
});

test('an empty or non-string text refuses, and so does a second session while one runs', () => {
  const h = harness();
  const empty = h.ipc.handlers['ember:addStart']({ sender: fakeSender() }, { text: '   ' });
  assert.equal(empty.ok, false);
  const none = h.ipc.handlers['ember:addStart']({ sender: fakeSender() }, null);
  assert.equal(none.ok, false);
  h.ipc.handlers['ember:addStart']({ sender: fakeSender() }, { text: 'first' });
  const second = h.ipc.handlers['ember:addStart']({ sender: fakeSender() }, { text: 'second' });
  assert.equal(second.ok, false);
  assert.equal(h.sessions.length, 1);
});

test('session events ride the push channel to the invoking sender, in order', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:addStart']({ sender }, { text: 'text' });
  const [session] = h.sessions;
  session.emit('event', { event: 'block', kind: 'item', fields: {}, text: 'raw' });
  session.emit('event', { event: 'prompt', kind: 'choice', text: 'p', choices: ['y'] });
  // Nothing is lost before the attach: everything buffers, in order.
  assert.equal(sender.sent.length, 0, 'pushes stay buffered until the renderer attaches');
  h.attach();
  const eventMessages = sender.sent.filter((m) => m.channel === 'ember:addEvent');
  assert.deepEqual(
    eventMessages.map((m) => m.data.event),
    ['block', 'prompt'],
  );
});

test('a child that died BEFORE the renderer attached cannot lose its exit', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:addStart']({ sender }, { text: 'text' });
  const [session] = h.sessions;
  session.emit('exit', { exitCode: 1 }); // gone before anyone subscribed
  h.attach();
  const exit = sender.sent.find((m) => m.channel === 'ember:addExit');
  assert.ok(exit, 'the buffered exit message must flush on attach');
  assert.equal(exit.data.error.code, 'APP-002');
});

test('the exit cleans the temp file and carries the parsed engine error', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:addStart']({ sender }, { text: 'text' });
  const [session] = h.sessions;
  const failure = { code: 'CAPTURE-008', name: 'AiCallFail', where: 'x', detail: 'ai call fail' };
  session.emit('error', failure);
  session.emit('exit', { exitCode: 1 });
  h.attach();
  assert.equal(h.remainingTemps().length, 0, 'the temp file is removed after every exit');
  const exit = sender.sent.find((m) => m.channel === 'ember:addExit');
  assert.deepEqual(exit.data, { exitCode: 1, error: failure });
});

test('an exit WITHOUT a summary is an early end: APP-002, nothing half-written', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:addStart']({ sender }, { text: 'text' });
  const [session] = h.sessions;
  session.emit('event', { event: 'block', kind: 'item', fields: {}, text: 'raw' });
  session.emit('event', { event: 'prompt', kind: 'choice', text: 'p', choices: ['y'] });
  session.emit('exit', { exitCode: 0 }); // a crash that looks clean
  h.attach();
  const exit = sender.sent.find((m) => m.channel === 'ember:addExit');
  assert.equal(exit.data.error.code, 'APP-002');
  assert.match(exit.data.error.detail, /ended early/);
  assert.match(exit.data.error.detail, /nothing was half-written/);
});

test('a summary seen means a clean exit carries NO error (the stop case, exit 2)', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:addStart']({ sender }, { text: 'text' });
  const [session] = h.sessions;
  session.emit('event', { event: 'summary', accepted: 1, rejected: 0, aborted: true });
  session.emit('exit', { exitCode: 2 });
  h.attach();
  const exit = sender.sent.find((m) => m.channel === 'ember:addExit');
  assert.deepEqual(exit.data, { exitCode: 2, error: null });
});

/* ---------- ember:addAnswer — the BRIDGE-001 pin ---------- */

test('answers reach the session as strings; a non-string is refused at the edge', () => {
  const h = harness();
  const sender = fakeSender();
  h.ipc.handlers['ember:addStart']({ sender }, { text: 'text' });
  const [session] = h.sessions;
  const ok = h.ipc.handlers['ember:addAnswer']({}, 'y');
  assert.deepEqual(ok, { ok: true });
  assert.deepEqual(session.answers, ['y']);
  for (const bad of [5, null, { answer: 'y' }, ['y']]) {
    const res = h.ipc.handlers['ember:addAnswer']({}, bad);
    assert.equal(res.ok, false, `a ${typeof bad} answer must be refused`);
    assert.equal(res.error.code, 'APP-002');
  }
  assert.deepEqual(session.answers, ['y'], 'nothing but the valid string ever reached the child');
});

/* ---------- ember:addStop ---------- */

test('stop closes the session stdin and is refused when nothing runs', () => {
  const h = harness();
  const refused = h.ipc.handlers['ember:addStop']();
  assert.equal(refused.ok, false);
  h.ipc.handlers['ember:addStart']({ sender: fakeSender() }, { text: 'text' });
  const ok = h.ipc.handlers['ember:addStop']();
  assert.deepEqual(ok, { ok: true });
  assert.equal(h.sessions[0].stopped, true);
});

test('the wiring returns the channel names it registered (the allowlist pin)', () => {
  const h = harness();
  assert.deepEqual(h.wiring.channels, ['ember:addStart', 'ember:addAnswer', 'ember:addStop', 'ember:addAttach']);
  assert.equal(h.wiring.eventChannel, 'ember:addEvent');
  assert.equal(h.wiring.exitChannel, 'ember:addExit');
});

/* ---------- capture-temp: the real fs edges ---------- */

test('the temp file is written 0600 into the given folder, named add-text-*.txt', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-temptext-'));
  const res = writeTempText(dir, 'some pasted text\nwith two lines\n');
  assert.equal(res.ok, true);
  assert.match(path.basename(res.path), /^add-text-\d+-\d{6}\.txt$/);
  assert.equal(fs.readFileSync(res.path, 'utf8'), 'some pasted text\nwith two lines\n');
  const mode = fs.statSync(res.path).mode & 0o777;
  assert.equal(mode, 0o600, 'the pasted draft is owner-only');
  removeTempFile(res.path);
  assert.equal(fs.existsSync(res.path), false);
});

test('a failed write returns APP-000 and removes nothing', () => {
  const res = writeTempText('/definitely/not/a/real/folder', 'x');
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'APP-000');
});

test('cleanStaleTempFiles removes only its own leftovers (a crash at next start)', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-temptext-'));
  fs.writeFileSync(path.join(dir, 'add-text-111-000001.txt'), 'crashed draft', 'utf8');
  fs.writeFileSync(path.join(dir, 'add-text-111-000002.txt'), 'crashed draft', 'utf8');
  fs.writeFileSync(path.join(dir, 'keep-me.txt'), 'not mine', 'utf8');
  fs.mkdirSync(path.join(dir, 'add-text-dir.txt')); // a directory with our name: untouchable-ish
  const removed = cleanStaleTempFiles(dir);
  assert.equal(removed, 2);
  assert.equal(fs.existsSync(path.join(dir, 'keep-me.txt')), true);
  assert.equal(fs.existsSync(path.join(dir, 'add-text-dir.txt')), true, 'a directory named like a temp file is left alone');
});

test('the temp name is always add-text-*.txt shaped', () => {
  const name = tempName(() => 1234, () => 0.5);
  assert.match(name, /^add-text-1234-500000\.txt$/);
  assert.equal(TEMP_PREFIX, 'add-text-');
});

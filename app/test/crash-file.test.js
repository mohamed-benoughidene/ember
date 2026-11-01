'use strict';

/**
 * The app-side crash-folder helper (Spec-Batch2, decision N4): the one
 * rule for WHERE crash reports live, shared with the engine via the
 * same XDG rule. The engine writes the files; the app only needs to
 * FIND them (Copy crash report / Show file, Chunk 13). Pure path
 * rules (T1): strings in, strings out — these tests never create or
 * even list a real folder.
 *
 * Safety: every XDG_STATE_HOME this test sets points at a scratch
 * folder under /tmp/opencode/batch2/chunk12 — NEVER at the user's real
 * ~/.local/state.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');

const { crashDir, crashPath } = require('../main/crash-file');

const SCRATCH = '/tmp/opencode/batch2/chunk12';

test('crashDir honours XDG_STATE_HOME (N4)', () => {
  const saved = process.env.XDG_STATE_HOME;
  try {
    process.env.XDG_STATE_HOME = path.join(SCRATCH, 'state-a');
    assert.equal(crashDir(), path.join(SCRATCH, 'state-a', 'ember', 'crashes'));
    // An empty value counts as unset (the XDG rule falls back).
    process.env.XDG_STATE_HOME = '';
    assert.equal(crashDir(), path.join(os.homedir(), '.local', 'state', 'ember', 'crashes'));
  } finally {
    if (saved === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = saved;
  }
});

test('crashDir falls back to the XDG default state folder', () => {
  const saved = process.env.XDG_STATE_HOME;
  delete process.env.XDG_STATE_HOME;
  try {
    // A string comparison only — the real folder is never listed or created.
    assert.equal(crashDir(), path.join(os.homedir(), '.local', 'state', 'ember', 'crashes'));
    assert.equal(
      crashPath('20261101T000000Z-abc123'),
      path.join(os.homedir(), '.local', 'state', 'ember', 'crashes', '20261101T000000Z-abc123.txt'),
    );
  } finally {
    if (saved !== undefined) process.env.XDG_STATE_HOME = saved;
  }
});

test('crashPath refuses a crash id containing / or ..', () => {
  for (const bad of ['a/b', '..', '../evil', 'x/../y', 'id/sub/..', '/abs']) {
    assert.throws(() => crashPath(bad), /crash id/i, `expected a refusal for ${JSON.stringify(bad)}`);
  }
  // A plain engine-shaped id (Chunk 2: UTC timestamp + 6 hex) passes.
  assert.equal(
    crashPath('20261101T000000Z-abc123'),
    path.join(crashDir(), '20261101T000000Z-abc123.txt'),
  );
});

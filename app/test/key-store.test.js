'use strict';

/**
 * The key store tests (step file §2, "key store fake paths", decision
 * 4-A): a fake safeStorage stands in for the OS keyring. The key file
 * must never hold plain text; a weak/missing backend refuses with
 * APP-003 and offers the session-only path.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createKeyStore, isBackendTrusted } = require('../main/key-store');

const KEY = 'sk-or-v1-test-key-abcdef0123456789';

/** A safeStorage fake over a masked "keyring" (never a real secret
 * store). Like the real safeStorage, decryptString THROWS when the
 * bytes are not ours (corrupt file, wrong backend). */
function fakeSafeStorage(backend) {
  const MAGIC = Buffer.from('EMBERFAKE1');
  const mask = Buffer.from('fake-keyring-mask');
  return {
    getSelectedStorageBackend: () => backend,
    encryptString: (plain) => {
      const data = Buffer.from(plain, 'utf8');
      const out = Buffer.alloc(data.length);
      for (let i = 0; i < data.length; i += 1) out[i] = data[i] ^ mask[i % mask.length];
      return Buffer.concat([MAGIC, out]);
    },
    decryptString: (buffer) => {
      if (buffer.length < MAGIC.length || !buffer.subarray(0, MAGIC.length).equals(MAGIC)) {
        throw new Error('Failed to decrypt: the bytes were not encrypted by this backend');
      }
      const body = buffer.subarray(MAGIC.length);
      const out = Buffer.alloc(body.length);
      for (let i = 0; i < body.length; i += 1) out[i] = body[i] ^ mask[i % mask.length];
      return out.toString('utf8');
    },
  };
}

function tempFile() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ember-key-'));
  return path.join(dir, 'key.enc');
}

test('the backend rule: real keyrings pass, basic_text and nothing fail', () => {
  assert.equal(isBackendTrusted(fakeSafeStorage('kwallet6')), true);
  assert.equal(isBackendTrusted(fakeSafeStorage('gnome_libsecret')), true);
  assert.equal(isBackendTrusted(fakeSafeStorage('basic_text')), false);
  assert.equal(isBackendTrusted(fakeSafeStorage(undefined)), false);
  assert.equal(isBackendTrusted(null), false);
  assert.equal(isBackendTrusted({}), false);
});

test('a strong backend stores the key encrypted and round-trips it', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  const result = store.set(KEY);
  assert.deepEqual(result, { ok: true });
  assert.equal(store.get().key, KEY, 'the same key comes back');
  assert.equal(store.get().state, 'key');

  // THE security pin: the bytes on disk are NOT the key.
  const onDisk = fs.readFileSync(file, 'utf8');
  assert.ok(!onDisk.includes(KEY), 'the plain key must never reach the disk');
  const decoded = Buffer.from(onDisk, 'base64');
  assert.ok(!decoded.toString('utf8').includes(KEY), 'not even base64 of the plain key');
});

test('the saved file is readable only by the owner (0600)', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  store.set(KEY);
  const mode = fs.statSync(file).mode & 0o777;
  assert.equal(mode, 0o600, `mode was ${mode.toString(8)}`);
});

test('no key stored yet: get() is null and status says so', () => {
  const store = createKeyStore({ file: tempFile(), safeStorage: fakeSafeStorage('kwallet6') });
  assert.deepEqual(store.get(), { state: 'absent', key: null });
  assert.deepEqual(store.status(), { stored: false, sessionOnly: false, unreadable: false, backend: 'kwallet6' });
});

test('a weak backend refuses to save with APP-003 and writes NOTHING (decision 4-A)', () => {
  for (const backend of ['basic_text', undefined]) {
    const file = tempFile();
    const store = createKeyStore({ file, safeStorage: fakeSafeStorage(backend) });
    const result = store.set(KEY);
    assert.equal(result.ok, false, backend);
    assert.equal(result.error.code, 'APP-003');
    assert.equal(result.error.name, 'KeyStoreUnavailable');
    assert.ok(!result.error.detail.includes(KEY), 'the error must never quote the key');
    assert.equal(fs.existsSync(file), false, 'no file, not even an empty one');
  }
});

test('the session-only offer: the key works this session, the disk stays empty', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('basic_text') });
  assert.deepEqual(store.setSessionOnly(KEY), { ok: true });
  assert.equal(store.get().state, 'key');
  assert.equal(store.get().key, KEY);
  assert.equal(fs.existsSync(file), false, 'the weak-backend path must not write the key');
  assert.deepEqual(store.status(), { stored: false, sessionOnly: true, unreadable: false, backend: 'basic_text' });
});

test('a session-only key does not survive a "restart" (a fresh store)', () => {
  const file = tempFile();
  createKeyStore({ file, safeStorage: fakeSafeStorage('basic_text') }).setSessionOnly(KEY);
  const revived = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  assert.deepEqual(revived.get(), { state: 'absent', key: null }, 'the key was never written, so a restart loses it');
});

test('saving properly replaces a session-only key', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  store.setSessionOnly(KEY);
  store.set('sk-or-v1-real-saved-key');
  assert.equal(store.status().sessionOnly, false);
  assert.equal(store.get().key, 'sk-or-v1-real-saved-key');
});

test('remove deletes the file and the session copy (careful action, story 89)', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  store.set(KEY);
  assert.deepEqual(store.remove(), { ok: true });
  assert.equal(fs.existsSync(file), false);
  assert.deepEqual(store.get(), { state: 'absent', key: null });
  assert.deepEqual(store.remove(), { ok: true }, 'removing twice stays calm');
});

test('a corrupt key file reads as UNREADABLE (fix F6), never as "no key"', () => {
  const file = tempFile();
  fs.writeFileSync(file, 'not base64 at all');
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  // The distinct result: present but unreadable. No key bytes in it.
  assert.deepEqual(store.get(), { state: 'unreadable', key: null });
  // The status flag the screens read (a boolean only, never the key).
  assert.equal(store.status().unreadable, true);
  assert.equal(store.status().stored, true);
});

test('a missing file stays ABSENT, and a good key stays readable (fix F6)', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  assert.deepEqual(store.get(), { state: 'absent', key: null });
  assert.equal(store.status().unreadable, false);
  assert.equal(store.set('sk-or-v1-abcdef1234567890abcd').ok, true);
  const held = store.get();
  assert.equal(held.state, 'key');
  assert.equal(held.key, 'sk-or-v1-abcdef1234567890abcd');
  assert.equal(store.status().unreadable, false);
  // A session-only key does not make the (missing) file "unreadable".
  const fresh = createKeyStore({ file: tempFile(), safeStorage: fakeSafeStorage('kwallet6') });
  fresh.setSessionOnly('sk-or-v1-abcdef1234567890abcd');
  assert.deepEqual(fresh.get(), { state: 'key', key: 'sk-or-v1-abcdef1234567890abcd' });
  assert.equal(fresh.status().unreadable, false);
});

test('the settings words for an unreadable key tell the user to paste again (fix F6)', async () => {
  const { aiStatusWords } = await import('../renderer/screens/settings.mjs');
  const words = aiStatusWords({ stored: true, unreadable: true });
  assert.match(words.title, /could not be read/);
  assert.match(words.help, /Paste the key again/);
  // No key text can ever be part of the words (I21: zero secrets).
  const fakeKey = 'sk-or-v1-abcdef1234567890abcd';
  assert.ok(!words.title.includes(fakeKey) && !words.help.includes(fakeKey));
  // The other states keep their pinned sentences (null = caller's own).
  assert.equal(aiStatusWords({ stored: true }), null);
  assert.equal(aiStatusWords(null), null);
});

test('an empty or non-string key is refused without touching the disk', () => {
  const file = tempFile();
  const store = createKeyStore({ file, safeStorage: fakeSafeStorage('kwallet6') });
  for (const bad of ['', null, 42]) {
    const result = store.set(bad);
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'APP-003');
  }
  assert.deepEqual(store.setSessionOnly(42).error.code, 'APP-003');
  assert.equal(fs.existsSync(file), false);
});

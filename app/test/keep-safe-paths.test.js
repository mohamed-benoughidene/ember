'use strict';

/**
 * The Keep safe pure path-safety logic (app step 09; ticket A38), unit
 * tested without a DOM or a filesystem (T1): the save-dialog default
 * names, the chosen-path shape check, and the onto-itself CAUTION.
 * The real self-overwrite RULE stays in the engine (B3) — these are
 * the app's own suggestions, shape checks and caution label only, and
 * that boundary is asserted here too.
 */

const test = require('node:test');
const assert = require('node:assert/strict');

test('the save-dialog default names sit beside the knowledge base and never equal it', async () => {
  const { defaultBackupTarget, defaultExportTarget } = await import('../shared/keep-safe-paths.mjs');
  const db = '/home/someone/ember/ember.db';
  assert.equal(defaultBackupTarget(db), '/home/someone/ember/ember-backup.db');
  assert.equal(defaultExportTarget(db), '/home/someone/ember/ember-export.txt');
  assert.notEqual(defaultBackupTarget(db), db);
  assert.notEqual(defaultExportTarget(db), db);
  // The onto-itself guard by construction: the suggested name carries
  // the suffix, so a suggestion can never be the knowledge base itself.
  assert.ok(defaultBackupTarget(db).includes('-backup'));
  assert.ok(defaultExportTarget(db).endsWith('.txt'), 'an export is a text file any editor reads');
  // Garbage in -> null, never a broken suggestion on screen.
  assert.equal(defaultBackupTarget(''), null);
  assert.equal(defaultBackupTarget('/'), null);
  assert.equal(defaultBackupTarget('no-folder.db'), null);
  assert.equal(defaultExportTarget(undefined), null);
  // A stem without an extension still works; a dotfile keeps its name whole.
  assert.equal(defaultBackupTarget('/tmp/ember'), '/tmp/ember-backup.db');
  assert.equal(defaultBackupTarget('/tmp/.ember'), '/tmp/.ember-backup.db');
});

test('validateChosenPath refuses only OBVIOUSLY unusable picks (the engine owns the rules)', async () => {
  const { validateChosenPath } = await import('../shared/keep-safe-paths.mjs');
  assert.deepEqual(validateChosenPath(''), { ok: false, reason: 'empty' });
  assert.deepEqual(validateChosenPath('   '), { ok: false, reason: 'empty' });
  assert.deepEqual(validateChosenPath(null), { ok: false, reason: 'empty' });
  assert.deepEqual(validateChosenPath('relative/name.db'), { ok: false, reason: 'relative' });
  assert.deepEqual(validateChosenPath('~/ember.db'), { ok: false, reason: 'relative' }, 'an unexpanded ~ is not a usable absolute path here');
  assert.deepEqual(validateChosenPath('/tmp/folder/'), { ok: false, reason: 'no-file-name' });
  // Usable shapes pass; whether the engine may WRITE there is its call.
  assert.deepEqual(validateChosenPath('/tmp/backups/ember.db'), { ok: true });
  assert.deepEqual(validateChosenPath('C:\\Users\\me\\ember.db'), { ok: true });
  assert.deepEqual(validateChosenPath('/tmp/with space/ember db.db'), { ok: true });
});

test('the onto-itself CAUTION sees the obvious spellings and stays a caution only', async () => {
  const { isSelfOverwrite } = await import('../shared/keep-safe-paths.mjs');
  const db = '/home/me/Ember/ember.db';
  // Same spelling, and the spellings a human actually types.
  assert.equal(isSelfOverwrite(db, db), true);
  assert.equal(isSelfOverwrite('/home/me/Ember/ember.db/', db), true, 'a trailing separator is the same file');
  assert.equal(isSelfOverwrite('/home/me/Ember//ember.db', db), true, 'a doubled separator is the same file');
  assert.equal(isSelfOverwrite('/HOME/ME/EMBER/EMBER.DB', db), true, 'case is not a difference on these systems');
  assert.equal(isSelfOverwrite('/home/me/Ember/./ember.db', db), true, 'a dot segment is the same file');
  // Different files (and different stems) are NOT the knowledge base.
  assert.equal(isSelfOverwrite('/home/me/Ember/ember-backup.db', db), false);
  assert.equal(isSelfOverwrite('/other/place/ember.db', db), false);
  assert.equal(isSelfOverwrite('', db), false);
  // The caution can never BLOCK anything: it returns a boolean the
  // screen shows as a note; a refusal is the engine's BACKUP-003 /
  // EXPORT-002 (asserted on the real engine in keep-safe-contract.test.js).
  assert.equal(typeof isSelfOverwrite(db, db), 'boolean');
});

test('splitPath is the shared base of the pure helpers', async () => {
  const { splitPath } = await import('../shared/keep-safe-paths.mjs');
  assert.deepEqual(splitPath('/a/b/kb.db'), { dir: '/a/b', stem: 'kb', ext: '.db' });
  assert.deepEqual(splitPath('/a/b/kb'), { dir: '/a/b', stem: 'kb', ext: '' });
  assert.equal(splitPath('/a/b/'), null);
  assert.equal(splitPath(''), null);
  assert.equal(splitPath('/a/b/..'), null);
});

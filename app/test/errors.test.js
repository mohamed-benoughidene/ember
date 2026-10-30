'use strict';

/** The APP- namespace pins (plan §6): stable codes, stable names, I17. */

const test = require('node:test');
const assert = require('node:assert/strict');
const { APP_CODES, NAMES, AppError, appErrorInfo, asAppError } = require('../shared/errors');

test('the nine codes exist and their names match the plan table', () => {
  assert.deepEqual(Object.values(APP_CODES), [
    'APP-000',
    'APP-001',
    'APP-002',
    'APP-003',
    'APP-004',
    'APP-005',
    'APP-006',
    'APP-007',
    'APP-008',
  ]);
  assert.deepEqual(NAMES, {
    'APP-000': 'AppError',
    'APP-001': 'BridgeSpawnFailed',
    'APP-002': 'BridgeOutputInvalid',
    'APP-003': 'KeyStoreUnavailable',
    'APP-004': 'SettingsUnreadable',
    'APP-005': 'ShortcutRegistrationFailed',
    'APP-006': 'KnowledgeBaseMissing',
    'APP-007': 'RuntimeMissing',
    'APP-008': 'BridgeTimeout',
  });
});

test('an AppError carries code, name, where, detail — nothing secret by construction', () => {
  const err = new AppError('APP-003', 'KeyStoreUnavailable', 'main.key-store.set', 'the keyring refused');
  assert.equal(err.code, 'APP-003');
  assert.equal(err.name, 'KeyStoreUnavailable');
  assert.equal(err.where, 'main.key-store.set');
  assert.equal(err.detail, 'the keyring refused');
  assert.deepEqual(err.toInfo(), { code: 'APP-003', name: 'KeyStoreUnavailable', where: 'main.key-store.set', detail: 'the keyring refused' });
});

test('unknown codes are refused loudly (no spelling drift into the namespace)', () => {
  assert.throws(() => appErrorInfo('APP-009', 'x', 'y'), /unknown APP code/);
  assert.throws(() => appErrorInfo('BRIDGE-001', 'x', 'y'), /unknown APP code/);
});

test('asAppError(info) rebuilds the real error from its plain shape', () => {
  const info = appErrorInfo('APP-008', 'main.bridge-client.runCommand', 'timed out');
  const err = asAppError(info);
  assert.ok(err instanceof AppError);
  assert.deepEqual(err.toInfo(), info);
});

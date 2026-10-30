'use strict';

/*
 * The placeholder screen (L3 app step 02, the smallest end-to-end
 * proof). It shows "Ember is starting", then the knowledge base item
 * count from one real read command (`ember list-items`), or a plain
 * named error line. Real screens are steps 04+; the design system is
 * step 03. This file uses ONLY the window.ember preload allowlist —
 * no Node, no Electron, asserted by test/preload-allowlist.test.js.
 */

const startedEl = document.querySelector('[data-testid="status"]');
const itemsEl = document.querySelector('[data-testid="items"]');
const errorEl = document.querySelector('[data-testid="error"]');

function showError(error) {
  startedEl.textContent = 'Something did not work';
  // No bare code on screen: the plain sentence carries the code name.
  errorEl.textContent = `${error.code} ${error.name}: ${error.detail}`;
}

async function run() {
  const seam = await window.ember.ping();
  if (seam !== 'pong') {
    showError({ code: 'APP-002', name: 'BridgeOutputInvalid', detail: 'the preload seam did not answer' });
    return;
  }
  const state = await window.ember.getState();
  if (state.settingsNotice) showError(state.settingsNotice);
  else if (state.bootNotice) showError(state.bootNotice);

  const result = await window.ember.listItems();
  if (!result.ok) {
    showError(result.error);
    return;
  }
  startedEl.textContent = 'Ember is running';
  itemsEl.textContent = `items: ${result.data.total}`;
}

run().catch(() => {
  startedEl.textContent = 'Something did not work';
  errorEl.textContent = 'The window could not reach the app core. Close and reopen Ember.';
});

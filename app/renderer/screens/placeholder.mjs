/**
 * The interim panes (Add, Link items, Fix and close, Clean up, Keep
 * safe, Settings): their real screens are build steps 05-11. Home's
 * buttons (stories 9, 14, 15) must land somewhere honest — so each
 * pane shows its real title and one empty state saying the screen
 * arrives in a later build step. Nothing here pretends to work.
 */

import { buttonHtml } from '../components/button.mjs';
import { emptyHtml } from '../components/state-block.mjs';

const PANES = {
  add: { name: 'Add', sub: 'Turn text into items. Ember proposes; you confirm.' },
  link: { name: 'Link items', sub: 'Connect related items: supports, contradicts, supersedes, answers, depends on.' },
  fix: { name: 'Fix and close', sub: 'Change an item or a link. Every change is written to the ledger.' },
  cleanup: { name: 'Clean up', sub: 'The sweep: preview what the links imply, then apply.' },
  keepsafe: { name: 'Keep safe', sub: 'Back up, export, and check the knowledge base file.' },
  settings: { name: 'Settings', sub: 'Text size, colours, quick popup, AI connection.' },
};

export function paneNames() {
  return Object.keys(PANES);
}

export function createPlaceholderScreen(ctx, paneId) {
  const pane = PANES[paneId];
  return {
    render() {
      ctx.renderFrame(
        `<div data-testid="pane-${paneId}">
          <div class="titlerow"><div class="grow"><h1>${pane.name}</h1>
            <p class="sub">${pane.sub}</p></div></div>
          <div data-testid="pane-body"></div>
        </div>`,
        (root) => {
          const body = root.querySelector('[data-testid="pane-body"]');
          body.innerHTML = emptyHtml({
            title: `The ${pane.name} screen arrives in a later build step. Nothing here works yet.`,
            next: 'Go to Home',
            onNext: 'placeholder-home',
          });
          body.querySelector('[data-action="placeholder-home"]')?.addEventListener('click', () => ctx.navigate('home'));
        },
      );
    },
  };
}

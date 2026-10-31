'use strict';

/**
 * The application menu's main-process manager (app step 12, plan
 * §5.7): it takes the PURE template (shared/menu-template.mjs), hands
 * Electron the template with ONE dispatch call per actionable item,
 * and can rebuild the whole menu whenever the context changed (the
 * Undo/Redo labels, a hide/reorder save, a sidebar toggle). This is
 * the only place the spec §9 menu touches Electron's Menu API (T2);
 * the manager is injected with a fake-able MenuApi, exactly like the
 * shortcut and tray managers (T3).
 */

/**
 * @param {object} args
 * @param {typeof Electron.Menu} args.MenuApi Electron's Menu (or a fake
 *   with buildFromTemplate/setApplicationMenu)
 * @param {'darwin'|'other'} args.platform the template's platform knob
 * @param {() => {kbChosen: boolean, sidebarVisible: boolean,
 *   jobs: {order: string[], hidden: string[]},
 *   undo: object, redo: object}} args.context the knobs, read fresh on
 *   every rebuild (settings may have changed between rebuilds)
 * @param {(actionId: string) => void} args.dispatch what an actionable
 *   item's click means (main.js maps the ids; the ONLY OS effects)
 */
function createAppMenuManager({ MenuApi, platform, context, dispatch }) {
  if (typeof MenuApi?.buildFromTemplate !== 'function' || typeof MenuApi?.setApplicationMenu !== 'function') {
    throw new TypeError('app-menu: MenuApi must have buildFromTemplate and setApplicationMenu');
  }
  if (typeof dispatch !== 'function') throw new TypeError('app-menu: dispatch must be a function');
  if (typeof context !== 'function') throw new TypeError('app-menu: context must be a function');

  /**
   * Attach click -> dispatch(item.id) to every actionable item. Items
   * with an Electron role (Cut, Minimize, Quit...) keep their role and
   * get NO click: one behaviour per item, the standard one.
   */
  function wire(submenu) {
    return submenu.map((item) => {
      if (item.type === 'separator' || item.role || !item.id) return item;
      return { ...item, click: () => dispatch(item.id) };
    });
  }

  /**
   * Rebuild the application menu from the current context. Safe to
   * call any number of times; every call REPLACES the menu, so the
   * labels and enabled states are never stale copies.
   */
  function refresh() {
    const pure = require('../shared/menu-template.mjs');
    const built = pure
      .buildMenuTemplate({ ...context(), platform })
      .map((menu) => ({ label: menu.label, submenu: wire(menu.submenu) }));
    MenuApi.setApplicationMenu(MenuApi.buildFromTemplate(built));
    return built;
  }

  return { refresh };
}

module.exports = { createAppMenuManager };

'use strict';

/**
 * The settings schema (interface-app-plan.md §5.3, D5/D6).
 *
 * Exactly the four settings of spec decision 8 — text size, colours
 * (light and dark), quick popup shortcut and position, menu order and
 * visibility — plus last pane and knowledge-base path. The schema is
 * versioned with a number (currently 1). Pure module (T1): no I/O.
 */

const SCHEMA_NUMBER = 1;

// [app 10] The five text-size values are the DESIGN.md steps Small,
// Default, Large, Larger, Largest (stories 82-83): Largest must be
// savable or the 200% floor (story 82) is unreachable. The earlier
// list carried `smallest` and no `larger`; see archive/interface-deviations.md.
const TEXT_SIZES = Object.freeze(['small', 'default', 'large', 'larger', 'largest']);
const COLOUR_THEMES = Object.freeze(['system', 'light', 'dark']);

const DEFAULT_MENU_ORDER = Object.freeze([
  'add',
  'lookup',
  'link',
  'fix',
  'cleanup',
  'keepsafe',
]);

const DEFAULTS = Object.freeze({
  schema: SCHEMA_NUMBER,
  textSize: 'default',
  colourTheme: 'system',
  quickPopup: Object.freeze({
    shortcut: 'CommandOrControl+Alt+E',
    position: 'bottom-right',
  }),
  menuOrder: DEFAULT_MENU_ORDER,
  menuHidden: Object.freeze([]),
  lastPane: 'home',
  knowledgeBasePath: '',
});

/**
 * Turn any parsed JSON value into valid settings (D6: validate at the
 * edge; unknown keys are dropped, wrong values fall back per field).
 * Never throws.
 *
 * @param {unknown} raw the parsed file content (or anything)
 * @returns {{settings: object, schemaChanged: boolean}} `schemaChanged`
 *   is true when the file's schema number was missing, foreign, or the
 *   file was not an object — the APP-004 "defaults used" case.
 */
function normalizeSettings(raw) {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return { settings: structuredClone(DEFAULTS), schemaChanged: true };
  }
  // A missing or foreign schema number means the file was not written
  // by this app version: pay the safe price, use full defaults (D5).
  if (raw.schema !== SCHEMA_NUMBER) {
    return { settings: structuredClone(DEFAULTS), schemaChanged: true };
  }
  const inList = (value, list, fallback) => (list.includes(value) ? value : fallback);
  const stringList = (value, fallback) =>
    Array.isArray(value) && value.every((v) => typeof v === 'string')
      ? Object.freeze([...value])
      : Object.freeze([...fallback]);
  const quickPopup =
    typeof raw.quickPopup === 'object' && raw.quickPopup !== null
      ? Object.freeze({
          shortcut:
            typeof raw.quickPopup.shortcut === 'string' && raw.quickPopup.shortcut.trim() !== ''
              ? raw.quickPopup.shortcut
              : DEFAULTS.quickPopup.shortcut,
          position:
            typeof raw.quickPopup.position === 'string' && raw.quickPopup.position.trim() !== ''
              ? raw.quickPopup.position
              : DEFAULTS.quickPopup.position,
        })
      : structuredClone(DEFAULTS.quickPopup);

  const settings = {
    schema: SCHEMA_NUMBER,
    textSize: inList(raw.textSize, TEXT_SIZES, DEFAULTS.textSize),
    colourTheme: inList(raw.colourTheme, COLOUR_THEMES, DEFAULTS.colourTheme),
    quickPopup,
    menuOrder: stringList(raw.menuOrder, DEFAULT_MENU_ORDER),
    menuHidden: stringList(raw.menuHidden, []),
    lastPane: typeof raw.lastPane === 'string' && raw.lastPane.trim() !== '' ? raw.lastPane : DEFAULTS.lastPane,
    knowledgeBasePath:
      typeof raw.knowledgeBasePath === 'string' ? raw.knowledgeBasePath : DEFAULTS.knowledgeBasePath,
  };
  return { settings, schemaChanged: false };
}

module.exports = { SCHEMA_NUMBER, TEXT_SIZES, COLOUR_THEMES, DEFAULTS, normalizeSettings };

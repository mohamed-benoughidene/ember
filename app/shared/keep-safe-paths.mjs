/**
 * Pure path-safety helpers for the Keep safe screen (app step 09, L3
 * app step file §1; ticket A38). Pure module (T1): strings in, strings
 * out; no fs, no DOM, no I/O. Unit-tested in test/keep-safe-paths.test.js.
 *
 * THE RULE STAYS IN PYTHON (Constitution B3): whether a backup or an
 * export may really write a target is the engine's decision — back up
 * refuses a target that IS the knowledge base file (BACKUP-003, see
 * `ember/adapters/backup.py` + `ember/adapters/paths.py same_path`);
 * export refuses `--out` naming the database (EXPORT-002). The app
 * does NOT pre-judge that refusal (step file §1: the engine's refusal
 * is shown in plain words, story 72). What the APP may decide on its
 * own is only this much:
 *
 * - which name it SUGGESTS in the save dialog (never the knowledge
 *   base itself, never an empty string);
 * - whether a chosen path is OBVIOUSLY unusable before any child
 *   process is started (empty, relative, directory-shaped), because
 *   the app owns the dialog;
 * - a caution label when the chosen target looks like the knowledge
 *   base itself — a statement of fact on screen, while the engine's
 *   own refusal still decides the outcome.
 */

/**
 * Split a path into dir / stem / extension. Returns null for anything
 * that is not a usable absolute-looking path (empty, no file name).
 *
 * @param {string} p
 * @returns {{dir: string, stem: string, ext: string}|null}
 */
export function splitPath(p) {
  if (typeof p !== 'string') return null;
  const text = p.trim();
  if (text === '' || text.endsWith('/') || text.endsWith('\\')) return null;
  const slash = Math.max(text.lastIndexOf('/'), text.lastIndexOf('\\'));
  const dir = slash === -1 ? '' : text.slice(0, slash);
  const name = slash === -1 ? text : text.slice(slash + 1);
  if (name === '' || name === '.' || name === '..') return null;
  const dot = name.lastIndexOf('.');
  const stem = dot <= 0 ? name : name.slice(0, dot);
  const ext = dot <= 0 ? '' : name.slice(dot);
  return { dir, stem, ext };
}

/**
 * The backup target the save dialog SUGGESTS: beside the knowledge
 * base, same extension, `-backup` appended. Never equal to the
 * knowledge base path itself (that name carries `-backup`). Garbage
 * in -> null, so the screen shows plain words instead of a broken
 * default (never pre-judges a real refusal).
 *
 * @param {string} dbPath
 * @returns {string|null}
 */
export function defaultBackupTarget(dbPath) {
  const parts = splitPath(dbPath);
  if (parts === null || parts.dir === '') return null;
  return `${parts.dir}/${parts.stem}-backup${parts.ext || '.db'}`;
}

/**
 * The export target the save dialog SUGGESTS: a `.txt` beside the
 * knowledge base, so any editor opens it. Never equal to the knowledge
 * base path itself. Garbage in -> null.
 *
 * @param {string} dbPath
 * @returns {string|null}
 */
export function defaultExportTarget(dbPath) {
  const parts = splitPath(dbPath);
  if (parts === null || parts.dir === '') return null;
  return `${parts.dir}/${parts.stem}-export.txt`;
}

/**
 * Lower-cased, separator-normalised form for CAUTION comparisons only
 * (`.`, empty segments and trailing separators collapse; Windows
 * backslashes fold to `/`). This is string logic; it can never see
 * symlinks or hard links. The ENGINE's `same_path` (os.path.samefile)
 * remains the only real rule (B3); this function only feeds an on-screen
 * caution that never blocks anything.
 *
 * @param {string} p
 * @returns {string}
 */
export function normalizeForCompare(p) {
  if (typeof p !== 'string') return '';
  return p
    .trim()
    .replace(/\\/g, '/')
    .replace(/\/{2,}/g, '/')
    .replace(/\/(\.\/)+/g, '/')
    .replace(/\/+$/, '')
    .toLowerCase();
}

/**
 * The onto-itself caution: true when the CHOSEN target obviously names
 * the same file as the knowledge base by spelling. Fact, not ruling:
 * the screen shows a caution line and still runs the engine, whose own
 * refusal (BACKUP-003 / EXPORT-002) is what the user sees.
 *
 * @param {string} targetPath
 * @param {string} dbPath
 * @returns {boolean}
 */
export function isSelfOverwrite(targetPath, dbPath) {
  const target = normalizeForCompare(targetPath);
  const source = normalizeForCompare(dbPath);
  if (target === '' || source === '') return false;
  return target === source;
}

/**
 * Whether a path the user just chose is OBVIOUSLY unusable, judged
 * before any child process starts (the app owns its dialog; I9). This
 * is not an Ember rule — it is the shape of a usable file path.
 *
 * @param {string} p
 * @returns {{ok: true} | {ok: false, reason: 'empty'|'relative'|'no-file-name'}}
 */
export function validateChosenPath(p) {
  if (typeof p !== 'string' || p.trim() === '') return { ok: false, reason: 'empty' };
  const text = p.trim();
  if (!text.startsWith('/') && !/^[A-Za-z]:[\\/]/.test(text)) {
    return { ok: false, reason: 'relative' };
  }
  if (text.endsWith('/') || text.endsWith('\\')) return { ok: false, reason: 'no-file-name' };
  return { ok: true };
}

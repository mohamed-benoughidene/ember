/**
 * Keep safe (app step 09, spec stories 70-77; ticket A38). Four blocks
 * in one column, from the approved prototype (PROTOTYPE "safe" pane:
 * title row + one panel of rows; DESIGN.md components only):
 *
 * - BACK UP (70-72, 77): one button; the OS save dialog suggests a name
 *   beside the knowledge base (defaultBackupTarget, app/shared/keep-safe-paths.mjs);
 *   `backup` writes a restorable snapshot and the result line shows the
 *   engine's own report — location, format version, item count, and the
 *   kept-older-copy line when the engine rotated one aside (story 71).
 *   A refusal is the ENGINE's words (BACKUP- codes through the shared
 *   sentence table, stories 72/77); the app never pre-judges it — the
 *   onto-itself caution (`isSelfOverwrite`) states a fact on screen and
 *   still lets the engine decide.
 * - EXPORT (73-74, 77): one line says an export cannot be restored
 *   into Ember; `export --out` is exit-code-driven and the app reads no
 *   export JSON (step file §1).
 * - HEALTH CHECK (75): `db-check` runs when the pane opens and on
 *   Retry; every report line reads as one plain sentence via the
 *   shared read-map (plain-sentences.mjs, step-09 block); OK / DRIFT /
 *   UNREADABLE each get their words and their way forward.
 * - OPEN A DIFFERENT FILE (76): picker -> one confirmation naming the
 *   file and saying the current file is unchanged -> db-check gate
 *   (UNREADABLE -> APP-006; an older v12 file passes) -> the setting
 *   changes; the pane offers to reload onto the new file.
 *
 * Every failure says the knowledge base file is unchanged (story 77 —
 * true by construction: backup/export never write the live file).
 * Needs NO AI key (spec §2: every command here works without one).
 */

import { esc } from '../design/escape-html.mjs';
import { buttonHtml } from '../components/button.mjs';
import { errorHtml, stateBlockHtml } from '../components/state-block.mjs';
import { sentenceFor, dbCheckVerdictWords, dbCheckRowSentence } from '../../shared/plain-sentences.mjs';
import { defaultBackupTarget, defaultExportTarget, isSelfOverwrite, validateChosenPath } from '../../shared/keep-safe-paths.mjs';

export function createKeepSafeScreen(ctx) {
  const kbPath = (ctx.state && ctx.state.effectiveKbPath) || '';
  const state = {
    backup: { phase: 'idle', target: null, result: null, error: null, caution: false },
    export: { phase: 'idle', target: null, result: null, error: null },
    check: { phase: 'loading', report: null, error: null },
    open: { phase: 'idle', chosen: null, current: kbPath, check: null, error: null },
  };

  function refresh() {
    ctx.renderFrame(html(), wire);
  }

  function render() {
    refresh();
  }

  /* ---------------- block renderers ---------------- */

  function backupBlockHtml() {
    const s = state.backup;
    let result = '';
    if (s.phase === 'loading') {
      result = '<p class="help" role="status" data-testid="ks-backup-busy">Writing the backup copy… Your knowledge base file is only read.</p>';
    } else if (s.phase === 'ok' && s.result) {
      const r = s.result;
      const rotated = r.rotated
        ? ` An older copy was already there; it was kept beside the new one as <span class="mono">${esc(r.rotated)}</span>.`
        : '';
      result = `<div class="ok" role="status" data-testid="ks-backup-result">Backup written: <span class="mono">${esc(r.path)}</span>. File format version ${esc(
        String(r.schemaVersion),
      )}, ${esc(String(r.itemCount))} items inside.${rotated} Your knowledge base file is unchanged.</div>`;
    } else if (s.phase === 'error') {
      result = errorAreaHtml('backup', 'ks-backup-retry', s.error);
    }
    const caution =
      s.phase === 'loading' && s.caution
        ? '<p class="help" data-testid="ks-self-caution">The place you picked is your knowledge base file itself, by the way.</p>'
        : '';
    return `<div class="panel"><div class="pad" data-testid="ks-backup">
      <strong>Back up</strong>
      <p class="help" style="margin:0">A copy you can restore later by opening it as your knowledge base file. Ember refuses to write over your knowledge base file itself, and keeps up to three older copies beside a new one.</p>
      <div class="actions">${buttonHtml({ label: 'Back up now', action: 'ks-backup-run', variant: 'primary', testid: 'ks-backup-run' })}</div>
      ${caution}${result}
    </div></div>`;
  }

  function exportBlockHtml() {
    const s = state.export;
    let result = '';
    if (s.phase === 'loading') {
      result = '<p class="help" role="status" data-testid="ks-export-busy">Writing the export… Your knowledge base file is only read.</p>';
    } else if (s.phase === 'ok' && s.result) {
      result = `<div class="ok" role="status" data-testid="ks-export-result">Export written: <span class="mono">${esc(s.result.outPath)}</span>. It cannot be restored into Ember — the backup above is what restores. Your knowledge base file is unchanged.</div>`;
    } else if (s.phase === 'error') {
      result = errorAreaHtml('export', 'ks-export-retry', s.error);
    }
    return `<div class="panel"><div class="pad" data-testid="ks-export">
      <strong>Export</strong>
      <p class="help" style="margin:0">A plain text file any editor can read, so your knowledge outlives Ember. An export cannot be restored into Ember.</p>
      <div class="actions">${buttonHtml({ label: 'Export as text…', action: 'ks-export-run', variant: 'secondary', testid: 'ks-export-run' })}</div>
      ${result}
    </div></div>`;
  }

  function checkBlockHtml() {
    const s = state.check;
    let body = '';
    if (s.phase === 'loading') {
      body = `<div data-testid="ks-check-body">${stateBlockHtml('loading', { hint: 'Reading the file. The check never writes…' })}</div>`;
    } else if (s.phase === 'error') {
      body = `<div data-testid="ks-check-body">${errorAreaHtml('check', 'ks-check-retry', s.error)}</div>`;
    } else if (s.phase === 'report' && s.report) {
      const verdict = dbCheckVerdictWords(s.report.result);
      const titleClass = verdict.kind === 'ok' ? 'ok' : 'errbox';
      const rows = s.report.lines.map((line) => `<li data-testid="ks-check-row">${esc(dbCheckRowSentence(line))}</li>`).join('');
      body = `<div data-testid="ks-check-body">
        <div class="${titleClass}" data-testid="ks-check-verdict" role="${verdict.kind === 'ok' ? 'status' : 'alert'}">
          <strong>${esc(verdict.title)}</strong><span class="detail">${esc(verdict.what)}</span><span class="hint">${esc(verdict.next)}</span>
          <div class="actions">${buttonHtml({ label: 'Run the check again', action: 'ks-check-retry', variant: 'secondary', testid: 'ks-check-retry' })}</div>
        </div>
        <ul class="lineage" data-testid="ks-check-rows">${rows}</ul>
      </div>`;
    }
    return `<div class="panel"><div class="pad" data-testid="ks-check">
      <strong>Health check</strong>
      <p class="help" style="margin:0">Looks for broken or missing data inside the file. It reads only; it changes nothing.</p>
      ${body}
    </div></div>`;
  }

  function openBlockHtml() {
    const s = state.open;
    let body = '';
    if (s.phase === 'confirm') {
      body = `<div class="errbox" data-testid="ks-open-confirm" role="alertdialog" aria-label="Confirm switching knowledge base file">
        <strong>Open <span class="mono">${esc(s.chosen ?? '')}</span> as your knowledge base?</strong>
        <span class="detail">Your current file <span class="mono">${esc(s.current)}</span> stays exactly as it is. Ember will only look at a different file from now on.</span>
        <div class="actions">
          ${buttonHtml({ label: 'Open that file', action: 'ks-open-confirm', variant: 'primary', testid: 'ks-open-confirm-yes' })}
          ${buttonHtml({ label: 'Keep the current file', action: 'ks-open-cancel', variant: 'secondary', testid: 'ks-open-cancel' })}
        </div></div>`;
    } else if (s.phase === 'checking') {
      body = '<p class="help" role="status" data-testid="ks-open-busy">Checking the chosen file before anything changes…</p>';
    } else if (s.phase === 'ok' && s.check) {
      body = `<div class="ok" role="status" data-testid="ks-open-result">Now using <span class="mono">${esc(s.chosen ?? '')}</span>. Your previous file is unchanged.
        <div class="actions">${buttonHtml({ label: 'Show the new file', action: 'ks-open-reload', variant: 'primary', testid: 'ks-open-reload' })}</div></div>`;
    } else if (s.phase === 'error') {
      body = `<div>${errorAreaHtml('open', 'ks-open-retry2', s.error)}
        <div class="actions">${buttonHtml({ label: 'Back to the current file', action: 'ks-open-cancel', variant: 'secondary', testid: 'ks-open-back' })}</div></div>`;
    }
    return `<div class="panel"><div class="pad" data-testid="ks-open">
      <strong>Knowledge base file</strong>
      <p class="help" style="margin:0">Ember is using: <span class="mono" data-testid="ks-open-current">${esc(kbPath)}</span></p>
      <p class="help" style="margin:0">To go back to an older state, open an older backup file as the knowledge base. Restore is not a command: the file itself is the restore.</p>
      <div class="actions">${buttonHtml({ label: 'Open a different file…', action: 'ks-open-pick', variant: 'secondary', testid: 'ks-open-pick' })}</div>
      ${body}
    </div></div>`;
  }

  /**
   * One failing block's own error (stories 102-103): the shared plain
   * words for its code, Retry inside the block, the code behind
   * Details — never a bare code on screen.
   */
  function errorAreaHtml(which, retryAction, error) {
    const sentence = sentenceFor(error && error.code ? error.code : null);
    return `<div data-testid="ks-${which}-error">${errorHtml({
      title: sentence.title,
      detail: sentence.what,
      why: `${sentence.next} Your knowledge base file is unchanged.`,
      onRetry: retryAction,
    })}<p class="help" data-testid="ks-${which}-error-code" hidden>${esc(`${error ? `${error.code} ${error.name} | ${error.detail}` : 'no details'}`)}</p></div>`;
  }

  function html() {
    return `<div data-testid="keepsafe-pane">
      <div class="titlerow"><div class="grow"><h1>Keep safe</h1>
        <p class="sub">Protect your knowledge base. Nothing on this screen changes your items.</p></div></div>
      <div class="help" data-testid="ks-kb-line">Knowledge base file: <span class="mono">${esc(kbPath)}</span></div>
      ${backupBlockHtml()}
      ${exportBlockHtml()}
      ${checkBlockHtml()}
      ${openBlockHtml()}
    </div>`;
  }

  /* ---------------- actions ---------------- */

  async function runBackup() {
    const picked = await ctx.api.pickSaveFile({ kind: 'backup', defaultName: defaultBackupTarget(kbPath) ?? 'ember-backup.db' });
    if (!picked || !picked.ok) return; // cancelled: nothing happens
    state.backup = {
      phase: 'loading',
      target: picked.path,
      result: null,
      error: null,
      caution: isSelfOverwrite(picked.path, kbPath),
    };
    refresh();
    const result = await ctx.api.backupTo(picked.path);
    state.backup = result.ok
      ? { phase: 'ok', target: picked.path, result: result.data, error: null, caution: false }
      : { phase: 'error', target: picked.path, result: null, error: result.error, caution: false };
    refresh();
  }

  async function runExport() {
    const picked = await ctx.api.pickSaveFile({ kind: 'export', defaultName: defaultExportTarget(kbPath) ?? 'ember-export.txt' });
    if (!picked || !picked.ok) return;
    state.export = { phase: 'loading', target: picked.path, result: null, error: null };
    refresh();
    const result = await ctx.api.exportTo(picked.path);
    state.export = result.ok
      ? { phase: 'ok', target: picked.path, result: result.data, error: null }
      : { phase: 'error', target: picked.path, result: null, error: result.error };
    refresh();
  }

  async function loadCheck() {
    state.check = { phase: 'loading', report: null, error: null };
    refresh();
    const result = await ctx.api.dbCheck();
    state.check = result.ok
      ? { phase: 'report', report: result.data, error: null }
      : { phase: 'error', report: null, error: result.error };
    refresh();
  }

  async function openPicked() {
    const chosen = await ctx.api.pickKnowledgeBaseFile();
    if (chosen && chosen.error) {
      // The OS pick itself was refused (APP-006: not there / not an Ember file).
      state.open = { phase: 'error', chosen: null, current: kbPath, check: null, error: chosen.error };
      refresh();
      return;
    }
    if (!chosen || !chosen.ok || typeof chosen.path !== 'string') return; // cancelled
    state.open = { phase: 'confirm', chosen: chosen.path, current: kbPath, check: null, error: null };
    refresh();
  }

  async function openConfirm() {
    const chosen = state.open.chosen;
    const shape = validateChosenPath(chosen);
    if (!shape.ok) {
      state.open = {
        ...state.open,
        phase: 'error',
        error: { code: 'APP-006', name: 'KnowledgeBaseMissing', where: 'keepsafe', detail: 'the chosen file is not there or is not a file' },
      };
      refresh();
      return;
    }
    state.open = { ...state.open, phase: 'checking' };
    refresh();
    const result = await ctx.api.switchKnowledgeBase(chosen);
    state.open = result.ok
      ? { phase: 'ok', chosen, current: kbPath, check: result.data.check, error: null }
      : { phase: 'error', chosen, current: kbPath, check: null, error: result.error };
    refresh();
  }

  /* ---------------- wiring ---------------- */

  let checkStarted = false; // the check auto-runs once when the pane opens

  function wire(root) {
    root.querySelector('[data-action="ks-backup-run"]')?.addEventListener('click', () => runBackup().catch(() => {}));
    root.querySelector('[data-action="ks-export-run"]')?.addEventListener('click', () => runExport().catch(() => {}));
    root.querySelector('[data-action="ks-check-retry"]')?.addEventListener('click', () => loadCheck().catch(() => {}));
    root.querySelector('[data-action="ks-backup-retry"]')?.addEventListener('click', () => runBackup().catch(() => {}));
    root.querySelector('[data-action="ks-export-retry"]')?.addEventListener('click', () => runExport().catch(() => {}));
    root.querySelector('[data-action="ks-open-retry2"]')?.addEventListener('click', () => {
      state.open = { phase: 'idle', chosen: null, current: kbPath, check: null, error: null };
      refresh();
    });
    root.querySelector('[data-action="ks-open-pick"]')?.addEventListener('click', () => openPicked().catch(() => {}));
    root.querySelector('[data-action="ks-open-confirm"]')?.addEventListener('click', () => openConfirm().catch(() => {}));
    root.querySelector('[data-action="ks-open-cancel"]')?.addEventListener('click', () => {
      state.open = { phase: 'idle', chosen: null, current: kbPath, check: null, error: null };
      refresh();
    });
    root.querySelector('[data-action="ks-open-reload"]')?.addEventListener('click', () => window.location.reload());
    // The health check runs as soon as the pane first opens (it is
    // read-only; story 75). Later renders show the settled state, and
    // the Retry button re-runs it explicitly.
    if (!checkStarted) {
      checkStarted = true;
      loadCheck().catch(() => {});
    }
    // The error blocks' Details reveal the code (story 102): each error
    // area's own code line sits right after its state block.
    root.querySelectorAll('[data-action="show-details"]').forEach((button) => {
      button.addEventListener('click', () => {
        const area = button.closest('.state');
        const host = area && area.parentElement ? area.parentElement : null;
        const code = host ? host.querySelector('[data-testid$="-error-code"]') : null;
        if (code) code.hidden = !code.hidden;
      });
    });
  }

  return { render, loadCheck };
}

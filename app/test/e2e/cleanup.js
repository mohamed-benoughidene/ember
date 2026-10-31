'use strict';

/**
 * The Clean up E2E (L3 app step 08, ticket A37; the step file's check
 * command: `npm --prefix app run e2e -- cleanup`).
 *
 * This step's confirm loop NEEDS the AI over the bridge, so — unlike
 * the step-04 fake stub — this e2e runs the REAL `ember` from the venv
 * against a REAL temp knowledge base seeded by the Python helpers, with
 * the AI faked at the same seam the Python bridge tests use: a local
 * OpenAI-shaped server on EMBER_AI_BASE_URL returning one canned close
 * proposal. The key arrives as EMBER_AI_API_KEY in the launch env (the
 * bridge hands it to the child; the app's own key store stays empty).
 *
 * Scenarios:
 *  1. PREVIEW + APPLY-Accept: Apply disabled with its why (65), the
 *     preview table with before → after heat marks and the Because
 *     column (64), the counts and the "stale: N" note, the badge (68),
 *     the Apply label's count (66), the REAL proposal loop answered
 *     from the keyboard ('y', the engine's own prompt), the accepted
 *     close's report line as an inline message, the final summary with
 *     the new heat marks (67), and the REAL database row-verified.
 *  2. APPLY-Reject + Stop: two stale questions; the first proposal is
 *     rejected by button, the secondanswered with Esc/Stop = stop()
 *     (nothing more is asked); the result says Stopped, the declined
 *     question stays Active in the database.
 *  3. CAP NOTE: eleven stale questions — the preview lists ten and
 *     says the list is capped; with zero changes the badge stays
 *     hidden and the calm empty message shows (68, 69).
 *  4. NO KEY: an apply whose stale loop cannot reach a key fails
 *     INSIDE the block, with Retry, plain words and the code behind
 *     Details; the sweep changes written before the stop are real in
 *     the database.
 *
 * The step-03 accessibility helper runs on every state this e2e
 * renders, and Reduce Motion is honoured (96-104).
 */

const { _electron } = require('playwright');
const { execFile, execFileSync } = require('node:child_process');
const { promisify } = require('node:util');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { APP_ROOT, PYTHON, REPO_ROOT } = require('../util');
const { startFakeAiServer } = require('../helpers/fake-ai-server');

const execFileP = promisify(execFile);
const EMBER = path.join(REPO_ROOT, '.venv', 'bin', 'ember');

function fail(what) {
  throw new Error(what);
}

/* ---------- the seeds (real temp knowledge bases) ---------- */

const SEED_MIXED = `
import sys
from pathlib import Path
from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_link_with_confirmation, insert_source

db = sys.argv[1]
Path(db).touch()
conn = open_maintain_database(db)
try:
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type='Decision', statement='We chose SQLite')
    insert_item(conn, source_id=source_id, item_id=2, item_type='Finding', statement='Auth is measured')
    insert_item(conn, source_id=source_id, item_id=3, item_type='Finding', statement='Contradicted claim')
    insert_item(conn, source_id=source_id, item_id=7, item_type='Question', statement='should we cache tokens?', status_origin='manual')
    insert_link_with_confirmation(conn, 2, 3, 'contradicts')
    insert_link_with_confirmation(conn, 2, 7, 'answers', created_at='2026-01-01T00:00:00+00:00')
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (7, NULL, 'status_origin', 'derived', 'manual',"
        " '2026-01-02T00:00:00+00:00', 'user_set_status')"
    )
    conn.commit()
finally:
    conn.close()
`;

const SEED_TWO_STALE = `
import sys
from pathlib import Path
from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_link_with_confirmation, insert_source

db = sys.argv[1]
Path(db).touch()
conn = open_maintain_database(db)
try:
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type='Finding', statement='auth measured')
    insert_item(conn, source_id=source_id, item_id=7, item_type='Question', statement='should we cache tokens?', status_origin='manual')
    insert_item(conn, source_id=source_id, item_id=9, item_type='Question', statement='which auth backend?', status_origin='manual')
    insert_link_with_confirmation(conn, 1, 7, 'answers', created_at='2026-01-01T00:00:00+00:00')
    insert_link_with_confirmation(conn, 1, 9, 'answers', created_at='2026-01-01T00:00:00+00:00')
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (7, NULL, 'status_origin', 'derived', 'manual',"
        " '2026-01-02T00:00:00+00:00', 'user_set_status')"
    )
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (9, NULL, 'status_origin', 'derived', 'manual',"
        " '2026-01-02T00:00:00+00:00', 'user_set_status')"
    )
    conn.commit()
finally:
    conn.close()
`;

const SEED_CAP = `
import sys
from pathlib import Path
from ember.adapters.sqlite import open_maintain_database
from tests.fakes import insert_item, insert_link_with_confirmation, insert_source

db = sys.argv[1]
Path(db).touch()
conn = open_maintain_database(db)
try:
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=100, item_type='Finding', statement='answer source')
    for n in range(1, 12):
        insert_item(conn, source_id=source_id, item_id=n, item_type='Question',
                    statement=f'old question {n}', status_origin='manual')
        insert_link_with_confirmation(conn, 100, n, 'answers', created_at='2026-01-01T00:00:00+00:00')
        conn.execute(
            "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause)"
            f" VALUES ({n}, NULL, 'status_origin', 'derived', 'manual',"
            " '2026-01-02T00:00:00+00:00', 'user_set_status')"
        )
    conn.commit()
finally:
    conn.close()
`;

function seedKb(script, name) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `ember-e2e-cleanup-${name}-`));
  const dbPath = path.join(dir, 'kb.db');
  execFileSync(PYTHON, ['-c', script, dbPath], { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'inherit'] });
  return dbPath;
}

/** Read one item's live row through the real command (parity by eye of
  * the same door the app uses). */
async function itemRow(dbPath, id) {
  const { stdout } = await execFileP(EMBER, ['list-items', '--db', dbPath]);
  const doc = JSON.parse(stdout);
  return doc.items.find((it) => it.id === Number(id));
}

/* ---------- the shell ---------- */

async function launch({ kbPath, aiUrl = null, apiKey = null }) {
  const configDir = path.join(path.dirname(kbPath), 'config');
  const userData = path.join(configDir, 'ember-app');
  fs.mkdirSync(userData, { recursive: true });
  // The exact settings the store would write (schema 1).
  fs.writeFileSync(
    path.join(userData, 'settings.json'),
    `${JSON.stringify(
      {
        schema: 1,
        textSize: 'default',
        colourTheme: 'system',
        quickPopup: { shortcut: 'CommandOrControl+Alt+E', position: 'bottom-right' },
        menuOrder: ['add', 'lookup', 'link', 'fix', 'cleanup', 'keepsafe'],
        menuHidden: [],
        lastPane: 'cleanup',
        knowledgeBasePath: kbPath,
      },
      null,
      2,
    )}\n`,
  );
  const env = {
    ...process.env,
    XDG_CONFIG_HOME: configDir,
    EMBER_APP_COMMAND: EMBER,
    EMBER_APP_DB: kbPath,
  };
  if (aiUrl) env.EMBER_AI_BASE_URL = aiUrl;
  if (apiKey) env.EMBER_AI_API_KEY = apiKey;
  const app = await _electron.launch({ args: ['.'], cwd: APP_ROOT, env });
  const win = await app.firstWindow();
  await win.waitForSelector('[data-testid="pane-cleanup"]');
  return { app, win };
}

async function assertCleanScan(win, label) {
  const { runAccessibilityScan } = await import('../helpers/a11y-scan.mjs');
  const { violations, checked } = await runAccessibilityScan(win, {
    prepare: (page) => page.evaluate(() => document.documentElement.classList.add('big')),
    cleanup: (page) => page.evaluate(() => document.documentElement.classList.remove('big')),
  });
  if (violations.length > 0) {
    fail(`a11y scan on ${label} found ${violations.length}: ${JSON.stringify(violations, null, 2)}`);
  }
  process.stdout.write(`a11y scan clean on ${label} (${checked.tabbableCount} tabbable controls)\n`);
}

async function closeShell(shell, dir, ai = null) {
  await shell.app.close().catch(() => {});
  if (ai) await ai.close().catch(() => {});
  fs.rmSync(dir, { recursive: true, force: true });
}

async function badgeState(win) {
  const badge = win.locator('[data-testid="cleanup-badge"]');
  if ((await badge.count()) === 0) return { visible: false, text: '' };
  return { visible: await badge.isVisible(), text: (await badge.textContent()).trim() };
}

/* ---------- scenario 1: preview + apply, accept by keyboard ---------- */

async function acceptFlow() {
  process.stdout.write('--- clean up: preview + apply (accept) ---\n');
  const ai = await startFakeAiServer();
  const kbPath = seedKb(SEED_MIXED, 'accept');
  const shell = await launch({ kbPath, aiUrl: ai.url, apiKey: 'sk-or-v1-fake-key-e2e-only-0000000000' });
  try {
    const { win } = shell;

    // Story 65: Apply is off before a preview, and says why (103).
    const applyBtn = win.locator('[data-testid="cleanup-apply"]');
    if (!(await applyBtn.isDisabled())) fail('story 65: Apply must stay off before a preview');
    if (!/Preview the sweep first/.test((await applyBtn.getAttribute('title')) ?? '')) fail('story 103: the disabled Apply must say why');
    await assertCleanScan(win, 'Clean up, before any preview');

    // Story 64: the preview. The sweep is zero-AI: the fake server must
    // not have been called for the preview.
    await win.click('[data-action="cleanup-preview"]');
    await win.waitForSelector('[data-testid="cleanup-table"]');
    if (ai.calls.length !== 0) fail(`the preview must not call the AI, saw ${ai.calls.length} calls`);
    const row3 = await win.textContent('[data-testid="cleanup-row-3"]');
    if (!/Contradicted claim/.test(row3)) fail(`the preview row must name the item: ${row3}`);
    const marks = await win.locator('[data-testid="cleanup-move-3"] [data-testid^="status-pill-"]').count();
    if (marks !== 2) fail(`the Becomes cell needs the before → after heat marks, saw ${marks}`);
    if (!/a confirmed contradicts link/.test(row3)) fail(`the Because cell must name the rule: ${row3}`);
    const counts = await win.textContent('[data-testid="cleanup-counts"]');
    if (!/challenge 1 item/.test(counts)) fail(`the counts line must carry the engine summary: ${counts}`);
    if (!/1 old question that has an answer/.test(counts)) fail(`the stale summary must read in plain words: ${counts}`);
    const staleList = await win.textContent('[data-testid="cleanup-stale-list"]');
    if (!/Item 7 — should we cache tokens\?/.test(staleList)) fail(`the stale shortlist must be listed: ${staleList}`);

    // Story 66: Apply says how many changes. Story 68: the badge.
    if (!/Apply 1 change/.test((await applyBtn.textContent()) ?? '')) fail('story 66: the Apply label must say the count');
    const badge = await badgeState(win);
    if (!badge.visible || badge.text !== '1') fail(`story 68: the badge must show the pending 1, saw ${JSON.stringify(badge)}`);
    await assertCleanScan(win, 'Clean up, preview');

    // The loop: the REAL proposal block for item 7, in the pinned
    // order (Stop, Reject, Confirm — maintain has no Edit), answered
    // from the keyboard with the engine's own letter.
    await win.click('[data-testid="cleanup-apply"]');
    await win.waitForSelector('[data-testid="sweep-proposal"]');
    if (!/item 7 \[Question\]/.test(await win.textContent('[data-testid="sweep-proposal"]'))) {
      fail(`the proposal must name the stale question: ${await win.textContent('[data-testid="sweep-proposal"]')}`);
    }
    const judgment = await win.textContent('[data-testid="sweep-judgment"]');
    if (!/expired/.test(judgment) || !/0\.8/.test(judgment)) fail(`the proposal must carry the AI's judgment: ${judgment}`);
    const actions = await win.locator('[data-testid="sweep-proposal"] .actions button').allTextContents();
    const kinds = actions.map((t) => (t.startsWith('Stop') ? 'Stop' : t.startsWith('Reject') ? 'Reject' : t.startsWith('Confirm') ? 'Confirm' : 'other'));
    if (JSON.stringify(kinds) !== JSON.stringify(['Stop', 'Reject', 'Confirm'])) {
      fail(`the pinned order (Stop, Reject, Confirm; no Edit) is required, saw ${JSON.stringify(kinds)}`);
    }
    if (ai.calls.length !== 1) fail(`the loop must ask the AI once per candidate, saw ${ai.calls.length}`);
    await assertCleanScan(win, 'Clean up, the proposal loop');

    await win.keyboard.press('y');
    await win.waitForSelector('[data-testid="sweep-result-headline"]');

    // The final summary, the new heat marks, and the inline report
    // lines. The engine's document counts the SWEEP's changes; the
    // accepted close answers through its own outcome numbers and its
    // report line (D3: no number is recomputed in the app).
    const headline = await win.textContent('[data-testid="sweep-result-headline"]');
    if (!/Done\. 1 item was changed/.test(headline)) fail(`the result headline must carry the sweep's own count: ${headline}`);
    if (!/1 proposal made, 1 accepted, 0 declined/.test(headline)) fail(`the phase-5 outcome must be in the summary: ${headline}`);
    const messages = await win.textContent('[data-testid="sweep-result-messages"]');
    if (!/item 7: Active -> Closed/.test(messages)) fail(`the close report line must show as an inline message: ${messages}`);
    if (!/You confirmed the close for item 7/.test(messages)) fail(`the answer's own note must be in the transcript: ${messages}`);
    const now3 = await win.locator('[data-testid="cleanup-result-now-3"]').innerHTML();
    if (!/status-pill-challenged/.test(now3)) fail(`item 3's new heat mark must read Challenged: ${now3}`);
    // The badge refresh runs after the write (a new dry-run read), so
    // poll briefly: nothing is pending now, so it must hide.
    await win.waitForFunction(
      () => {
        const badge = document.querySelector('[data-testid="cleanup-badge"]');
        return !badge || badge.hidden;
      },
      undefined,
      { timeout: 20000 },
    );
    await assertCleanScan(win, 'Clean up, result');

    // The REAL database must say what the screen said.
    const row3db = await itemRow(kbPath, 3);
    if (row3db.status !== 'Challenged') fail(`item 3 must be Challenged in the database, saw ${row3db.status}`);
    const row7db = await itemRow(kbPath, 7);
    if (row7db.status !== 'Closed' || row7db.close_reason !== 'expired') {
      fail(`item 7 must be Closed(expired) in the database, saw ${row7db.status}/${row7db.close_reason}`);
    }
    process.stdout.write('accept flow OK: preview table, badge, loop from real events, result, database (stories 63-68)\n');

    // Reduce Motion honoured on this screen too (99/104).
    await win.emulateMedia({ reducedMotion: 'reduce' });
    await win.click('[data-action="cleanup-preview"]');
    await win.waitForSelector('[data-testid="cleanup-stale-cap"], [data-testid="cleanup-empty"], [data-testid="cleanup-counts"]', { timeout: 20000 });
    const animated = await win.evaluate(() =>
      [...document.querySelectorAll('svg, .skel')].filter((el) => {
        const name = getComputedStyle(el).animationName;
        return name !== 'none' && name !== '';
      }).length,
    );
    if (animated !== 0) fail(`Reduce Motion must leave nothing animating, saw ${animated}`);
    process.stdout.write('Reduce Motion honoured on Clean up\n');
  } finally {
    await closeShell(shell, path.dirname(kbPath), ai);
  }
}

/* ---------- scenario 2: the AI declines for one, the human rejects the other ---------- */

async function declineAndRejectFlow() {
  process.stdout.write('--- clean up: apply (decline, then reject) ---\n');
  // The fake AI declines for item 7 (close=false) and proposes for 9.
  const PROPOSE = JSON.stringify({ close: true, reason: 'expired', confidence: 0.8, rationale: 'answered long ago, no follow-up open' });
  const DECLINE = JSON.stringify({ close: false, confidence: 0.9, rationale: null });
  const ai = await startFakeAiServer({
    contentFor: (body) => (body.includes('Item 7 [Question]') ? DECLINE : PROPOSE),
  });
  const kbPath = seedKb(SEED_TWO_STALE, 'declinereject');
  const shell = await launch({ kbPath, aiUrl: ai.url, apiKey: 'sk-or-v1-fake-key-e2e-only-0000000000' });
  try {
    const { win } = shell;

    await win.click('[data-action="cleanup-preview"]');
    await win.waitForSelector('[data-testid="cleanup-stale-list"]');
    // Zero sweep changes: the calm empty message (69), but the stale
    // questions still wait for the apply run.
    const empty = await win.textContent('[data-testid="cleanup-empty"]');
    if (!/Nothing to update/.test(empty)) fail(`story 69: the calm message is required: ${empty}`);
    const list = await win.textContent('[data-testid="cleanup-stale-list"]');
    if (!/Item 7 — should we cache tokens\?/.test(list) || !/Item 9 — which auth backend\?/.test(list)) {
      fail(`both stale questions must be listed: ${list}`);
    }
    await assertCleanScan(win, 'Clean up, empty sweep with stale questions');

    await win.click('[data-testid="cleanup-apply"]');

    // The AI's decline arrives as a real close block with no prompt;
    // the screen says so and moves on.
    await win.waitForFunction(
      () => document.body.innerText.includes('Ember proposed no close for item 7'),
      undefined,
      { timeout: 15000 },
    );
    // The second candidate gets a real proposal; Reject by BUTTON.
    await win.waitForFunction(() => {
      const el = document.querySelector('[data-testid="sweep-proposal"]');
      return el && /item 9 \[Question\]/.test(el.textContent);
    }, undefined, { timeout: 15000 });
    await win.click('[data-testid="sweep-reject"]');
    await win.waitForSelector('[data-testid="sweep-result-headline"]');
    const headline = await win.textContent('[data-testid="sweep-result-headline"]');
    if (/Stopped\./.test(headline)) fail(`nothing was stopped here: ${headline}`);
    if (!/1 proposal made, 0 accepted, 1 declined/.test(headline)) {
      fail(`the outcome must count the rejection: ${headline}`);
    }
    const messages = await win.textContent('[data-testid="sweep-result-messages"]');
    if (!/Ember proposed no close for item 7/.test(messages)) fail(`the decline must be shown: ${messages}`);
    if (!/You declined the close for item 9/.test(messages)) fail(`the answer's own note must show: ${messages}`);
    if (ai.calls.length !== 2) fail(`one AI call per asked candidate, saw ${ai.calls.length}`);
    const row7db = await itemRow(kbPath, 7);
    if (row7db.status !== 'Active') fail(`a declined close writes nothing (item 7), saw ${row7db.status}`);
    const row9db = await itemRow(kbPath, 9);
    if (row9db.status !== 'Active') fail(`a rejected close writes nothing (item 9), saw ${row9db.status}`);
    process.stdout.write('decline + reject flow OK: the decline is shown, the reject writes nothing\n');
  } finally {
    await closeShell(shell, path.dirname(kbPath), ai);
  }
}

/* ---------- scenario 3: the cap note, and Stop = stop() ---------- */

async function capNoteFlow() {
  process.stdout.write('--- clean up: the stale shortlist cap note, and stop ---\n');
  const ai = await startFakeAiServer();
  const kbPath = seedKb(SEED_CAP, 'cap');
  const shell = await launch({ kbPath, aiUrl: ai.url, apiKey: 'sk-or-v1-fake-key-e2e-only-0000000000' });
  try {
    const { win } = shell;
    await win.click('[data-action="cleanup-preview"]');
    await win.waitForSelector('[data-testid="cleanup-stale-cap"]');
    const cap = await win.textContent('[data-testid="cleanup-stale-cap"]');
    if (!/capped at 10 questions in one sweep/.test(cap)) fail(`the cap note must tell the cap: ${cap}`);
    let listed = await win.locator('[data-testid="cleanup-stale-list"] li').count();
    if (listed !== 10) fail(`the capped shortlist lists 10 questions, saw ${listed}`);
    let badge = await badgeState(win);
    if (badge.visible) fail('with zero pending changes the badge must stay hidden (story 68)');
    const applyBtn = win.locator('[data-testid="cleanup-apply"]');
    if ((await applyBtn.textContent()).includes('Apply (no status changes)') === false) {
      fail(`with zero changes the label must say so plainly: ${await applyBtn.textContent()}`);
    }
    await assertCleanScan(win, 'Clean up, capped shortlist preview');

    // Apply, then STOP at the first proposal with Esc: stop() closes
    // the session's input; the engine reads that as a quit, asks no
    // more, and the summary says aborted.
    await win.click('[data-testid="cleanup-apply"]');
    await win.waitForSelector('[data-testid="sweep-proposal"]');
    await win.keyboard.press('Escape');
    await win.waitForSelector('[data-testid="sweep-result-headline"]');
    const headline = await win.textContent('[data-testid="sweep-result-headline"]');
    if (!/Stopped\./.test(headline)) fail(`a stopped sweep must say so: ${headline}`);
    if (!/1 proposal made, 0 accepted, 0 declined/.test(headline)) fail(`the stopped run asked one question: ${headline}`);
    if (ai.calls.length !== 1) fail(`a stopped loop never asks the rest, saw ${ai.calls.length} calls`);
    listed = 0;
    const row1 = await itemRow(kbPath, 1);
    if (row1.status !== 'Active') fail(`the stop must write nothing; item 1 saw ${row1.status}`);
    badge = await badgeState(win);
    if (badge.visible) fail('the stopped run wrote nothing, so the badge stays hidden');
    process.stdout.write('cap note + stop OK: 10 listed + the cap sentence, Esc = stop(), nothing written\n');
  } finally {
    await closeShell(shell, path.dirname(kbPath), ai);
  }
}

/* ---------- scenario 4: the loop without a key ---------- */

async function noKeyFlow() {
  process.stdout.write('--- clean up: apply without a key ---\n');
  const kbPath = seedKb(SEED_MIXED, 'nokey');
  const shell = await launch({ kbPath, aiUrl: null, apiKey: null });
  try {
    const { win } = shell;
    await win.click('[data-action="cleanup-preview"]');
    await win.waitForSelector('[data-testid="cleanup-table"]');
    // The preview never needs a key.
    await win.click('[data-testid="cleanup-apply"]');
    await win.waitForSelector('[data-testid="state-error"]');
    const errText = await win.evaluate(() => document.body.innerText);
    // The shared plain-sentence table's family fallback names the code
    // inside a full sentence (the step-03 wording); what must never
    // show is the RAW house line or a lone code with no words.
    if (/\| ember\./.test(errText) || /(MAINTAIN|APP|QUERY)-\d{3} \|/.test(errText)) {
      fail(`the raw error line must not reach the screen: ${errText.slice(0, 300)}`);
    }
    if (!/maintain engine \(the sweep\)/.test(errText)) fail(`the plain words must name the sweep's family: ${errText.slice(0, 300)}`);
    if (!/ledger/.test(errText)) fail(`the error must point at the ledger for what was already written: ${errText.slice(0, 300)}`);
    await win.click('[data-testid="state-error"] [data-action="show-details"]');
    const code = await win.textContent('[data-testid="error-code"]');
    if (!/MAINTAIN-020/.test(code)) fail(`the code behind Details must name the missing key, saw ${code}`);
    // The sweep changes written before the failed proposal loop are real.
    const row3db = await itemRow(kbPath, 3);
    if (row3db.status !== 'Challenged') fail(`the sweep change must be real even when the loop failed, saw ${row3db.status}`);
    await assertCleanScan(win, 'Clean up, apply failed (no key)');
    process.stdout.write('no-key flow OK: the error lives in the block, the applied change is real\n');
  } finally {
    await closeShell(shell, path.dirname(kbPath), null);
  }
}

/* ---------- main ---------- */

async function main() {
  if (process.platform !== 'linux') {
    process.stdout.write('e2e cleanup: Linux only (dev-only), skipped elsewhere\n');
    return;
  }
  await acceptFlow();
  await declineAndRejectFlow();
  await capNoteFlow();
  await noKeyFlow();
  process.stdout.write('e2e cleanup OK: all four scenarios green (real ember, real temp KB, fake AI server on EMBER_AI_BASE_URL)\n');
}

main().catch((err) => {
  process.stderr.write(`e2e cleanup FAILED: ${err.message}\n`);
  process.exit(1);
});

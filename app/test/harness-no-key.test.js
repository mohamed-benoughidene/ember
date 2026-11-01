'use strict';

/**
 * Decision I5, the automated half: no AI key may reach the launch-check
 * child. A recorder fake engine (EMBER_TEST_ENGINE) runs in place of the
 * real venv `ember`, dumps the whole child environment to a file, and
 * this test reads that dump back: neither sentinel key may appear among
 * the child's env names, and XDG_CONFIG_HOME must sit inside the
 * check's own `ember-launch-check-` work folder, never `~/.config`.
 *
 * The real launch check still fails the harness itself on a surviving
 * key (Chunk 6's guard) — the recording proves what actually reached
 * the child, not only what the harness thought it passed on.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const APP_ROOT = path.join(__dirname, '..');
const SENTINEL = 'sk-or-v1-SENTINEL-NEVER-SPEND';

// The fake engine: argv[2] is the dump file (EMBER_TEST_ENGINE is a
// space-split argv prefix, ember-command.js). It records the env names
// plus the XDG_CONFIG_HOME value, answers the launch check's one read
// command with a `total: 1` list-items document (the app prints the
// forwarded `items: 1` line from it), and exits 0.
const RECORDER = `'use strict';
const fs = require('node:fs');
fs.writeFileSync(process.argv[2], JSON.stringify({
  names: Object.keys(process.env).sort(),
  xdgConfigHome: process.env.XDG_CONFIG_HOME || null,
}, null, 2));
process.stdout.write(JSON.stringify({ total: 1, items: [] }) + '\\n');
process.exit(0);
`;

test('no AI key reaches the launch-check child — a recording fake engine proves the environment', { timeout: 180_000 }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-no-key-'));
  const dumpFile = path.join(dir, 'child-env.json');
  const recorder = path.join(dir, 'recorder-engine.js');
  fs.writeFileSync(recorder, RECORDER);
  try {
    const run = spawnSync(process.execPath, [path.join(__dirname, 'launch-check.js')], {
      cwd: APP_ROOT,
      encoding: 'utf8',
      timeout: 120_000, // the check itself gives its child 90 s
      env: {
        ...process.env,
        EMBER_AI_API_KEY: SENTINEL,
        OPENROUTER_API_KEY: SENTINEL,
        EMBER_TEST_ENGINE: `node ${recorder} ${dumpFile}`,
      },
    });
    assert.equal(run.status, 0, `launch-check exited ${run.status}: ${run.stderr}`);

    const okLine = run.stdout.split('\n').find((l) => l.startsWith('check:launch OK'));
    assert.ok(okLine, `no OK line on stdout: ${JSON.stringify(run.stdout.slice(0, 300))}`);
    const configDir = okLine.split('config: ')[1];
    assert.ok(configDir, `OK line names no config dir: ${JSON.stringify(okLine)}`);
    // Under the suite run TMPDIR is /tmp/opencode/batch0, so the OK
    // line must name a temp path there — never ~/.config.
    assert.ok(configDir.startsWith(os.tmpdir()), `config dir is not under the temp dir: ${configDir}`);
    assert.ok(configDir.includes('ember-launch-check-'), `config dir is not the check's own work folder: ${configDir}`);
    assert.ok(!configDir.startsWith(os.homedir()), `config dir leaks the home config: ${configDir}`);

    assert.ok(fs.existsSync(dumpFile), 'the recorder never ran: no env dump file (is the EMBER_TEST_ENGINE hook in launch-check.js?)');
    const dump = JSON.parse(fs.readFileSync(dumpFile, 'utf8'));
    assert.equal(
      dump.names.filter((name) => name === 'EMBER_AI_API_KEY' || name === 'OPENROUTER_API_KEY').length,
      0,
      `an AI key reached the launch-check child: ${JSON.stringify(dump.names.filter((n) => n.includes('API_KEY')))}`,
    );
    assert.ok(dump.xdgConfigHome, 'the child saw no XDG_CONFIG_HOME at all');
    assert.ok(
      path.dirname(dump.xdgConfigHome).includes('ember-launch-check-'),
      `XDG_CONFIG_HOME is not inside the check's own work folder: ${dump.xdgConfigHome}`,
    );
    assert.ok(!dump.xdgConfigHome.startsWith(os.homedir()), `XDG_CONFIG_HOME leaks the real home config: ${dump.xdgConfigHome}`);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

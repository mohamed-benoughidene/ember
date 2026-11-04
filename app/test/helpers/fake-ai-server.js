'use strict';

/**
 * A tiny local OpenAI-compatible chat-completions server for tests
 * (ticket A37). It answers POST /v1/chat/completions with ONE canned
 * completion, so the real `ember` child exercises its real AI adapter
 * against `EMBER_AI_BASE_URL` without any network use. It records every
 * request it saw (path + authorization presence, never the key value).
 *
 * Used by the cleanup contract test and the cleanup E2E — the same
 * pattern the Python bridge tests use at the same seam.
 */

const http = require('node:http');
const { once } = require('node:events');

/**
 * @param {object} [options]
 * @param {string} [options.content] the assistant text to answer with
 *   (defaults to the canned close proposal the stale-question loop
 *   judges: close=true, reason expired, confidence 0.8)
 * @param {(requestBody: string) => string} [options.contentFor] a
 *   per-request choice (e.g. decline for one item, propose for
 *   another); overrides `content` when given
 * @returns {Promise<{server: import('node:http').Server, calls: object[], url: string, close: () => Promise<void>}>}
 */
async function startFakeAiServer({ content, contentFor } = {}) {
  const answer =
    content ??
    JSON.stringify({
      close: true,
      reason: 'expired',
      confidence: 0.8,
      rationale: 'answered long ago, no follow-up open',
    });
  const calls = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      calls.push({
        path: req.url,
        hasAuth: Boolean(req.headers.authorization),
        body,
        retryCount: req.headers['x-stainless-retry-count'] ?? null,
      });
      const answerText = typeof contentFor === 'function' ? contentFor(body) : answer;
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          id: 'chatcmpl-fake-ember',
          object: 'chat.completion',
          created: 0,
          model: 'fake-model',
          choices: [
            {
              index: 0,
              message: { role: 'assistant', content: answerText },
              finish_reason: 'stop',
            },
          ],
          usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
        }),
      );
    });
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = server.address().port;
  return {
    server,
    calls,
    url: `http://127.0.0.1:${port}/v1`,
    close: () => new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve()))),
  };
}

module.exports = { startFakeAiServer };

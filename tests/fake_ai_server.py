"""A localhost-only fake OpenAI chat-completions server for CLI tests.

The Python-side twin of `app/test/helpers/fake-ai-server.js` (the JS side of
report 4.5): tests point the real `ember` AI adapter at it through
`EMBER_AI_BASE_URL`, so the CLI exercises its real provider code path with no
network use and no real key. It binds 127.0.0.1 on an ephemeral port and is
never exposed beyond the machine.

Modes (Batch 7 Chunk 15):

* `"normal"` — every request gets 200 with the saved answer fixture (or the
  `content` override), the OpenAI chat-completions shape;
* `"429"` — every request gets 429 with a `Retry-After` header, so the ONE
  retry policy in the adapters runs for real (`count_429` caps how many
  requests see the 429 before a normal answer — set it high to answer 429
  forever, 0 to answer at once);
* `"hang"` — the connection is accepted and never answered (for the skipped
  slow-provider test, Chunk 16).

Every request is recorded with one monotonic arrival time, so a test can
measure the wait BETWEEN two arrivals (the retry sleep it cannot see inside
the process).
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from pathlib import Path
from types import TracebackType

RETRY_AFTER_DEFAULT_SECONDS = 1.0

_FIXTURE = Path(__file__).parent / "fixtures" / "ai_responses" / "case_01.response.json"

_COMPLETION_BODY = {
    "id": "chatcmpl-fake-ember",
    "object": "chat.completion",
    "created": 0,
    "model": "fake-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": ""},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


class FakeAiServer:
    """The running fake server. `calls` records one entry per request."""

    def __init__(self, httpd: http.server.ThreadingHTTPServer, url: str) -> None:
        self._httpd = httpd
        self.url = url
        # One entry per request: {"arrival": <monotonic s>, "path": <str>}.
        self.calls: list[dict[str, object]] = httpd.calls  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()

    def __enter__(self) -> "FakeAiServer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Stop the server. A `"hang"` handler thread stays blocked — it is
        a daemon thread and dies with the test process."""
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


def start_fake_ai_server(
    *,
    mode: str = "normal",
    count_429: int | None = None,
    retry_after: float = RETRY_AFTER_DEFAULT_SECONDS,
    content: str | None = None,
) -> FakeAiServer:
    """Start the fake on 127.0.0.1 port 0 and return its handle.

    `mode`: `"normal"` answers 200 at once; `"429"` answers 429 with the
    `Retry-After` header (always when `count_429` is None, for the first
    `count_429` requests otherwise, then 200); `"hang"` accepts the request
    and never answers. `content` overrides the answered assistant text
    (defaults to the saved answer fixture).
    """
    if mode not in ("normal", "429", "hang"):
        raise ValueError(f"unknown fake AI server mode: {mode!r}")
    answer = content if content is not None else _FIXTURE.read_text(encoding="utf-8")
    calls: list[dict[str, object]] = []
    lock = threading.Lock()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server naming
            length = int(self.headers.get("content-length") or 0)
            self.rfile.read(length)
            with lock:
                calls.append({"arrival": time.monotonic(), "path": self.path})

            if mode == "hang":
                threading.Event().wait()  # never answered
                return

            answered_429 = mode == "429" and (
                count_429 is None or len(calls) <= count_429
            )
            if answered_429:
                body = json.dumps(
                    {
                        "error": {
                            "message": "rate limited by the fake provider",
                            "type": "rate_limit_error",
                        }
                    }
                ).encode("utf-8")
                self.send_response(429)
                self.send_header("Retry-After", str(retry_after))
            else:
                completion = dict(_COMPLETION_BODY)
                completion["choices"] = [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ]
                body = json.dumps(completion).encode("utf-8")
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # keep the test output clean

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.calls = calls  # type: ignore[attr-defined]  # the shared requests log
    return FakeAiServer(httpd, f"http://127.0.0.1:{httpd.server_address[1]}/v1")

# Batch 7: AI calls and input limits

**Source:** `archive/Plan.md` Batch 7. Decision D-23. Findings from `archive/Problems.md`.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch7.md`). Decisions N18, N19, N20, N21, B7-D5 applied 2026-11-01. Not yet published.

## Problem Statement

- **Retries without backoff.** A rate-limit reply triggers an instant second call, which usually fails the same way and spends money. The constitution requires backoff.
- **Timeouts longer than the app waits.** The engine's worst case is 120 s with no output. The app gives up at 120 s, so a hung provider shows as the app's timeout, never the engine's.
- **Unbounded input.** Stdin has no 5 MB cap. Empty files still cost an AI call. A title can be empty.
- **Weak grounding and prompts.** A proposal's quote of `"a"` counts as grounded. The note goes into the prompt with no delimiter. Relate and maintain classify every prompt as a choice prompt, so a drifted prompt would be choice-parsed in silence.
- **Relate limits.** Graph and label candidates have no cap, so a busy project overflows the prompt. A wrong-length cached vector blocks relate forever. The vector cache has no format tag. Query and cache vectors use different float sizes. A cold cache with no network waits 120 s and leaves its loader thread running. Timeout values of 0 or less are accepted.
- **Test gaps.** No test pins the AI base URL for capture and relate. The real AI path has no CI coverage, and that is not written down.

## Solution

- AI calls retry with exponential backoff and jitter, honor the provider's retry-after, and stop after a fixed limit.
- Rate limiting and timeouts get their own error codes in every family that calls AI (capture, relate, maintain), so the one-sentence lookup can tell them apart.
- The engine's total AI time budget is below the app's idle limit, so the engine always reports its own timeout.
- Input is capped and validated before any AI call.
- Grounding needs a meaningful quote. The note is clearly delimited in the prompt. Choices are parsed only from the three documented prompt constants; any other prompt is kind "unknown" and fails loudly.
- Relate caps total candidates, repairs bad cached vectors, tags the cache format, and fails fast offline.

## User Stories

1. As a user, I want a rate-limited call to wait before retrying, so that I'm not charged for a call that will fail.
2. As a user, I want retries to stop after a fixed number and to end in the engine's own rate-limit code (a distinct code per calling family), so that a broken provider can't run up costs silently.
3. As a user, I want a slow provider reported as the engine's own AI-timeout code (a distinct code per calling family), so that I know it was the provider, not Ember or the app.
4. As a user, I want pasted text over 5 MB refused before any AI call, so that I don't pay for a huge request.
5. As a user, I want an empty file refused before any AI call, so that I don't pay for nothing.
6. As a user, I want a note's title taken from its first non-blank line, so that titles are never empty.
7. As a user, I want proposed items to quote my note meaningfully, so that "grounded" means something.
8. As a user, I want my note clearly separated from instructions in the prompt, so that text in my note can't steer the AI.
9. As the founder, I want choices parsed only from the documented prompt constants, so that a drifted or future prompt fails loudly instead of being choice-parsed in silence.
10. As a user, I want Link items to work in a busy project, so that many labeled items don't overflow the request.
11. As a user, I want a damaged cached vector repaired automatically, so that "Try again" actually works.
12. As a user, I want relate results stable between runs, so that the same data gives the same suggestions.
13. As a user, I want relate to fail fast when the model isn't available offline, so that I don't wait two minutes for nothing.
14. As a user, I want a model change to keep the cache when there's nothing to relate, so that no work is wasted.
15. As the founder, I want capture to send a fixed temperature, so that proposals are repeatable.
16. As the founder, I want invalid timeout settings refused at startup, so that a 0 or negative value can't break loading.
17. As the founder, I want the cache to record its vector format, so that a future format change can't decode wrongly.
18. As a contributor, I want tests that pin the AI base URL for capture and relate, so that a wrong endpoint fails a test.
19. As a contributor, I want it written down that real AI calls are not tested in CI, so that nobody assumes they are.

## Implementation Decisions

### AI calls
- One retry policy in the AI adapter: at most 2 attempts, exponential backoff with jitter, honoring retry-after up to a cap. Used by capture, relate and maintain.
- New, distinct codes for "AI rate-limited" and "AI timed out" in each family that calls AI (capture, relate, maintain), replacing today's habit of one generic AI-failure code with the HTTP status and exception name riding along as attributes. Each new code gets exactly one sentence in Batch 6's sentence table.
- One total time budget per AI call, retries included, below the app's idle limit for that command. The budget and the idle limit are written in one documented place both sides test against. [Assumption: budget 90 s for capture against the app's 120 s. Wrong if: real calls need longer, in which case the app limit rises instead.]
- Capture sends temperature 0. [Assumption. Wrong if: the founder wants variety in proposals.]
- The note is wrapped in clear delimiters, and the instructions say text inside them is data.

### Input
- Stdin gets the same 5 MB cap as `--file`. Oversized stdin is refused with the existing `CAPTURE` "too large" code (`SourceTooLarge`). Empty input is refused before any AI call with a new capture code; its sentence goes in Batch 6's table.
- Title is the first non-blank line, cut to 80 characters.
- Grounding requires a quote of at least a minimum length (proposed: 3 words) found in the note.
- Choices are parsed only from the three documented PROMPT constants in capture's, relate's and maintain's confirm writers. Any other prompt is kind "unknown" and fails loudly (capture already does this; relate and maintain adopt the same pattern, so a prompt change shows as drift until the constant is registered).

### Relate
- Total candidates are capped. Order: dense similarity first, then graph, then labels. [Assumption: cap 40. Wrong if: the prompt fits more.]
- A cached vector the relate engine cannot use is deleted and recomputed. That is both a blob that does not decode (today `RELATE-037` from `sqlite.py:2108-2111`) and one of the wrong length (today `RELATE-022` from `candidate_pool.py:131-138`); neither path deletes the row today.
- New optional cache column for vector format (constitution: new optional fields over renames). Missing means today's format.
- The query vector is packed and unpacked through the cache's float32 format before scoring, so query and cache vectors always compare at the same precision. No schema change; this floats-only round-trip is separate from the cache-format tag above.
- Offline mode with no cached model fails at once with the model-missing code: the embedder checks the local model cache before the load starts, and a missing model means the load never starts.
- Timeout settings must be positive, checked at startup.
- The model-change wipe runs after the empty-universe check.

### Tests and docs
- Adapter tests assert the base URL for capture and relate.
- The test docs state live AI tests are skipped without a key and are not in CI.

## Testing Decisions

**Good tests here** use a fake provider and saved reply fixtures, and assert codes, call counts seen by the fake, and timing bounds. Never exact AI wording (constitution).

**Seams (D-23):** the `ember` CLI on temp databases with a fake provider server.
1. Fake returns 429 twice: the second request arrives after a wait, then the engine gives the calling family's rate-limit code — a distinct code, not the generic AI-failure code plus a status attribute.
2. Fake hangs: the engine's own AI-timeout code (distinct, in the calling family) arrives before the app's idle limit.
3. 6 MB stdin and an empty file: refused, fake receives no request. Oversized stdin is refused with the existing too-large code; empty input with the new empty-input capture code.
4. Proposal with a one-letter quote: rejected as ungrounded.
5. 300 labeled items: the fake receives at most the cap.
6. A wrong-length cached vector: relate succeeds and the row is rewritten.
7. Offline with no model: model-missing code within seconds, before any load attempt starts.

**Prior art:** the local fake OpenAI server the review used for capture (report 4.5). `tests/test_llm_adapter_unit.py`.

## Out of Scope

- Relate batching and progress (Batch 8).
- An AI quality benchmark set (constitution rule on AI evaluation). Worth its own plan item later.
- The sentences for this batch's new codes (rate-limited, timed out in capture/relate/maintain; empty input in capture) and what the app does with the "unknown" prompt kind: these are decided and written in Batch 6's code-keyed sentence table (D-08). This batch only adds the codes.

## Further Notes

- **Open question (answered 2026-11-01, from the code check): the app's idle limits per command.** They live in the app layer, not the engine:
  - One-shot read commands (`list-items`, `show-item`, `current-state`, `topic-search`, `why`, `history`, `db-check`): 30 s hard timeout with at most one automatic retry (`bridge-client.js:136` and the `READ_COMMANDS` set at `:52-60`).
  - The one-shot write `capture-source`: 120 s, never retried (`bridge-client.js:137`, `WRITE_COMMANDS` at `:68`).
  - Confirm sessions (`capture`, `relate`, `maintain`): inactivity limit 120 s default (`bridge-client.js:138`); `capture` and `maintain` use the shared client, which sets no override (`ipc.js:127-135`). Plus `sessionPromptWaitMs` 30 min while a user prompt sits unanswered (`bridge-client.js:139`).
  - `relate` is the exception: a dedicated client with a 10-minute inactivity limit (`relate-session.js:50`, applied by `ipc.js:708-713`), because a first model download may sit silent for minutes.
  - Engine side, for comparison: AI request timeout 60 s, at most 2 attempts (`llm.py:43`, retry in the engine core), so capture's silent worst case is 120 s — the same number as the app's capture idle limit, which is why a hung provider today reads as the app's `APP-008`. Model load timeout 120 s default (`embedder.py:27`).
  - "One documented place both sides test against" therefore has these exact numbers to capture; none of them live in a doc file today.

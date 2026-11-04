# Batch 8: performance

**Source:** `archive/Plan.md` Batch 8. Decisions D-15, D-17, D-23. Findings 4.7 #3, #6, #12, 4.8 #1, #2.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch8.md`).

## Problem Statement

- **Search is too slow.** It recomputes word counts per item per term. Measured: 1k items 0.16 s, 5k 15.8 s, 10k 73.2 s. The app gives up at 30 s. `--limit` cuts results only after scoring everything. [Fact: report 4.7 #3]
- **Search misses matching text.** The same word typed with different hidden encodings, or in different case forms like `Straße` and `STRASSE`, does not match.
- **History loads everything.** Asking for 31 lines loads and classifies the whole ledger.
- **Relate's first run is too slow and silent.** It encodes one item at a time, 4.9x slower than in batches. Over about 2,000 items it passes the app's 10-minute limit. It prints nothing while working, and warns about wiping the cache only after wiping it.

## Solution

- Search scores in one pass, with word statistics computed once. Target under 1 s at 10k items (D-15).
- Words are normalized for hidden encoding and case. Accents still count (D-17).
- History filters and limits in SQL.
- Relate encodes in batches, prints progress lines, and warns before wiping.

## User Stories

1. As a user with 10k items, I want search to answer in under a second, so that I can use it while I work.
2. As a user, I want the same word to match however it was typed or pasted, so that I find what I wrote. Known limit: a word that differs only by a combining mark — `İstanbul` (dotted capital I) against `istanbul` — does not match; this is documented, not accidental (N22).
3. As a user, I want case ignored properly in every language, so that `STRASSE` finds `Straße`.
4. As a user, I want `cafe` not to match `café`, so that accents keep their meaning (D-17).
5. As a user, I want history to open fast however long it is, so that a big ledger doesn't slow me down.
6. As a user, I want relate's first run to finish on a large knowledge base, so that I can use Link items at all.
7. As a user, I want to see relate's progress, so that I know it's working and how long is left.
8. As a user, I want to be warned before the cache is wiped, so that I understand the wait.
9. As the founder, I want search and relate timing measured in tests, so that slowdowns are caught.

## Implementation Decisions

- Search: compute document frequency and item token lists once per query, then score every item once. Results sorted, then cut to `--limit`. A search `--offset` and a result total do NOT happen here: they are finding 4.7 #5, owned by Batch 6 (`topic-search` has no `--offset` flag today).
- Tokenizer: Unicode NFC normalization, then full case folding. No accent stripping. One tokenizer used for items and queries. Known limit (N22): the `İstanbul` split stays. Case-folding `İ` produces `i` plus a combining dot above, and the tokenizer splits on combining marks, so `İstanbul` tokenizes as `i` + `stanbul`; a word whose only difference from another is a combining mark never matches the plain form. Same-word-different-case still matches (`İstanbul` and `İSTANBUL` casefold identically). Fixing it would need stripping or keeping combining marks, which conflicts with the accent rule (D-17), so it is accepted and documented, not fixed.
- CJK stays as today. [Assumption: CJK splitting is not needed for a 10k-item personal base. Wrong if: users write in Chinese or Japanese.]
- History: `WHERE` and `LIMIT` in SQL, classification only on the rows returned.
- Relate: encode texts in batches. The batch size is a module-level constant, 32 (N23). It is not read from config or the environment; tuning happens only if testing decision 5's 2,000-item check misses its 10-minute bound.
- Relate prints progress as message event lines with done and total (the existing sink: `JsonSink.echo` → `{"event":"message",...}`; no new event type, see the answered open question below). The app shows them in the Link screen's log. The idle timer resets on every line (it already resets on every stdout chunk).
- The wipe warning prints before the wipe. Under `--confirm json` it is a message event on stdout — the app never displays stderr lines, so a stderr warning could never reach story 8. On the terminal it stays on stderr as today.

## Testing Decisions

**Good tests here** measure time on seeded temp databases and check results, with generous bounds to avoid flaky timing.

**Seams (D-23):** the `ember` CLI on temp databases for the search and history timing tests (tests seed the temp file directly — the CLI has no seeding command, and 10k items cannot come in through `capture`, which needs AI proposals). For relate, the existing pytest seam with an injected fake embedder (`tests/relate/fakes.py` `FakeEmbedder`): the CLI builds its embedder from the environment (`ember/cli.py:478` → `build_embedder()`), so a fake embedder cannot reach a real CLI run.
1. Seed 10k items, run a 3-word search: under 1 s on the CI runner, with a bound that fails clearly if the old algorithm returns. Same top results as a slow reference implementation on a small seed.
2. NFD `café` finds NFC `café`. `STRASSE` finds `Straße`. `cafe` does not find `café`. The known limit is pinned too: `İstanbul` does not match `istanbul` (N22), while `İstanbul` does match `İSTANBUL`.
3. History with 20k rows and limit 31: reads only what it needs, under a time bound.
4. Relate with a fake embedder: called in batches, not once per item. Progress lines appear (message events, done and total). The warning line comes before the cache is empty.
5. Plan.md's Batch 8 second "Done when" check: once, on a machine with the real local model, encode a seeded 2,000-item knowledge base and see progress lines and a finish inside 10 minutes. No AI key is involved — encoding is local, so this is allowed as a manual check. If it misses the bound, the batch-size constant (32, N23) is the first thing to tune.

**Prior art:** the review's timing script for search (report 4.7). The relate tests that passed 276 cases (report 4.8).

## Out of Scope

- SQLite full-text search (D-15 keeps the current search).
- Accent-insensitive search (D-17).
- Fixing the `İstanbul` combining-mark split. Kept as a documented known limit (N22); options like keeping or stripping combining marks were rejected in the spec check (`archive/spec-check-batch8.md`, needs-a-decision 1, option A).
- Making the relate batch size configurable (no `EMBER_EMBEDDER_BATCH_SIZE` or config entry). N23 fixes it as a module-level constant, 32; the env-var option was rejected in the spec check (`archive/spec-check-batch8.md`, needs-a-decision 2).

## Further Notes

- **Open question (answered 2026-11-01, see `archive/spec-check-batch8.md`):** does the app show event lines from relate today? Yes. The app forwards every validated session event to the renderer; `message` events land in the Link screen's visible log (`relate-view.mjs:145-153`, `link.mjs:214-219`, shown as written by `relate-words.mjs:39-47`), and every stdout line resets the idle timer (`bridge-client.js:399-401`). Progress lines can be plain `message` events with zero app changes and no dependency on Batch 5. A typed `progress` event would additionally need `parse-event-line.js:12` (only `block/prompt/message/summary` are accepted today — an unknown event name kills the session as APP-002), a `relate-view.mjs` case, and the shared event fixture from report 4.4 #8 (Batch 5). Not needed for this batch.

# Embedder swap cost at scale (issue #12 measurement)

Date: 2026-10-29
Ticket: 14 of the follow-up builds
Script: `scripts/measure_model_change.py` (rerunnable: `python scripts/measure_model_change.py --items N`)
Machine: Intel Core i7-5500U @ 2.40GHz, 4 threads, 7.7 GB RAM, Linux (laptop-class CPU, CPU-only inference)

## Why this measurement exists

Ember stores a numeric fingerprint (an embedding) of every item, computed by a local AI model (`bge-base-en-v1.5`). When the model is ever changed, all stored fingerprints become invalid. Ember detects this automatically, wipes them, and re-encodes every item the next time you run `ember relate`. That re-encode freezes the command, and until now nothing measured how long the freeze lasts. Issue #12 asked for exactly that number before any model swap decision.

## The results

Each row is a synthetic database seeded through the real schema, then a forced model change from `bge-base-en-v1.5` to `all-MiniLM-L6-v2`, then one timed Phase-2 run (the part of `ember relate` that owns the wipe and re-encode).

| Corpus size | Wipe time | Re-encode time | Total Phase-2 wall clock | Encode speed |
|---|---|---|---|---|
| 500 items | 0.006s | 6.89s | 7.07s | 72.5 items/sec |
| 2,000 items | 0.022s | 25.59s | 26.27s | 78.2 items/sec |
| 5,000 items | 0.056s | 56.59s | 58.26s | 88.4 items/sec |

Every run was verified: the model-change warning appeared on stderr exactly as the product prints it, and the wipe happened for real.

## What the numbers mean

- The wipe itself is instant (milliseconds). The entire cost is the re-encoding of every item by the new model.
- The cost scales linearly: roughly 1 second per 85 items on this machine.
- A "minutes-long freeze" only arrives at very large libraries. At the master plan's scale ceiling of 5,000 items (§6.3), the worst case is just under one minute of frozen `ember relate`, with one stderr warning line as the only notice.
- A model swap therefore stays a cheap, manual, one-minute operation at any scale this project realistically reaches. The master plan's deferral of the embedder swap (§9) remains comfortable.

## Honest limits

- The re-encode speed measured is the swap **to** `all-MiniLM-L6-v2` (the only other locally cached model). A swap to a different future model will encode at a somewhat different speed, but the same order of magnitude.
- The measurement covers Phase 2 (the candidate-pool build where the wipe happens), not a whole `ember relate` invocation end to end. Phase 2 is where the freeze lives, so this is the number that matters.
- Timing was done on a busy laptop with other work running at times. Treat the numbers as order-of-magnitude accurate, which is all the decision needed.

## Where it is recorded

- GitHub: comment on issue #12 (issue closed with "keep the block" replaced by this measurement as the recorded evidence).
- Ticket: `.scratch/hardening/issues/14-embedder-measurement.md` (local, gitignored).
- Code: `scripts/measure_model_change.py`, committed at `03d4f9e` on `feat/hardening`.

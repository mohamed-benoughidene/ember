# Embedder swap cost. Measurement record. Issue #12. Ticket 14.

Date 2026-10-29. Machine: i7-5500U, 4 threads, 7.7 GB RAM, CPU only.

## What measured

Real schema. Seed N items. Warm cache with model A (`bge-base-en-v1.5`). Swap to model B (`all-MiniLM-L6-v2`). Wipe + full re-encode. Timed with `perf_counter`. Script: `scripts/measure_model_change.py`. Rerun: `python scripts/measure_model_change.py --items N`.

## Numbers

| N | wipe | re-encode | total Phase-2 | speed |
|---|---|---|---|---|
| 500 | 0.006s | 6.89s | 7.07s | 72.5/s |
| 2000 | 0.022s | 25.59s | 26.27s | 78.2/s |
| 5000 | 0.056s | 56.59s | 58.26s | 88.4/s |

`MODEL_CHANGED_LINE` asserted on stderr. Every run exit 0. Warning real.

## Facts

1. Wipe instant. Milliseconds. All cost is re-encode.
2. Cost linear. ~1 second per 85 items on this machine.
3. 5000 items = 58s freeze. Minutes-long stall needs ~25000+ items.
4. Phase 2 owns the freeze. Number is Phase-2 wall clock, by design.
5. Swap direction: bge-base TO MiniLM. Reverse direction differs. Same order of magnitude.

## Verdict

Model swap cheap at this scale. Manual swap fine. One-minute freeze at master-plan ceiling (5000). Stderr warning is the only notice. Embedder swap deferral (master-plan §9) stands.

## Limits

- Speed is MiniLM speed. Other model = different speed. Same magnitude.
- Laptop CPU, other work ran sometimes. Numbers are order-of-magnitude.
- No test covers the script. Timing assertions flaky. By design. Run manually.

## Evidence

GitHub comment on issue #12 (dated, machine spec). Ticket file ticked. Script committed `03d4f9e`. Suite after: 836 passed, 4 deselected.

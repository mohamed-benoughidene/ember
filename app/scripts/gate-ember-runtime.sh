#!/usr/bin/env bash
# The RUNTIME GATE as its own script (Batch 1, decision N1).
#
# What it does: the same proof the build script's gate block runs
# (build-ember-runtime.sh:174-202) — the packed program must do the two
# things the app's first run needs — migrate a fresh file, and fail
# HONESTLY on a missing key. The F1 crash (a ModuleNotFoundError
# traceback on every capture: the migrations package missing from the
# bundle) must be impossible to ship again.
#
# Usage:
#   bash gate-ember-runtime.sh <runtime-folder>
#
# The checks (TIGHTER than the old build gate):
#  1. no-key capture on a fresh temp file. The env has EVERY AI key
#     variable removed, so the gate can never make a real AI call.
#     A healthy bundle exits 1 with EXACTLY ONE stderr line starting
#     "error: CAPTURE-008" (the one honest house line) — never a second
#     line (the old gate swallowed those at :186-189), never another
#     "error: ..." code, never a traceback.
#  2. db-check on the SAME file: the capture migrated it before the key
#     check, so it must end 0 and report "version: 13" and
#     "result: OK".
#
# Failure behavior (finding 4.1 #20): on ANY failure the FULL error is
# printed (no 200-byte cut at :184/:191) and the gate log folder is
# KEPT for reading afterward; the temp files are removed only when the
# gate PASSES.
#
# Scratch rule (same as the build script: :68-75): the scratch is
# created NEXT TO the runtime folder (same disk), never in /tmp, which
# on many systems is a small tmpfs. The tests point the runtime at a
# folder on the normal scratch disk, so the gate logs follow it.

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "error: CAPTURE-008 gate | gate-ember-runtime | exactly one argument needed: the runtime folder (usage: gate-ember-runtime.sh <runtime-folder>)" >&2
  exit 1
fi

RUNTIME="$1"

if [ ! -d "$RUNTIME" ]; then
  echo "error: CAPTURE-008 gate | gate-ember-runtime | no runtime folder at $RUNTIME — build it first (build-ember-runtime.sh) or fix the path" >&2
  exit 1
fi

if [ ! -x "$RUNTIME/ember" ]; then
  echo "error: CAPTURE-008 gate | gate-ember-runtime | no executable ember at $RUNTIME/ember" >&2
  exit 1
fi

# The scratch: next to the runtime (same disk rule as the build), and
# it IS the gate log folder — kept on failure, removed only on success.
SCRATCH="$(mktemp -d "$(cd "$RUNTIME/.." && pwd)/gate-ember-runtime-XXXXXX")"

GATE_NOTE="$SCRATCH/gate-note.txt"
GATE_KB="$SCRATCH/gate.kb"
printf 'The gate note: setup sticks because the hinge is loose.' > "$GATE_NOTE"

# Print the FULL content of a gate output file and fail (the old gate
# cut every error at 200 bytes; the full text is what you debug from).
gate_fail() { # $1 = reason, $2 = file whose FULL contents follow
  echo "gate-ember-runtime FAILED: $1" >&2
  if [ -n "${2:-}" ] && [ -f "$2" ]; then
    echo "--- full output ($2) ---" >&2
    cat "$2" >&2
  fi
  echo "gate log folder kept for reading: $SCRATCH" >&2
  exit 1
}

# == check 1: no-key capture → exit 1, EXACTLY ONE stderr line,
# starting "error: CAPTURE-008" =====================================
set +e
env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY \
  "$RUNTIME/ember" capture --format json --confirm json --file "$GATE_NOTE" --db "$GATE_KB" \
  > "$SCRATCH/gate-capture.out" 2> "$SCRATCH/gate-capture.err"
CAPTURE_RC=$?
set -e

if [ "$CAPTURE_RC" -ne 1 ]; then
  gate_fail "the gate capture must end 1 (key missing) on a healthy bundle; got $CAPTURE_RC" "$SCRATCH/gate-capture.err"
fi

ERR_LINES="$(grep -c '' "$SCRATCH/gate-capture.err" || true)"
if [ "$ERR_LINES" -ne 1 ]; then
  gate_fail "the gate capture must print EXACTLY ONE stderr line (the honest no-key line); got $ERR_LINES lines" "$SCRATCH/gate-capture.err"
fi

FIRST_ERR="$(head -n1 "$SCRATCH/gate-capture.err")"
case "$FIRST_ERR" in
  "error: CAPTURE-008"*) : ;; # the one honest house line, by code
  *) gate_fail "the gate capture's one stderr line must start 'error: CAPTURE-008' (a traceback or another code means the bundle is broken): $FIRST_ERR" "$SCRATCH/gate-capture.err" ;;
esac

# == check 2: db-check on the SAME file → version 13, result OK ======
set +e
env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY \
  "$RUNTIME/ember" db-check --db "$GATE_KB" --format json \
  > "$SCRATCH/gate-dbcheck.out" 2> "$SCRATCH/gate-dbcheck.err"
DBCHECK_RC=$?
set -e

if [ "$DBCHECK_RC" -ne 0 ]; then
  gate_fail "the gate db-check must end 0 (the capture migrated the file); got $DBCHECK_RC" "$SCRATCH/gate-dbcheck.err"
fi

DBCHECK_JSON="$(cat "$SCRATCH/gate-dbcheck.out")"
case "$DBCHECK_JSON" in
  *'"version: 13"'*) : ;;
  *) gate_fail "the gate db-check must report the file migrated to version 13; its lines were:" "$SCRATCH/gate-dbcheck.out" ;;
esac
case "$DBCHECK_JSON" in
  *'"result: OK"'*) : ;;
  *) gate_fail "the gate db-check must end 'result: OK'; its lines were:" "$SCRATCH/gate-dbcheck.out" ;;
esac

# PASSED: clean the temp files. On any failure above they (and the
# full logs) stay inside $SCRATCH — gone only after a green gate.
rm -f "$GATE_NOTE" "$GATE_KB" "$GATE_KB".bak-v*
rm -rf "$SCRATCH"

echo "gate capture: exit 1, one line ok ($FIRST_ERR)"
echo "gate db-check: version 13, result OK"
echo "gate PASSED: $RUNTIME"

#!/usr/bin/env bash
# Build the BUNDLED Ember runtime (app step 13, decision 3-B).
#
# What it makes: a PyInstaller ONEDIR build of the real Ember CLI with
# the optional relate embedder INCLUDED (sentence-transformers +
# torch from the CPU index), plus the model weights copied into the
# bundle so `relate` never downloads anything (story 107).
#
# Why ONEDIR and not the spike's ONEFILE: the spike measured a 20 MB
# onefile binary of the BASE CLI (no embedder). With torch inside, a
# onefile build would re-extract ~1.4 GB to a temp folder on EVERY
# command start (~1 s overhead per child, often hundreds per day).
# An onedir build starts as fast as the venv and lives as one folder.
#
# Env (all optional):
#   EMBER_PACK_VENV    the venv with ember + the embedder + pyinstaller.
#                      NEVER install pyinstaller into the maintainer's
#                      real venv — make a copy (AGENTS.md §2).
#                      Default: the repo's .venv (fails if it lacks
#                      pyinstaller, with instructions).
#   EMBER_RUNTIME_OUT  output folder. Default: app/dist/ember-runtime.
#   EMBER_MODEL_CACHE  a Hugging Face hub cache that already holds the
#                      `BAAI/bge-base-en-v1.5` weights (hub/ layout).
#                      Copied to <runtime>/models/hub. Without it the
#                      bundle ships WITHOUT weights and the first
#                      `relate` would download them (story 45).
#
# HARD RULES (plan §3 decision 3): the torch wheel MUST come from the
# CPU index (https://download.pytorch.org/whl/cpu). Plain PyPI pulls
# multi-GB CUDA wheels — the spike's hard note. This script installs
# nothing; it only checks what the venv already has and refuses loudly
# when a CUDA build is present.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_ROOT/.." && pwd)"

PACK_VENV="${EMBER_PACK_VENV:-$REPO_ROOT/.venv}"
RUNTIME_OUT="${EMBER_RUNTIME_OUT:-$APP_ROOT/dist/ember-runtime}"
MODEL_CACHE="${EMBER_MODEL_CACHE:-}" # empty = no weights copied
MODEL_ID="BAAI/bge-base-en-v1.5"     # ember's own default (ember/adapters/embedder.py)

PY="$PACK_VENV/bin/python"
fail() { echo "build-ember-runtime FAILED: $*" >&2; exit 1; }

if [ -n "$MODEL_CACHE" ]; then
  MODEL_CACHE="$(realpath -m "$MODEL_CACHE")" # canonical form; -m creates nothing
fi

# Refuse bad output paths BEFORE anything is created (stories 14, 15;
# findings 4.1 #7, #8): the multi-GB scratch is made NEXT TO this path
# and the old $RUNTIME_OUT is REMOVED at swap time, so a sloppy path
# must never reach those lines.
case "$RUNTIME_OUT" in
  "") fail "EMBER_RUNTIME_OUT is empty - set it to an absolute folder path" ;;
  /*) : ;; # absolute - the only safe form
  *) fail "EMBER_RUNTIME_OUT must be an ABSOLUTE path (got '$RUNTIME_OUT'): a relative path would drop the multi-GB build scratch wherever the script happens to run" ;;
esac
RUNTIME_OUT="$(realpath -m "$RUNTIME_OUT")" # canonical form; -m creates nothing
case "$RUNTIME_OUT" in
  "/")
    fail "EMBER_RUNTIME_OUT = / is unsafe - the build deletes and replaces this folder at the end; use a dedicated folder, never the root" ;;
  "$REPO_ROOT"|"$APP_ROOT")
    fail "EMBER_RUNTIME_OUT = $RUNTIME_OUT is unsafe - it must be a dedicated folder, not the repo itself (the build deletes and replaces it at the end)" ;;
esac

[ -x "$PY" ] || fail "no python at $PY (set EMBER_PACK_VENV to a venv with ember + the embedder + pyinstaller)"

check_pkg() { "$PY" -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" || fail "the pack venv is missing $2 (install it into EMBER_PACK_VENV, never into the maintainer's real venv)"; }
check_pkg setuptools "setuptools (pyinstaller needs it)"
check_pkg ember "the ember package (pip install -e <repo>)"
check_pkg torch "torch from the CPU index (--index-url https://download.pytorch.org/whl/cpu)"
check_pkg sentence_transformers "sentence-transformers"
check_pkg PyInstaller "pyinstaller"

# Refuse a CUDA torch: decision 3-B says CPU only (the spike measured
# plain-PyPI torch pulling multi-GB CUDA wheel sets).
"$PY" - <<'EOF' || exit 1
import torch, sys
ver = getattr(torch, "__version__", "")
if "+cpu" not in ver and "+cu" not in ver:
    print(f"torch {ver}: no +cpu/+cu tag, assuming a CPU build — continuing")
elif "+cu" in ver:
    sys.exit(f"build-ember-runtime FAILED: the pack venv has a CUDA torch ({ver}); decision 3-B needs the CPU build")
EOF

# Refuse a weightless / FOREIGN model cache BEFORE the 20-minute
# PyInstaller step and BEFORE the old runtime is removed (story 13):
# when EMBER_MODEL_CACHE is set it must already hold THIS model's
# weights, or the bundle would ship without them and the first
# `relate` would download gigabytes on the user's machine (story 45).
HUB_SRC=""
if [ -n "$MODEL_CACHE" ]; then
  # Accept both hub-cache layouts: <cache>/hub/models--... (HF_HOME-style)
  # or <cache>/models--... (snapshot_download's cache_dir is the hub dir).
  HUB_SRC="$MODEL_CACHE/hub"
  [ -d "$HUB_SRC" ] || HUB_SRC="$MODEL_CACHE"
  MODEL_TREE="$HUB_SRC/${MODEL_ID//\//--}" # models--BAAI--bge-base-en-v1.5
  if [ ! -d "$MODEL_TREE" ] || [ -z "$(find "$MODEL_TREE" -name model.safetensors -print -quit)" ]; then
    fail "EMBER_MODEL_CACHE holds no '$MODEL_ID' weights (looked for $MODEL_TREE with a model.safetensors under it) - a weightless cache would ship a bundle that downloads the weights itself on first use"
  fi
fi

# NOTE: the build needs several GB of scratch (torch alone is ~1.5 GB
# installed) — the scratch is created NEXT TO the output (same disk),
# never in /tmp, which on many systems is a small tmpfs.

echo "== pyinstaller: the ONEDIR Ember runtime (this can take minutes with torch) =="
mkdir -p "$(dirname "$RUNTIME_OUT")"
BUILD_DIR="$(mktemp -d "$(dirname "$RUNTIME_OUT")/build-ember-runtime-XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
cat > "$BUILD_DIR/entry.py" <<'EOF'
# The frozen CLI entry: the same call the installed `ember` script makes.
import sys
from ember.cli import main
sys.exit(main())
EOF

cd "$REPO_ROOT"
# Fix F1: collect-all ember ALONE shipped no ember.adapters.migrations.
# The pack venv's ember is an EDITABLE install (the code lives in the
# repo, not in site-packages), and the packer's data-file collector
# cannot see an editable package's .sql sheets; the module itself also
# needed naming. So: name the module (hidden-import) AND copy the .sql
# files into the bundle by hand (add-data); the F1 build gate below
# fails the build if either is missing again. The destination
# 'ember/adapters/migrations' is the in-bundle path _migration_scripts
# reads via importlib.resources.
"$PACK_VENV/bin/pyinstaller" \
  --distpath "$BUILD_DIR/dist" \
  --workpath "$BUILD_DIR/work" \
  --specpath "$BUILD_DIR" \
  --noconfirm --clean \
  --onedir \
  --name ember-runtime \
  --paths "$REPO_ROOT" \
  --collect-all torch \
  --collect-all transformers \
  --collect-all sentence_transformers \
  --collect-all tokenizers \
  --collect-all safetensors \
  --collect-all huggingface_hub \
  --collect-all ember \
  --hidden-import ember.adapters.migrations \
  --add-data "$REPO_ROOT/ember/adapters/migrations:ember/adapters/migrations" \
  "$BUILD_DIR/entry.py"

rm -rf "$RUNTIME_OUT"
mkdir -p "$(dirname "$RUNTIME_OUT")"
mv "$BUILD_DIR/dist/ember-runtime" "$RUNTIME_OUT"
# The COLLECT puts the executable under the ONEDIR folder named after
# --name; the app's layout wants `<ember-runtime>/ember` (one name on
# every platform, see app/main/ember-command.js bundleLayout).
mv "$RUNTIME_OUT/ember-runtime" "$RUNTIME_OUT/ember" 2>/dev/null || mv "$RUNTIME_OUT/ember-runtime.exe" "$RUNTIME_OUT/ember.exe"

echo "== the bundle carries the model weights (no first-run download, story 107) =="
if [ -n "$MODEL_CACHE" ]; then
  # HUB_SRC was resolved and the weights were checked BEFORE PyInstaller
  # (story 13): a cache without the '$MODEL_ID' weights never gets this
  # far, so the bare "any models--* tree" grep is gone.
  mkdir -p "$RUNTIME_OUT/models"
  cp -r "$HUB_SRC" "$RUNTIME_OUT/models/hub"
  # Trim duplicate weight formats from the COPY (the staging cache keeps
  # everything): sentence-transformers/transformers load
  # model.safetensors; pytorch_model.bin and onnx/ are dead weight (~800
  # MB) in every install. Then KEEP exactly the blobs the snapshot
  # symlinks still name (the hub cache also carries sha-named blob
  # links that would otherwise resurrect everything).
  find "$RUNTIME_OUT/models/hub" \( -name 'pytorch_model.bin' -o -type d -name 'onnx*' \) -exec rm -rf {} + 2>/dev/null || true
  hub="$RUNTIME_OUT/models/hub"
  refs="$(find "$hub" -type l -path '*snapshots/*' -exec realpath {} \; | sort -u)"
  cd "$hub"
  while IFS= read -r link; do
    rp="$(realpath "$link")" || continue
    echo "$refs" | grep -qxF "$rp" || rm -f "$link"
  done < <(find . -type l ! -path '*snapshots/*')
  while IFS= read -r blob; do
    rp="$(realpath "$blob")" || continue
    echo "$refs" | grep -qxF "$rp" || rm -f "$blob"
  done < <(find blobs -type f)
  find . -empty -type d -delete
  rm -rf .locks
  cd "$REPO_ROOT"
  echo "weights in bundle: $(du -sm "$RUNTIME_OUT/models/hub" | cut -f1) MB"
else
  echo "NO weights copied (EMBER_MODEL_CACHE unset) — a first `relate` would download them"
fi

# Base smoke: the frozen CLI answers --help with NO venv and NO repo
# source on the path (spike check 1b, mechanism proven there for the
# base 20 MB build; here the same proof for the with-embedder build).
cd /
"$RUNTIME_OUT/ember" --help > /dev/null || fail "the frozen runtime does not run standalone"
"$RUNTIME_OUT/ember" --version > /dev/null || true

# == THE BUILD GATE (fix F1, founder order): the packed program must do
# the two things the app's first run needs — migrate a fresh file, and
# fail HONESTLY on a missing key. The F1 crash (a ModuleNotFoundError
# traceback on every capture: the migrations package missing from the
# bundle) must be impossible to ship again.
#
#  1. no-key capture on a fresh temp file. The env has EVERY AI key
#     variable removed, so the gate can never make a real AI call. A
#     healthy bundle exits 1 with ONE normal house line on stderr
#     ("error: CAPTURE-008 ... ai api key missing") — never a traceback.
#  2. db-check on the SAME file: the capture migrated it before the key
#     check, so it must print "version: 13" and "result: OK".
echo "== the build gate: the packed program must really work (fix F1) =="
GATE_NOTE="$BUILD_DIR/gate-note.txt"
GATE_KB="$BUILD_DIR/gate.kb"
printf 'The gate note: setup sticks because the hinge is loose.' > "$GATE_NOTE"
set +e
env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY \
  "$RUNTIME_OUT/ember" capture --format json --confirm json --file "$GATE_NOTE" --db "$GATE_KB" \
  > "$BUILD_DIR/gate-capture.out" 2> "$BUILD_DIR/gate-capture.err"
CAPTURE_RC=$?
set -e
[ "$CAPTURE_RC" -eq 1 ] || fail "the gate capture must end 1 (key missing) on a healthy bundle; got $CAPTURE_RC (stderr: $(head -c 200 "$BUILD_DIR/gate-capture.err"))"
FIRST_ERR="$(head -n1 "$BUILD_DIR/gate-capture.err")"
case "$FIRST_ERR" in
  "error: "*) : ;;  # the one honest house line
  *) fail "the gate capture's first stderr line must start 'error: ' (a Python traceback here means the F1 bug again): $FIRST_ERR" ;;
esac
DBCHECK_JSON="$("$RUNTIME_OUT/ember" db-check --db "$GATE_KB" --format json 2> "$BUILD_DIR/gate-dbcheck.err")" \
  || fail "the gate db-check must end 0 (the capture migrated the file); got: $(head -c 200 "$BUILD_DIR/gate-dbcheck.err")"
case "$DBCHECK_JSON" in
  *'"version: 13"'*) : ;;
  *) fail "the gate db-check must report the file migrated to version 13; its lines were: $(echo "$DBCHECK_JSON" | head -c 300)" ;;
esac
case "$DBCHECK_JSON" in
  *'"result: OK"'*) : ;;
  *) fail "the gate db-check must end 'result: OK'; its lines were: $(echo "$DBCHECK_JSON" | head -c 300)" ;;
esac
rm -f "$GATE_NOTE" "$GATE_KB" "$GATE_KB".bak-v*
echo "gate capture: exit 1, first line ok ($FIRST_ERR)"
echo "gate db-check: version 13, result OK"

echo "== sizes =="
du -sm "$RUNTIME_OUT" "$RUNTIME_OUT/_internal/torch" ${MODEL_CACHE:+"$RUNTIME_OUT/models"} 2>/dev/null || \
  du -sm "$RUNTIME_OUT" "$RUNTIME_OUT/_internal/torch"
echo "ember runtime ready at $RUNTIME_OUT"

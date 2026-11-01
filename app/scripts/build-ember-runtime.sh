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
  MODEL_TREE="$HUB_SRC/models--${MODEL_ID//\//--}" # models--BAAI--bge-base-en-v1.5
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
# files into the bundle by hand (add-data); the build gate below
# (gate-ember-runtime.sh) fails the build if either is missing again.
# The destination
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

# The new runtime tree is built and GATED ENTIRELY INSIDE the scratch
# dir (stories 11, 12, 21): $RUNTIME_OUT — the OLD runtime — is touched
# only after the new tree has passed the gate. A failed build of any
# kind (smoke, gate) leaves the old runtime untouched.
NEW_RUNTIME="$BUILD_DIR/dist/ember-runtime"
# The COLLECT puts the executable under the ONEDIR folder named after
# --name; the app's layout wants `<ember-runtime>/ember` (one name on
# every platform, see app/main/ember-command.js bundleLayout).
mv "$NEW_RUNTIME/ember-runtime" "$NEW_RUNTIME/ember" 2>/dev/null || mv "$NEW_RUNTIME/ember-runtime.exe" "$NEW_RUNTIME/ember.exe"

echo "== the bundle carries the model weights (no first-run download, story 107) =="
if [ -n "$MODEL_CACHE" ]; then
  # HUB_SRC was resolved and the weights were checked BEFORE PyInstaller
  # (story 13): a cache without the '$MODEL_ID' weights never gets this
  # far, so the bare "any models--* tree" grep is gone. The weights are
  # copied INTO THE SCRATCH TREE; they move with it on the swap below.
  mkdir -p "$NEW_RUNTIME/models"
  cp -r "$HUB_SRC" "$NEW_RUNTIME/models/hub"
  # Trim duplicate weight formats from the COPY (the staging cache keeps
  # everything): sentence-transformers/transformers load
  # model.safetensors; pytorch_model.bin and onnx/ are dead weight (~800
  # MB) in every install. Then KEEP exactly the blobs the snapshot
  # symlinks still name (the hub cache also carries sha-named blob
  # links that would otherwise resurrect everything).
  find "$NEW_RUNTIME/models/hub" \( -name 'pytorch_model.bin' -o -type d -name 'onnx*' \) -exec rm -rf {} + 2>/dev/null || true
  hub="$NEW_RUNTIME/models/hub"
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
  echo "weights in bundle: $(du -sm "$NEW_RUNTIME/models/hub" | cut -f1) MB"
else
  echo "NO weights copied (EMBER_MODEL_CACHE unset) — a first `relate` would download them"
fi

# Base smoke on the NEW tree while it is still in the scratch: the
# frozen CLI answers --help with NO venv and NO repo source on the path
# (spike check 1b). The --version smoke is now a REAL call (it exists
# since Batch 1 chunk 1; finding 4.1 #9): no more `|| true`, and both
# calls run BEFORE the swap, so a smoke failure also leaves the old
# runtime untouched.
cd /
"$NEW_RUNTIME/ember" --help > /dev/null || fail "the frozen runtime does not run standalone"
"$NEW_RUNTIME/ember" --version > /dev/null || fail "the frozen runtime answers no --version (the one engine source is broken in the bundle)"

# == THE BUILD GATE, as its own script (decision N1): the packed
# program must do the two things the app's first run needs — migrate a
# fresh file, and fail HONESTLY on a missing key. It runs on the NEW
# tree in the scratch (story 21); a failed gate never touches the old
# runtime (story 11).
echo "== the build gate: the packed program must really work (fix F1) =="
bash "$SCRIPT_DIR/gate-ember-runtime.sh" "$NEW_RUNTIME"

# The gate-passed marker (story 12: the pack refuses a runtime without
# it) is written ONLY now — after the gate PASSED — so a marker can
# never exist on a runtime the gate refused.
printf 'gate passed (build-ember-runtime.sh)\n' > "$NEW_RUNTIME/.gate-ok"

echo "== swap: only now may the old runtime be replaced (story 11) =="
rm -rf "$RUNTIME_OUT"
mv "$NEW_RUNTIME" "$RUNTIME_OUT"

echo "== sizes =="
du -sm "$RUNTIME_OUT" "$RUNTIME_OUT/_internal/torch" ${MODEL_CACHE:+"$RUNTIME_OUT/models"} 2>/dev/null || \
  du -sm "$RUNTIME_OUT" "$RUNTIME_OUT/_internal/torch"
echo "ember runtime ready at $RUNTIME_OUT"

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
  # Accept both hub-cache layouts: <cache>/hub/models--... (HF_HOME-style)
  # or <cache>/models--... (snapshot_download's cache_dir is the hub dir).
  HUB_SRC="$MODEL_CACHE/hub"
  [ -d "$HUB_SRC" ] || HUB_SRC="$MODEL_CACHE"
  ls "$HUB_SRC" | grep -q "^models--" || fail "EMBER_MODEL_CACHE holds no models--* tree: $MODEL_CACHE"
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

echo "== sizes =="
du -sm "$RUNTIME_OUT" "$RUNTIME_OUT/_internal/torch" ${MODEL_CACHE:+"$RUNTIME_OUT/models"} 2>/dev/null || \
  du -sm "$RUNTIME_OUT" "$RUNTIME_OUT/_internal/torch"
echo "ember runtime ready at $RUNTIME_OUT"

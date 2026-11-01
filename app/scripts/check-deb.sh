#!/bin/bash
# check-deb.sh — the .deb check script (Batch 1 Chunk 10; D-11, D-12, D-21; I12).
#
#   bash app/scripts/check-deb.sh <path/to/package.deb> [release-folder]
#
# ONE argument: a .deb package to check (runs alone on any .deb — S1; this
# script is NOT part of CI, D-11: it exists to gate real release artifacts
# on the packer machine, and Chunk 11 wires it after `dpkg-deb --build`).
#
# What it refuses (listed in a dated report, every offending item named):
#   - a symlink whose target leaves the package — ANY absolute target
#     (e.g. /usr/lib/... or a build-box path like /home/mo/...); every
#     library is bundled (I12), so a link back to a system path is a bug,
#   - any world-writable REGULAR file (other-write bit set),
#   - no .sql migrations at the runtime's migrations path
#     (opt/ember/app/ember-runtime/_internal/ember/adapters/migrations/),
#   - no model.safetensors under the model hub
#     (opt/ember/app/ember-runtime/models/hub/),
#   - control Architecture other than amd64 (Debian-only for V1).
#
# Save policy:
#   - PASS: the .deb + a dated report are saved into the release folder
#     (default app/dist/release/, gitignored — everything under dist/ is),
#     and only the newest 3 .debs (+ their reports) are kept (D-21),
#   - FAIL: the dated report is saved, the .deb is NEVER saved (D-12),
#     and the exit code is non-zero.
#
# The checks read the package in place (`dpkg-deb --info` + `--contents`
# with real mode parsing) — the checked .deb is never modified.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# The two content paths inside the package (the layout pack.js produces).
MIGRATIONS_PREFIX='./opt/ember/app/ember-runtime/_internal/ember/adapters/migrations/'
HUB_PREFIX='./opt/ember/app/ember-runtime/models/hub/'

DEB="${1:-}"
if [ -z "$DEB" ]; then
  echo "usage: check-deb.sh <path/to/package.deb> [release-folder]" >&2
  exit 2
fi
if [ ! -f "$DEB" ]; then
  echo "check-deb: no such .deb: $DEB" >&2
  exit 2
fi

# The release folder is an input (argument 2, or EMBER_RELEASE_DIR) so tests
# never write into the real app/dist/release.
RELEASE_DIR="${2:-${EMBER_RELEASE_DIR:-"$APP_ROOT/dist/release"}}"
mkdir -p "$RELEASE_DIR"

DEB_ABS="$(readlink -f "$DEB")"
STEM="$(basename "$DEB_ABS" .deb)"
STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
REPORT="$RELEASE_DIR/$STEM.$STAMP.report.txt"

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/check-deb.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

CONTENTS="$SCRATCH/contents.txt"
PROBLEMS="$SCRATCH/problems.txt"
CONTROL_INFO="$SCRATCH/control-info.txt"
: > "$PROBLEMS"

dpkg-deb --contents "$DEB_ABS" > "$CONTENTS"
dpkg-deb --info "$DEB_ABS" > "$CONTROL_INFO" 2>/dev/null || true

# Strip the 5 dpkg-deb --contents header fields (mode, owner, size, date,
# time) in one regex; what stays is the archive path (+ " -> target").
# ` +[^ ]+ ` skips any run of spaces, so padded size columns parse too.
STRIP5='^[^ ]+ +[^ ]+ +[^ ]+ +[^ ]+ +[^ ]+ +'

# --- rule: every symlink target must stay inside the package (I12) ---
# An absolute target (/usr/lib/..., /home/mo/...) always leaves the package.
# A relative target is resolved against the link's folder and refused when
# it climbs above the package root.
awk -v strip5="$STRIP5" '
  function strip(line) { sub(strip5, "", line); return line }
  $1 ~ /^l/ {
    line = strip($0)
    sep = index(line, " -> ")
    if (sep == 0) next
    path = substr(line, 1, sep - 1)
    target = substr(line, sep + 4)
    if (substr(target, 1, 1) == "/") {
      print "symlink target is an absolute path (every library is bundled; the target must live inside the package): " line
      next
    }
    n = split(path, pc, "/")
    depth = 0
    for (i = 1; i < n; i++) if (pc[i] != ".") depth++
    m = split(target, tc, "/")
    escaped = 0
    for (i = 1; i <= m; i++) {
      if (tc[i] == "" || tc[i] == ".") continue
      if (tc[i] == "..") { depth--; if (depth < 0) { escaped = 1; break } }
      else depth++
    }
    if (escaped) print "symlink target leaves the package: " line
  }
' "$CONTENTS" >> "$PROBLEMS"

# --- rule: no world-writable regular file ---
# chars of $1: 1 = type, 2-4 owner, 5-7 group, 8-10 other. Regular file =
# first char '-'; world-writable = char 9 (the other-write bit) is 'w'.
awk -v strip5="$STRIP5" '
  function strip(line) { sub(strip5, "", line); return line }
  $1 ~ /^-/ && substr($1, 9, 1) == "w" {
    print "world-writable regular file (mode " $1 "): " strip($0)
  }
' "$CONTENTS" >> "$PROBLEMS"

# --- rule: the migrations .sql files must be at the runtime's path ---
SQL_COUNT="$(awk -v want="${MIGRATIONS_PREFIX#./}" '
  $1 ~ /^-/ && $NF ~ /\.sql$/ && index($0, "./" want) { n++ }
  END { print n + 0 }
' "$CONTENTS")"

# --- rule: model.safetensors must exist under models/hub ---
MODEL_COUNT="$(awk -v want="${HUB_PREFIX#./}" '
  {
    line = $0
    sub(/^[^ ]+ +[^ ]+ +[^ ]+ +[^ ]+ +[^ ]+ +/, "", line)
    sep = index(line, " -> ")
    if (sep != 0) line = substr(line, 1, sep - 1)   # judge the link, not its target
    if (line ~ "./" want) {
      n = split(line, pc, "/")
      if (pc[n] == "model.safetensors") c++
    }
  }
  END { print c + 0 }
' "$CONTENTS")"

# --- rule: control Architecture must be amd64 ---
ARCH="$(dpkg-deb -f "$DEB_ABS" Architecture || true)"
if [ "$ARCH" != "amd64" ]; then
  echo "control Architecture is '${ARCH:-missing}', this package must be amd64" >> "$PROBLEMS"
fi
if [ "$SQL_COUNT" -eq 0 ]; then
  echo "no .sql migrations at ${MIGRATIONS_PREFIX#./} (the bundled runtime cannot create the knowledge base)" >> "$PROBLEMS"
fi
if [ "$MODEL_COUNT" -eq 0 ]; then
  echo "no model.safetensors under ${HUB_PREFIX#./} (relate would download on the user's machine)" >> "$PROBLEMS"
fi

# The report is written for EVERY check, pass or fail (dated, next to the
# check's saved outcome in the release folder).
write_report() {
  local verdict="$1"
  {
    echo "check-deb report"
    echo "date (UTC): $(date -u '+%Y-%m-%d %H:%M:%SZ')"
    echo "verdict: $verdict"
    echo "package: $DEB_ABS"
    echo ""
    echo "--- dpkg-deb --info ---"
    cat "$CONTROL_INFO"
    echo ""
    if [ -s "$PROBLEMS" ]; then
      echo "--- refused items ---"
      cat "$PROBLEMS"
    else
      echo "--- refused items ---"
      echo "(none; migrations .sql found: $SQL_COUNT; model.safetensors found: $MODEL_COUNT)"
    fi
  } > "$REPORT"
}

if [ -s "$PROBLEMS" ]; then
  # FAIL: report saved, .deb never saved (D-12), non-zero exit.
  write_report FAIL
  echo "check-deb: FAILED for $DEB_ABS"
  while IFS= read -r problem; do echo "check-deb: refused: $problem"; done < "$PROBLEMS"
  echo "check-deb: $(grep -c . "$PROBLEMS") refusal(s); report: $REPORT (the .deb was NOT saved)"
  exit 1
fi

# PASS: save the .deb + report into the release folder (D-12/D-21).
DEB_BASENAME="$(basename "$DEB_ABS")"
if [ "$DEB_ABS" != "$(readlink -f "$RELEASE_DIR/$DEB_BASENAME" 2>/dev/null || true)" ]; then
  cp -f "$DEB_ABS" "$RELEASE_DIR/$DEB_BASENAME"
fi
write_report PASS

# --- retention: keep only the newest 3 builds (D-21) ---
REMOVED=""
while IFS= read -r old_deb; do
  old_stem="$(basename "$old_deb" .deb)"
  rm -f "$old_deb"
  rm -f "$RELEASE_DIR/$old_stem".*.report.txt
  REMOVED="$REMOVED $(basename "$old_deb")"
done < <(find "$RELEASE_DIR" -maxdepth 1 -name '*.deb' -printf '%T@\t%p\n' \
          | sort -rn \
          | tail -n +4 \
          | cut -f2-)

KEPT_COUNT="$(find "$RELEASE_DIR" -maxdepth 1 -name '*.deb' | wc -l)"
echo "check-deb: PASS for $DEB_ABS"
echo "check-deb: saved $DEB_BASENAME + report $REPORT into $RELEASE_DIR"
if [ -n "$REMOVED" ]; then
  echo "check-deb: retention removed:$REMOVED (D-21: keep the newest 3)"
fi
echo "check-deb: $KEPT_COUNT build(s) in the release folder"
exit 0

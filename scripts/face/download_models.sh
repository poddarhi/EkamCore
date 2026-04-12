#!/usr/bin/env bash
# Download + verify the InsightFace buffalo_l pack (S11-005 / ART-15 §4).
#
# Invoked by `make download-face-models` from the repo root.
#
# Guarantees:
#   1. Refuses to run if any hash in CHECKSUMS.txt starts with
#      PLACEHOLDER_ (fail-closed default).
#   2. Downloads buffalo_l.zip from the official InsightFace release.
#   3. Verifies the zip SHA-256 against CHECKSUMS.txt BEFORE unzipping.
#   4. Unzips into infra/docker/workers/models/insightface/buffalo_l/.
#   5. Verifies each .onnx SHA-256 individually.
#   6. On ANY failure: deletes partial artifacts and exits non-zero.
#
# Flags:
#   --verify-only   Skip download; just re-verify hashes of files already
#                   on disk. Exits 0 if all pass, 1 if any mismatch.
#
# Network: the script assumes curl is available and the host can reach
# github.com. If you are air-gapped, download the zip manually, place
# it at infra/docker/workers/models/insightface/buffalo_l.zip, then run
# with --verify-only.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL_DIR="${REPO_ROOT}/infra/docker/workers/models/insightface"
ZIP_PATH="${MODEL_DIR}/buffalo_l.zip"
UNZIP_DIR="${MODEL_DIR}/buffalo_l"
CHECKSUMS_FILE="${MODEL_DIR}/CHECKSUMS.txt"

# Official release URL. When bumping to a newer pack, also update the
# hashes in CHECKSUMS.txt.
BUFFALO_L_URL="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"

VERIFY_ONLY=0
if [[ "${1:-}" == "--verify-only" ]]; then
  VERIFY_ONLY=1
fi

log() { printf '[download-face-models] %s\n' "$*"; }
err() { printf '[download-face-models] ERROR: %s\n' "$*" >&2; }

# ── 0. Sanity: CHECKSUMS.txt exists and has no placeholders ─────────────
if [[ ! -f "${CHECKSUMS_FILE}" ]]; then
  err "Missing ${CHECKSUMS_FILE}. Cannot verify integrity — aborting."
  exit 1
fi

if grep -q 'PLACEHOLDER_' "${CHECKSUMS_FILE}"; then
  err "CHECKSUMS.txt still contains PLACEHOLDER_ entries."
  err "Populate real SHA-256 hashes from the v0.7 release before running"
  err "this script. See ${CHECKSUMS_FILE} for the format."
  exit 1
fi

# Pick the right sha256 tool
if command -v sha256sum >/dev/null 2>&1; then
  SHA256_CMD="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SHA256_CMD="shasum -a 256"
else
  err "Neither sha256sum nor shasum is installed. Install coreutils or use macOS shasum."
  exit 1
fi

# Extract expected-hash for a given relative path
expected_hash_for() {
  local rel_path="$1"
  # Lines are: <hash>  <path>   (ignore # comments and blanks)
  awk -v p="${rel_path}" '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    { gsub(/^[[:space:]]+/, "", $0); hash=$1; path=$NF; if (path == p) { print hash; exit } }
  ' "${CHECKSUMS_FILE}"
}

# Verify a single file against CHECKSUMS.txt
verify_file() {
  local rel_path="$1"
  local abs_path="${MODEL_DIR}/${rel_path}"
  local expected actual

  expected="$(expected_hash_for "${rel_path}")"
  if [[ -z "${expected}" ]]; then
    err "No expected hash in CHECKSUMS.txt for ${rel_path}"
    return 1
  fi

  if [[ ! -f "${abs_path}" ]]; then
    err "Missing file: ${abs_path}"
    return 1
  fi

  actual="$(${SHA256_CMD} "${abs_path}" | awk '{print $1}')"
  if [[ "${actual}" != "${expected}" ]]; then
    err "Hash mismatch for ${rel_path}:"
    err "  expected: ${expected}"
    err "  actual:   ${actual}"
    return 1
  fi

  log "  ok  ${rel_path}"
  return 0
}

EXPECTED_FILES=(
  "buffalo_l/det_10g.onnx"
  "buffalo_l/w600k_r50.onnx"
  "buffalo_l/1k3d68.onnx"
  "buffalo_l/2d106det.onnx"
  "buffalo_l/genderage.onnx"
)

# ── Verify-only path ────────────────────────────────────────────────────
if [[ "${VERIFY_ONLY}" -eq 1 ]]; then
  log "Verify-only mode: checking existing files against CHECKSUMS.txt"
  failed=0
  for rel in "${EXPECTED_FILES[@]}"; do
    verify_file "${rel}" || failed=1
  done
  if [[ "${failed}" -eq 1 ]]; then
    err "Verification failed."
    exit 1
  fi
  log "All files verified OK."
  exit 0
fi

# ── 1. Download the zip ─────────────────────────────────────────────────
mkdir -p "${MODEL_DIR}"

if [[ -f "${ZIP_PATH}" ]]; then
  log "buffalo_l.zip already present, skipping download"
else
  log "Downloading buffalo_l.zip (~288 MB)…"
  log "  URL: ${BUFFALO_L_URL}"
  if ! curl -fL --retry 3 --retry-delay 2 -o "${ZIP_PATH}.tmp" "${BUFFALO_L_URL}"; then
    err "Download failed. Removing partial file."
    rm -f "${ZIP_PATH}.tmp"
    exit 1
  fi
  mv "${ZIP_PATH}.tmp" "${ZIP_PATH}"
  log "Downloaded to ${ZIP_PATH}"
fi

# ── 2. Verify zip SHA-256 BEFORE touching disk further ──────────────────
log "Verifying buffalo_l.zip…"
if ! verify_file "buffalo_l.zip"; then
  err "Zip hash mismatch. Deleting the bad download and aborting."
  rm -f "${ZIP_PATH}"
  exit 1
fi

# ── 3. Unzip into the target directory ─────────────────────────────────
log "Unzipping into ${UNZIP_DIR}…"
# Clean any previous partial unzip
rm -rf "${UNZIP_DIR}"
mkdir -p "${UNZIP_DIR}"

if ! unzip -q -o "${ZIP_PATH}" -d "${MODEL_DIR}"; then
  err "Unzip failed. Cleaning up."
  rm -rf "${UNZIP_DIR}"
  exit 1
fi

# ── 4. Verify each expected .onnx individually ─────────────────────────
log "Verifying individual model files…"
failed=0
for rel in "${EXPECTED_FILES[@]}"; do
  verify_file "${rel}" || failed=1
done

if [[ "${failed}" -eq 1 ]]; then
  err "One or more model files failed verification. Cleaning up."
  rm -rf "${UNZIP_DIR}"
  exit 1
fi

log "InsightFace buffalo_l pack downloaded and verified successfully."
log "Models are at: ${UNZIP_DIR}"

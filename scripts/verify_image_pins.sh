#!/usr/bin/env bash
# EkamCore Docker image pin verification (G-12 / ART-24)
#
# Checks that all base images in Dockerfiles and docker-compose.yml
# use pinned SHA256 digests (image@sha256:...) for supply chain security.
#
# Usage:
#   ./scripts/verify_image_pins.sh
#
# Exit codes:
#   0 — all images are pinned with @sha256: digests
#   1 — unpinned images found
#
# Must be run from the EkamCore project root.

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log() { echo "[$(date +%H:%M:%S)] $*"; }

PINNED=0
UNPINNED=0
TOTAL=0

log "============================================================"
log "  EkamCore Docker Image Pin Verification (ART-24)"
log "============================================================"
log ""

check_image() {
    local source="$1" image="$2" line_num="$3"
    ((TOTAL++))

    # Skip scratch and build stage aliases (FROM builder, FROM runtime, etc.)
    if [[ "$image" == "scratch" ]] || ! echo "$image" | grep -qE '[:/@]'; then
        return
    fi

    if echo "$image" | grep -q '@sha256:'; then
        log "  [pinned]   ${source}:${line_num} — ${image}"
        ((PINNED++))
    else
        log "  [UNPINNED] ${source}:${line_num} — ${image}"
        ((UNPINNED++))
    fi
}

# ── Check Dockerfiles ────────────────────────────────────────────────────────

log "[Dockerfiles]"

while IFS= read -r dockerfile; do
    rel_path="${dockerfile#${PROJECT_ROOT}/}"
    line_num=0
    while IFS= read -r line; do
        ((line_num++))
        # Match FROM lines: FROM image:tag [AS stage]
        if echo "$line" | grep -qiE '^\s*FROM\s+'; then
            # Strip FROM prefix and AS suffix (case-insensitive via tr)
            image=$(echo "$line" | sed -E 's/^[[:space:]]*[Ff][Rr][Oo][Mm][[:space:]]+//' | sed -E 's/[[:space:]]+[Aa][Ss][[:space:]]+.*$//' | sed -E 's/[[:space:]]+$//')
            check_image "$rel_path" "$image" "$line_num"
        fi
    done < "$dockerfile"
done < <(find "$PROJECT_ROOT" -name 'Dockerfile*' -not -path '*/node_modules/*' -not -path '*/.git/*' | sort)

# ── Check docker-compose.yml ────────────────────────────────────────────────

log ""
log "[docker-compose.yml]"

COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
if [[ -f "$COMPOSE_FILE" ]]; then
    line_num=0
    while IFS= read -r line; do
        ((line_num++))
        # Match image: lines (strip quotes, leading whitespace)
        if echo "$line" | grep -qE '^\s+image:\s+'; then
            image=$(echo "$line" | sed -E 's/^[[:space:]]*image:[[:space:]]+//' | sed -E 's/^["'"'"']//; s/["'"'"']$//' | sed -E 's/[[:space:]]+$//')
            check_image "docker-compose.yml" "$image" "$line_num"
        fi
    done < "$COMPOSE_FILE"
else
    log "  [warn] docker-compose.yml not found"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

log ""
log "============================================================"
log "  Total images: ${TOTAL}"
log "  Pinned (@sha256:): ${PINNED}"
log "  Unpinned: ${UNPINNED}"

if [[ $UNPINNED -gt 0 ]]; then
    log ""
    log "  FAIL: ${UNPINNED} unpinned image(s) found."
    log ""
    log "  To pin an image, look up its digest:"
    log "    docker pull <image>:<tag>"
    log "    docker inspect --format='{{index .RepoDigests 0}}' <image>:<tag>"
    log ""
    log "  Then update the FROM/image line:"
    log "    FROM python:3.12-slim@sha256:<digest>"
    log "    image: postgres:16.3@sha256:<digest>"
else
    log ""
    log "  PASS: All images are pinned with SHA256 digests."
fi
log "============================================================"

[[ $UNPINNED -gt 0 ]] && exit 1
exit 0

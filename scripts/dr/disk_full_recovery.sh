#!/usr/bin/env bash
# EkamCore Disk Full Recovery (S15-010 / ART-17)
#
# Frees disk space when the system is running low (< 30 GB free).
# Steps: identify consumers, rotate logs, prune Docker, clean old backups.
#
# Usage:
#   ./scripts/dr/disk_full_recovery.sh
#
# RTO target: < 10 minutes

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${EKAMCORE_BACKUP_DIR:-/backups}"
BACKUPS_TO_KEEP=3

echo "================================================================"
echo "  EkamCore Disk Full Recovery"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================================"

FREED_MB=0

# ── Step 1: Current disk status ──────────────────────────────────────────────

echo ""
echo "--- Step 1: Current Disk Status ---"

FREE_KB=$(df -k / | tail -1 | awk '{print $4}')
FREE_GB=$((FREE_KB / 1024 / 1024))
echo "  Boot volume free: ${FREE_GB} GB"

if [[ $FREE_GB -ge 30 ]]; then
    echo "  Disk space is adequate (>= 30 GB). Recovery not needed."
    echo "  Exiting."
    exit 0
fi

echo "  WARNING: Only ${FREE_GB} GB free — beginning cleanup..."

# ── Step 2: Identify largest Docker consumers ───────────────────────────────

echo ""
echo "--- Step 2: Docker Space Usage ---"

docker system df 2>/dev/null || echo "  Docker not available"

# ── Step 3: Truncate container logs ──────────────────────────────────────────

echo ""
echo "--- Step 3: Truncate Container Logs ---"

LOG_FREED=0
for container_id in $(docker ps -q --filter "label=com.docker.compose.project=ekamcore" 2>/dev/null); do
    LOG_FILE=$(docker inspect --format='{{.LogPath}}' "$container_id" 2>/dev/null)
    if [[ -n "$LOG_FILE" && -f "$LOG_FILE" ]]; then
        LOG_SIZE=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo "0")
        LOG_SIZE_MB=$((LOG_SIZE / 1024 / 1024))
        if [[ $LOG_SIZE_MB -gt 10 ]]; then
            NAME=$(docker inspect --format='{{.Name}}' "$container_id" 2>/dev/null | tr -d '/')
            echo "  Truncating $NAME log (${LOG_SIZE_MB} MB)..."
            truncate -s 0 "$LOG_FILE" 2>/dev/null || true
            LOG_FREED=$((LOG_FREED + LOG_SIZE_MB))
        fi
    fi
done
echo "  Freed from logs: ${LOG_FREED} MB"
FREED_MB=$((FREED_MB + LOG_FREED))

# ── Step 4: Clean old backups (keep last N) ──────────────────────────────────

echo ""
echo "--- Step 4: Clean Old Backups (keep last $BACKUPS_TO_KEEP) ---"

BACKUP_FREED=0
if [[ -d "$BACKUP_DIR" ]]; then
    BACKUP_COUNT=$(ls -d "$BACKUP_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ')
    if [[ $BACKUP_COUNT -gt $BACKUPS_TO_KEEP ]]; then
        TO_DELETE=$((BACKUP_COUNT - BACKUPS_TO_KEEP))
        echo "  Found $BACKUP_COUNT backups, removing oldest $TO_DELETE..."
        ls -dt "$BACKUP_DIR"/*/ 2>/dev/null | tail -n "$TO_DELETE" | while read -r dir; do
            DIR_SIZE=$(du -sm "$dir" 2>/dev/null | awk '{print $1}')
            echo "    Removing: $(basename "$dir") (${DIR_SIZE:-?} MB)"
            rm -rf "$dir"
            BACKUP_FREED=$((BACKUP_FREED + ${DIR_SIZE:-0}))
        done
    else
        echo "  Only $BACKUP_COUNT backups — keeping all"
    fi
else
    echo "  No backup directory at $BACKUP_DIR"
fi
FREED_MB=$((FREED_MB + BACKUP_FREED))

# ── Step 5: Docker system prune ──────────────────────────────────────────────

echo ""
echo "--- Step 5: Docker System Prune ---"

BEFORE_IMAGES=$(docker system df --format '{{.Size}}' 2>/dev/null | head -1)
docker system prune -f 2>/dev/null | tail -2
docker builder prune -f 2>/dev/null | tail -1
echo "  Docker prune complete"

# ── Step 6: Clean Ollama cache (unused models) ──────────────────────────────

echo ""
echo "--- Step 6: Ollama Cache ---"

OLLAMA_CACHE="$HOME/.ollama/models/blobs"
if [[ -d "$OLLAMA_CACHE" ]]; then
    OLLAMA_SIZE=$(du -sm "$OLLAMA_CACHE" 2>/dev/null | awk '{print $1}')
    echo "  Ollama model cache: ${OLLAMA_SIZE:-?} MB"
    echo "  (Not auto-cleaning models — run 'ollama rm <model>' manually if needed)"
else
    echo "  No Ollama cache found"
fi

# ── Step 7: Verify free space ────────────────────────────────────────────────

echo ""
echo "--- Step 7: Verify Free Space ---"

NEW_FREE_KB=$(df -k / | tail -1 | awk '{print $4}')
NEW_FREE_GB=$((NEW_FREE_KB / 1024 / 1024))
DELTA_GB=$((NEW_FREE_GB - FREE_GB))

echo "  Before: ${FREE_GB} GB free"
echo "  After:  ${NEW_FREE_GB} GB free"
echo "  Freed:  ~${DELTA_GB} GB"

# ── Step 8: Restart services if they were failing ────────────────────────────

echo ""
echo "--- Step 8: Service Recovery ---"

if [[ $NEW_FREE_GB -ge 10 ]]; then
    echo "  Restarting any stopped services..."
    cd "$PROJECT_ROOT"
    docker compose up -d 2>/dev/null | tail -3

    sleep 5
    if curl -sf --max-time 5 http://localhost:8420/health >/dev/null 2>&1; then
        echo "  [OK] API is healthy"
    else
        echo "  [!!] API not healthy — may need more time or manual intervention"
    fi
else
    echo "  [!!] Still low on space (${NEW_FREE_GB} GB). Manual cleanup required."
    echo "  Consider:"
    echo "    - Remove unused Docker images: docker image prune -a"
    echo "    - Remove unused Ollama models: ollama rm <model_name>"
    echo "    - Move backups to external storage"
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "================================================================"
echo "  Disk Recovery Complete"
echo "  Space freed: ~${DELTA_GB} GB | Now available: ${NEW_FREE_GB} GB"
if [[ $NEW_FREE_GB -ge 30 ]]; then
    echo "  Status: RECOVERED (>= 30 GB free)"
elif [[ $NEW_FREE_GB -ge 10 ]]; then
    echo "  Status: PARTIAL — still below 30 GB target"
else
    echo "  Status: CRITICAL — manual intervention needed"
fi
echo "================================================================"

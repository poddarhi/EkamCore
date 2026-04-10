#!/usr/bin/env bash
# EkamCore backup script (S08-004)
#
# Backs up:
#   - PostgreSQL: ekamcore + paperless databases (pg_dump custom format)
#   - Qdrant: collection snapshots via REST API + docker cp
#   - Paperless: document export via management command
#   - Config: .env, docker-compose.yml, config/
#
# Usage:
#   ./infra/backup/backup.sh [--backup-dir /path/to/backups] [--dry-run]
#
# Must be run from the EkamCore project root (where docker-compose.yml lives).

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults and argument parsing
# ---------------------------------------------------------------------------

BACKUP_ROOT="${EKAMCORE_BACKUP_DIR:-/backups}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-dir) BACKUP_ROOT="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        *)            echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

# Source .env for credentials if present (non-interactive shell may not have them)
if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-ekamcore}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ekamcore_dev_password}"
QDRANT_API_KEY="${QDRANT_API_KEY:-ekamcore_qdrant_dev}"
QDRANT_HOST="${QDRANT_HOST:-localhost:6333}"

export PGPASSWORD="$POSTGRES_PASSWORD"

log() { echo "[$(date +%H:%M:%S)] $*"; }
log_dry() { echo "[$(date +%H:%M:%S)] [DRY-RUN] $*"; }

if [[ "$DRY_RUN" == "true" ]]; then
    log_dry "Backup to: $BACKUP_DIR"
    log_dry "Skipping actual operations."
    exit 0
fi

# ---------------------------------------------------------------------------
# Verify stack is up
# ---------------------------------------------------------------------------

if ! docker compose ps --status running ekamcore-postgres 2>/dev/null | grep -q "running"; then
    echo "ERROR: ekamcore-postgres is not running. Start the stack first." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Create backup directory
# ---------------------------------------------------------------------------

mkdir -p "$BACKUP_DIR"
log "Backup directory: $BACKUP_DIR"

# ---------------------------------------------------------------------------
# 1. PostgreSQL dumps
# ---------------------------------------------------------------------------

log "Backing up PostgreSQL..."
mkdir -p "$BACKUP_DIR/postgres"

docker compose exec -T ekamcore-postgres \
    pg_dump -U "$POSTGRES_USER" -Fc ekamcore \
    > "$BACKUP_DIR/postgres/ekamcore.dump"
log "  ✓ ekamcore database"

docker compose exec -T ekamcore-postgres \
    pg_dump -U "$POSTGRES_USER" -Fc paperless \
    > "$BACKUP_DIR/postgres/paperless.dump"
log "  ✓ paperless database"

# ---------------------------------------------------------------------------
# 2. Qdrant collection snapshots
# ---------------------------------------------------------------------------

log "Backing up Qdrant collections..."
mkdir -p "$BACKUP_DIR/qdrant"

_qdrant_snapshot() {
    local collection="$1"
    local response

    # Create snapshot — Qdrant returns {"result": {"name": "...", ...}}
    response=$(curl -sf \
        -X POST \
        -H "api-key: ${QDRANT_API_KEY}" \
        "http://${QDRANT_HOST}/collections/${collection}/snapshots" \
        2>/dev/null) || {
        log "  ⚠ Collection '${collection}' not found or Qdrant unavailable — skipping"
        return 0
    }

    local snapshot_name
    snapshot_name=$(echo "$response" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['result']['name'])" 2>/dev/null) || {
        log "  ⚠ Could not parse snapshot name for '${collection}' — skipping"
        return 0
    }

    log "  ✓ Created snapshot: ${collection}/${snapshot_name}"
}

_qdrant_snapshot "document_embeddings"
_qdrant_snapshot "photo_embeddings"
_qdrant_snapshot "face_embeddings"

# Copy all snapshots out of the container at once
docker compose cp "ekamcore-qdrant:/qdrant/snapshots" "$BACKUP_DIR/qdrant/" 2>/dev/null \
    && log "  ✓ Qdrant snapshots copied" \
    || log "  ⚠ No Qdrant snapshots directory (no collections yet) — skipping"

# ---------------------------------------------------------------------------
# 3. Paperless document export
# ---------------------------------------------------------------------------

log "Backing up Paperless documents..."
mkdir -p "$BACKUP_DIR/paperless-export"

if docker compose ps --status running ekamcore-paperless 2>/dev/null | grep -q "running"; then
    # document_exporter writes to an internal directory; we then cp it out
    docker compose exec -T ekamcore-paperless \
        document_exporter /usr/src/paperless/export/ \
        --no-archive 2>/dev/null \
        && log "  ✓ Paperless export complete" \
        || log "  ⚠ Paperless export failed — skipping"

    docker compose cp \
        "ekamcore-paperless:/usr/src/paperless/export/" \
        "$BACKUP_DIR/paperless-export/" 2>/dev/null \
        && log "  ✓ Paperless export copied" \
        || log "  ⚠ Could not copy Paperless export — skipping"
else
    log "  ⚠ ekamcore-paperless is not running — skipping Paperless backup"
fi

# ---------------------------------------------------------------------------
# 4. Config files
# ---------------------------------------------------------------------------

log "Backing up config files..."
mkdir -p "$BACKUP_DIR/config"

[[ -f ".env" ]] && cp ".env" "$BACKUP_DIR/config/.env"
cp "docker-compose.yml" "$BACKUP_DIR/config/"
cp -r "config/" "$BACKUP_DIR/config/ekamcore-config"
log "  ✓ .env, docker-compose.yml, config/"

# ---------------------------------------------------------------------------
# 5. Rotation
# ---------------------------------------------------------------------------

log "Running backup rotation..."
python3 "$(dirname "$0")/rotate.py" --backup-dir "$BACKUP_ROOT"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo "unknown")
log "Backup complete: $BACKUP_DIR ($BACKUP_SIZE)"
echo "$BACKUP_DIR"

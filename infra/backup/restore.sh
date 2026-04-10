#!/usr/bin/env bash
# EkamCore restore script (S08-004)
#
# Restores from a backup created by backup.sh:
#   1. Stops all services
#   2. Restores PostgreSQL databases (ekamcore + paperless)
#   3. Restores Qdrant collection snapshots
#   4. Restores Paperless documents via document_importer
#   5. Restarts services
#
# Usage:
#   ./infra/backup/restore.sh <backup-path>
#
# Example:
#   ./infra/backup/restore.sh /backups/2026-04-10_02-00-00
#
# Must be run from the EkamCore project root (where docker-compose.yml lives).
# WARNING: This OVERWRITES all existing data. Ensure you want to restore.

set -euo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup-path>" >&2
    echo "" >&2
    echo "Example: $0 /backups/2026-04-10_02-00-00" >&2
    exit 1
fi

BACKUP_DIR="$1"

if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "ERROR: Backup directory not found: $BACKUP_DIR" >&2
    exit 1
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "Restoring from: $BACKUP_DIR"
log "WARNING: This will OVERWRITE all existing data in the running stack."
read -r -p "Proceed? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "Restore cancelled."
    exit 0
fi

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# 1. Stop all services except postgres and qdrant
# ---------------------------------------------------------------------------

log "Stopping application services..."
docker compose stop ekamcore-api ekamcore-workers ekamcore-web ekamcore-proxy \
    ekamcore-paperless 2>/dev/null || true

log "Services stopped. Postgres and Qdrant remain running for restore."

# ---------------------------------------------------------------------------
# 2. Restore PostgreSQL
# ---------------------------------------------------------------------------

log "Restoring PostgreSQL..."

if [[ -f "$BACKUP_DIR/postgres/ekamcore.dump" ]]; then
    # Drop and recreate the ekamcore database
    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='ekamcore' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS ekamcore;" > /dev/null

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "CREATE DATABASE ekamcore OWNER $POSTGRES_USER;" > /dev/null

    docker compose exec -T ekamcore-postgres \
        pg_restore -U "$POSTGRES_USER" -d ekamcore --no-acl --no-owner \
        < "$BACKUP_DIR/postgres/ekamcore.dump"

    log "  ✓ ekamcore database restored"
else
    log "  ⚠ ekamcore.dump not found — skipping"
fi

if [[ -f "$BACKUP_DIR/postgres/paperless.dump" ]]; then
    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='paperless' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS paperless;" > /dev/null

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "CREATE DATABASE paperless OWNER $POSTGRES_USER;" > /dev/null

    docker compose exec -T ekamcore-postgres \
        pg_restore -U "$POSTGRES_USER" -d paperless --no-acl --no-owner \
        < "$BACKUP_DIR/postgres/paperless.dump"

    log "  ✓ paperless database restored"
else
    log "  ⚠ paperless.dump not found — skipping"
fi

# ---------------------------------------------------------------------------
# 3. Restore Qdrant snapshots
# ---------------------------------------------------------------------------

log "Restoring Qdrant collections..."

if [[ -d "$BACKUP_DIR/qdrant/snapshots" ]]; then
    # Copy snapshot files back into the container
    docker compose cp "$BACKUP_DIR/qdrant/snapshots" "ekamcore-qdrant:/qdrant/snapshots"
    log "  ✓ Snapshots copied to container"

    # Recover each collection from its most recent snapshot
    for collection_dir in "$BACKUP_DIR/qdrant/snapshots"/*/; do
        collection="$(basename "$collection_dir")"
        # Find the most recent snapshot file in this collection's directory
        snapshot_file=$(ls -t "$collection_dir"*.snapshot 2>/dev/null | head -1) || continue
        [[ -z "$snapshot_file" ]] && continue
        snapshot_name="$(basename "$snapshot_file")"

        log "  Recovering ${collection} from ${snapshot_name}..."

        # Use the Qdrant recover API with the in-container path
        curl -sf \
            -X PUT \
            -H "api-key: ${QDRANT_API_KEY}" \
            -H "Content-Type: application/json" \
            -d "{\"location\": \"/qdrant/snapshots/${collection}/${snapshot_name}\"}" \
            "http://${QDRANT_HOST}/collections/${collection}/snapshots/recover" \
            > /dev/null \
            && log "  ✓ ${collection} recovered" \
            || log "  ⚠ ${collection} recovery failed — may need manual recovery"
    done
else
    log "  ⚠ No Qdrant snapshots in backup — skipping"
fi

# ---------------------------------------------------------------------------
# 4. Restore Paperless documents
# ---------------------------------------------------------------------------

log "Restoring Paperless documents..."

if [[ -d "$BACKUP_DIR/paperless-export" ]]; then
    log "  Starting Paperless for import..."
    docker compose up -d ekamcore-paperless
    log "  Waiting for Paperless to be ready..."
    timeout 120 bash -c \
        'until docker compose exec -T ekamcore-paperless curl -sf http://localhost:8000/api/ > /dev/null 2>&1; do sleep 5; done' \
        || log "  ⚠ Paperless health check timed out — attempting import anyway"

    # Copy export back into the container
    docker compose cp \
        "$BACKUP_DIR/paperless-export/" \
        "ekamcore-paperless:/usr/src/paperless/import/"

    docker compose exec -T ekamcore-paperless \
        document_importer /usr/src/paperless/import/ \
        && log "  ✓ Paperless documents imported" \
        || log "  ⚠ Paperless import failed — check logs"
else
    log "  ⚠ No Paperless export in backup — skipping"
fi

# ---------------------------------------------------------------------------
# 5. Re-run migrations (in case schema version changed)
# ---------------------------------------------------------------------------

log "Running database migrations..."
docker compose run --rm ekamcore-migrate
log "  ✓ Migrations complete"

# ---------------------------------------------------------------------------
# 6. Restart all services
# ---------------------------------------------------------------------------

log "Starting all services..."
docker compose up -d

log "Waiting for health checks..."
sleep 15
docker compose ps

log ""
log "Restore complete from: $BACKUP_DIR"
log "Verify the application is working correctly before declaring success."

#!/usr/bin/env bash
# EkamCore disaster recovery: restore from backup (G-07 / ART-17)
#
# Full restore procedure with integrity verification and timing.
# Extends infra/backup/restore.sh with:
#   - Automated verification (table counts, collection counts)
#   - JSON report output
#   - Non-interactive mode (--yes flag)
#   - Timing per phase
#
# Usage:
#   ./scripts/dr/restore_from_backup.sh <backup-path> [--yes]
#
# Output:
#   restore_report.json  (project root)
#
# Must be run from the EkamCore project root.

set -uo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────

CONFIRM_YES=false

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup-path> [--yes]" >&2
    echo "  --yes    Skip confirmation prompt" >&2
    exit 1
fi

BACKUP_DIR="$1"
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) CONFIRM_YES=true; shift ;;
        *)     echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "ERROR: Backup directory not found: $BACKUP_DIR" >&2
    exit 1
fi

# ── Environment ───────────────────────────────────────────────────────────────

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPORT_FILE="${PROJECT_ROOT}/restore_report.json"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-ekamcore}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ekamcore_dev_password}"
QDRANT_API_KEY="${QDRANT_API_KEY:-ekamcore_qdrant_dev}"
QDRANT_HOST="${QDRANT_HOST:-localhost:6333}"

export PGPASSWORD="$POSTGRES_PASSWORD"

log() { echo "[$(date +%H:%M:%S)] $*"; }

RESTORE_START=$(date +%s)
PHASES="[]"

add_phase() {
    local name="$1" status="$2" duration_s="$3" details="$4"
    PHASES=$(echo "$PHASES" | python3 -c "
import sys, json
phases = json.load(sys.stdin)
phases.append({'phase': '$name', 'status': '$status', 'duration_s': $duration_s, 'details': '''$details'''})
print(json.dumps(phases))
")
}

# ── Confirmation ──────────────────────────────────────────────────────────────

log "═══════════════════════════════════════════════════════════"
log "  EkamCore Disaster Recovery: Restore from Backup"
log "  Backup: $BACKUP_DIR"
log "═══════════════════════════════════════════════════════════"
log ""
log "WARNING: This will OVERWRITE all existing data."

if [[ "$CONFIRM_YES" != "true" ]]; then
    read -r -p "[$(date +%H:%M:%S)] Proceed? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Restore cancelled."
        exit 0
    fi
fi

# ── Phase 1: Stop application services ────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 1: Stopping application services..."

docker compose stop ekamcore-api ekamcore-workers ekamcore-web ekamcore-proxy \
    ekamcore-paperless 2>/dev/null || true

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "stop_services" "OK" "$PHASE_DURATION" "Stopped api, workers, web, proxy, paperless"
log "  ✓ Services stopped (${PHASE_DURATION}s)"

# ── Phase 2: Ensure data services are running ────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 2: Ensuring postgres, redis, qdrant are running..."

docker compose up -d ekamcore-postgres ekamcore-redis ekamcore-qdrant 2>/dev/null

# Wait for postgres healthy
WAIT=0
until docker compose exec -T ekamcore-postgres pg_isready -U "$POSTGRES_USER" > /dev/null 2>&1; do
    sleep 2
    WAIT=$((WAIT + 2))
    if [[ $WAIT -ge 60 ]]; then
        log "  ✗ PostgreSQL did not become ready within 60s"
        add_phase "start_data_services" "FAIL" "$WAIT" "PostgreSQL not ready"
        exit 1
    fi
done

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "start_data_services" "OK" "$PHASE_DURATION" "postgres, redis, qdrant running"
log "  ✓ Data services ready (${PHASE_DURATION}s)"

# ── Phase 3: Restore PostgreSQL ───────────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 3: Restoring PostgreSQL..."

PG_STATUS="OK"
PG_DETAILS=""

if [[ -f "$BACKUP_DIR/postgres/ekamcore.dump" ]]; then
    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='ekamcore' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS ekamcore;" > /dev/null 2>&1

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "CREATE DATABASE ekamcore OWNER $POSTGRES_USER;" > /dev/null 2>&1

    if docker compose exec -T ekamcore-postgres \
        pg_restore -U "$POSTGRES_USER" -d ekamcore --no-acl --no-owner \
        < "$BACKUP_DIR/postgres/ekamcore.dump" 2>/dev/null; then
        log "  ✓ ekamcore database restored"
        PG_DETAILS="ekamcore restored"
    else
        # pg_restore returns non-zero on warnings too — check if tables exist
        TABLE_CHECK=$(docker compose exec -T ekamcore-postgres \
            psql -U "$POSTGRES_USER" -d ekamcore -t -A \
            -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'" \
            2>/dev/null | tr -d '[:space:]')
        if [[ "$TABLE_CHECK" -ge 10 ]]; then
            log "  ✓ ekamcore database restored (with warnings)"
            PG_DETAILS="ekamcore restored with warnings (${TABLE_CHECK} tables)"
        else
            log "  ✗ ekamcore restore failed"
            PG_STATUS="FAIL"
            PG_DETAILS="ekamcore restore failed"
        fi
    fi
else
    log "  ⚠ ekamcore.dump not found"
    PG_STATUS="WARN"
    PG_DETAILS="ekamcore.dump not found in backup"
fi

if [[ -f "$BACKUP_DIR/postgres/paperless.dump" ]]; then
    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='paperless' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS paperless;" > /dev/null 2>&1

    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "CREATE DATABASE paperless OWNER $POSTGRES_USER;" > /dev/null 2>&1

    docker compose exec -T ekamcore-postgres \
        pg_restore -U "$POSTGRES_USER" -d paperless --no-acl --no-owner \
        < "$BACKUP_DIR/postgres/paperless.dump" 2>/dev/null \
        && log "  ✓ paperless database restored" \
        || log "  ⚠ paperless restore had warnings"
    PG_DETAILS="${PG_DETAILS}; paperless restored"
else
    log "  ⚠ paperless.dump not found — skipping"
fi

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "restore_postgres" "$PG_STATUS" "$PHASE_DURATION" "$PG_DETAILS"
log "  Phase 3 complete (${PHASE_DURATION}s)"

# ── Phase 4: Restore Qdrant ──────────────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 4: Restoring Qdrant collections..."

QD_STATUS="OK"
QD_DETAILS=""
COLLECTIONS_RESTORED=0

if [[ -d "$BACKUP_DIR/qdrant/snapshots" ]]; then
    docker compose cp "$BACKUP_DIR/qdrant/snapshots" "ekamcore-qdrant:/qdrant/snapshots" 2>/dev/null

    for collection_dir in "$BACKUP_DIR/qdrant/snapshots"/*/; do
        [[ ! -d "$collection_dir" ]] && continue
        collection="$(basename "$collection_dir")"
        snapshot_file=$(ls -t "$collection_dir"*.snapshot 2>/dev/null | head -1) || continue
        [[ -z "$snapshot_file" ]] && continue
        snapshot_name="$(basename "$snapshot_file")"

        if curl -sf \
            -X PUT \
            -H "api-key: ${QDRANT_API_KEY}" \
            -H "Content-Type: application/json" \
            -d "{\"location\": \"/qdrant/snapshots/${collection}/${snapshot_name}\"}" \
            "http://${QDRANT_HOST}/collections/${collection}/snapshots/recover" \
            > /dev/null 2>&1; then
            log "  ✓ ${collection} recovered"
            ((COLLECTIONS_RESTORED++))
        else
            log "  ⚠ ${collection} recovery failed"
        fi
    done
    QD_DETAILS="${COLLECTIONS_RESTORED} collections recovered"
else
    log "  ⚠ No Qdrant snapshots in backup"
    QD_STATUS="WARN"
    QD_DETAILS="No snapshots in backup"
fi

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "restore_qdrant" "$QD_STATUS" "$PHASE_DURATION" "$QD_DETAILS"
log "  Phase 4 complete (${PHASE_DURATION}s)"

# ── Phase 5: Run migrations ──────────────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 5: Running database migrations..."

if docker compose run --rm ekamcore-migrate 2>/dev/null; then
    log "  ✓ Migrations complete"
    add_phase "run_migrations" "OK" "$(( $(date +%s) - PHASE_START ))" "alembic upgrade head succeeded"
else
    log "  ✗ Migration failed"
    add_phase "run_migrations" "FAIL" "$(( $(date +%s) - PHASE_START ))" "alembic upgrade head failed"
fi

# ── Phase 6: Restart all services ────────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 6: Starting all services..."

docker compose up -d 2>/dev/null

log "  Waiting for services to become healthy..."
sleep 15

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "restart_services" "OK" "$PHASE_DURATION" "docker compose up -d"
log "  ✓ Services started (${PHASE_DURATION}s)"

# ── Phase 7: Verify data integrity ──────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 7: Verifying data integrity..."

VERIFY_STATUS="OK"
VERIFY_DETAILS=""

# Count tables
TABLE_COUNT=$(docker compose exec -T ekamcore-postgres \
    psql -U "$POSTGRES_USER" -d ekamcore -t -A \
    -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'" \
    2>/dev/null | tr -d '[:space:]') || TABLE_COUNT=0

if [[ "$TABLE_COUNT" -ge 16 ]]; then
    log "  ✓ ${TABLE_COUNT} tables verified"
else
    log "  ✗ Only ${TABLE_COUNT} tables (expected >= 16)"
    VERIFY_STATUS="FAIL"
fi

# Count rows in key tables
for table in users workspaces sessions sources calendar_events reminders contacts; do
    ROW_COUNT=$(docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d ekamcore -t -A \
        -c "SELECT count(*) FROM ${table}" 2>/dev/null | tr -d '[:space:]') || ROW_COUNT="error"
    log "  ${table}: ${ROW_COUNT} rows"
    VERIFY_DETAILS="${VERIFY_DETAILS}${table}=${ROW_COUNT};"
done

# Check Qdrant collections
for collection in document_embeddings photo_embeddings face_embeddings; do
    POINT_COUNT=$(curl -sf -H "api-key: ${QDRANT_API_KEY}" \
        "http://${QDRANT_HOST}/collections/${collection}" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])" 2>/dev/null \
        || echo "N/A")
    log "  qdrant:${collection}: ${POINT_COUNT} points"
    VERIFY_DETAILS="${VERIFY_DETAILS}qdrant_${collection}=${POINT_COUNT};"
done

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "verify_integrity" "$VERIFY_STATUS" "$PHASE_DURATION" "${TABLE_COUNT} tables; ${VERIFY_DETAILS}"

# ── Phase 8: Health check ────────────────────────────────────────────────────

PHASE_START=$(date +%s)
log ""
log "Phase 8: Running health check..."

API_HEALTH=$(curl -sf "http://localhost:8420/health" 2>/dev/null || echo "")
if [[ -n "$API_HEALTH" ]]; then
    API_STATUS=$(echo "$API_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
    log "  API health: ${API_STATUS}"
    HEALTH_STATUS="OK"
    [[ "$API_STATUS" != "healthy" ]] && HEALTH_STATUS="WARN"
else
    log "  ✗ API health endpoint not reachable"
    HEALTH_STATUS="FAIL"
    API_STATUS="unreachable"
fi

PHASE_DURATION=$(( $(date +%s) - PHASE_START ))
add_phase "health_check" "$HEALTH_STATUS" "$PHASE_DURATION" "API status: ${API_STATUS}"

# ── Write report ──────────────────────────────────────────────────────────────

RESTORE_DURATION=$(( $(date +%s) - RESTORE_START ))

OVERALL="SUCCESS"
echo "$PHASES" | python3 -c "
import sys, json
phases = json.load(sys.stdin)
if any(p['status'] == 'FAIL' for p in phases):
    print('PARTIAL_FAILURE')
else:
    print('SUCCESS')
" | read -r OVERALL || OVERALL="SUCCESS"

python3 -c "
import json
report = {
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'backup_path': '${BACKUP_DIR}',
    'total_duration_s': ${RESTORE_DURATION},
    'overall_status': '${OVERALL}',
    'phases': ${PHASES}
}
with open('${REPORT_FILE}', 'w') as f:
    json.dump(report, f, indent=2)
"

log ""
log "═══════════════════════════════════════════════════════════"
log "  Restore complete in ${RESTORE_DURATION}s"
log "  Report: ${REPORT_FILE}"
log "═══════════════════════════════════════════════════════════"

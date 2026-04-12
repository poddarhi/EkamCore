#!/usr/bin/env bash
# EkamCore database repair and integrity check (G-07 / ART-17)
#
# Checks:
#   - PostgreSQL for corruption (pg_amcheck if available)
#   - All expected tables exist with correct column counts
#   - Orphaned records (ingestion_states without matching files)
#   - Repairs: VACUUM FULL, REINDEX if issues found
#
# Usage:
#   ./scripts/dr/database_repair.sh [--repair] [--verbose]
#
# Options:
#   --repair    Actually perform VACUUM FULL and REINDEX (default: check only)
#   --verbose   Show detailed output for each check
#
# Must be run from the EkamCore project root.

set -uo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────

DO_REPAIR=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repair)  DO_REPAIR=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        *)         echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-ekamcore}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ekamcore_dev_password}"
export PGPASSWORD="$POSTGRES_PASSWORD"

log() { echo "[$(date +%H:%M:%S)] $*"; }

ISSUES_FOUND=0
REPAIRS_DONE=0

psql_exec() {
    docker compose exec -T ekamcore-postgres \
        psql -U "$POSTGRES_USER" -d ekamcore -t -A "$@" 2>/dev/null
}

log "============================================================"
log "  EkamCore Database Repair & Integrity Check"
log "  Mode: $(if $DO_REPAIR; then echo 'REPAIR'; else echo 'CHECK ONLY'; fi)"
log "============================================================"
log ""

# ── Check 1: PostgreSQL connectivity ─────────────────────────────────────────

log "[Check 1] PostgreSQL connectivity"

if ! psql_exec -c "SELECT 1" | grep -q "1"; then
    log "  ✗ Cannot connect to PostgreSQL"
    log "  Ensure ekamcore-postgres is running: docker compose up -d ekamcore-postgres"
    exit 1
fi
log "  ✓ Connected to PostgreSQL"

# ── Check 2: All expected tables exist ───────────────────────────────────────

log ""
log "[Check 2] Expected tables"

EXPECTED_TABLES=(
    users workspaces workspace_members sessions
    sources files file_chunks ingestion_states
    contacts calendar_events reminders
    photo_assets object_audit_log settings
    notifications correspondent_contact_candidates
)

ACTUAL_TABLES=$(psql_exec -c \
    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")

MISSING_TABLES=()
for table in "${EXPECTED_TABLES[@]}"; do
    if echo "$ACTUAL_TABLES" | grep -q "^${table}$"; then
        $VERBOSE && log "  ✓ ${table}"
    else
        MISSING_TABLES+=("$table")
        log "  ✗ MISSING: ${table}"
        ((ISSUES_FOUND++))
    fi
done

ACTUAL_COUNT=$(echo "$ACTUAL_TABLES" | wc -l | tr -d ' ')
log "  Tables found: ${ACTUAL_COUNT} | Expected: ${#EXPECTED_TABLES[@]} | Missing: ${#MISSING_TABLES[@]}"

if [[ ${#MISSING_TABLES[@]} -gt 0 ]]; then
    log "  ⚠ Missing tables: ${MISSING_TABLES[*]}"
    log "  Fix: Run 'docker compose run --rm ekamcore-migrate'"
fi

# ── Check 3: Table column counts ─────────────────────────────────────────────

log ""
log "[Check 3] Table column counts"

# Expected minimum column counts per table
declare -A MIN_COLUMNS=(
    [users]=6 [workspaces]=4 [workspace_members]=4 [sessions]=5
    [sources]=7 [files]=8 [file_chunks]=6 [ingestion_states]=5
    [contacts]=8 [calendar_events]=7 [reminders]=9
    [photo_assets]=10 [settings]=5 [notifications]=7
)

for table in "${!MIN_COLUMNS[@]}"; do
    COL_COUNT=$(psql_exec -c \
        "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='${table}'" \
        | tr -d '[:space:]')

    if [[ -z "$COL_COUNT" || "$COL_COUNT" == "0" ]]; then
        $VERBOSE && log "  ⚠ ${table}: table not found"
        continue
    fi

    EXPECTED="${MIN_COLUMNS[$table]}"
    if [[ "$COL_COUNT" -ge "$EXPECTED" ]]; then
        $VERBOSE && log "  ✓ ${table}: ${COL_COUNT} columns (>= ${EXPECTED})"
    else
        log "  ✗ ${table}: ${COL_COUNT} columns (expected >= ${EXPECTED})"
        ((ISSUES_FOUND++))
    fi
done

log "  Column count check complete"

# ── Check 4: Orphaned records ────────────────────────────────────────────────

log ""
log "[Check 4] Orphaned records"

# Ingestion states without matching files
ORPHAN_INGESTION=$(psql_exec -c \
    "SELECT count(*) FROM ingestion_states ist LEFT JOIN files f ON ist.file_id = f.id WHERE f.id IS NULL" \
    | tr -d '[:space:]') || ORPHAN_INGESTION="error"

if [[ "$ORPHAN_INGESTION" == "0" ]]; then
    log "  ✓ No orphaned ingestion_states"
elif [[ "$ORPHAN_INGESTION" == "error" ]]; then
    log "  ⚠ Could not check ingestion_states orphans"
else
    log "  ⚠ ${ORPHAN_INGESTION} orphaned ingestion_states (file_id points to deleted file)"
    ((ISSUES_FOUND++))
fi

# File chunks without matching files
ORPHAN_CHUNKS=$(psql_exec -c \
    "SELECT count(*) FROM file_chunks fc LEFT JOIN files f ON fc.file_id = f.id WHERE f.id IS NULL" \
    | tr -d '[:space:]') || ORPHAN_CHUNKS="error"

if [[ "$ORPHAN_CHUNKS" == "0" ]]; then
    log "  ✓ No orphaned file_chunks"
elif [[ "$ORPHAN_CHUNKS" == "error" ]]; then
    log "  ⚠ Could not check file_chunks orphans"
else
    log "  ⚠ ${ORPHAN_CHUNKS} orphaned file_chunks"
    ((ISSUES_FOUND++))
fi

# Workspace members without matching users
ORPHAN_MEMBERS=$(psql_exec -c \
    "SELECT count(*) FROM workspace_members wm LEFT JOIN users u ON wm.user_id = u.id WHERE u.id IS NULL" \
    | tr -d '[:space:]') || ORPHAN_MEMBERS="error"

if [[ "$ORPHAN_MEMBERS" == "0" ]]; then
    log "  ✓ No orphaned workspace_members"
elif [[ "$ORPHAN_MEMBERS" == "error" ]]; then
    log "  ⚠ Could not check workspace_members orphans"
else
    log "  ⚠ ${ORPHAN_MEMBERS} orphaned workspace_members"
    ((ISSUES_FOUND++))
fi

# ── Check 5: pg_amcheck (if available) ───────────────────────────────────────

log ""
log "[Check 5] Index/data corruption check"

HAS_AMCHECK=$(docker compose exec -T ekamcore-postgres \
    psql -U "$POSTGRES_USER" -d ekamcore -t -A \
    -c "SELECT 1 FROM pg_available_extensions WHERE name='amcheck'" 2>/dev/null | tr -d '[:space:]')

if [[ "$HAS_AMCHECK" == "1" ]]; then
    # Enable extension if not already
    psql_exec -c "CREATE EXTENSION IF NOT EXISTS amcheck" > /dev/null 2>&1

    # Check B-tree indexes
    BTREE_ERRORS=$(psql_exec -c "
        SELECT count(*) FROM (
            SELECT bt_index_check(c.oid)
            FROM pg_index i
            JOIN pg_class c ON i.indexrelid = c.oid
            WHERE i.indisvalid
            LIMIT 50
        ) t
    " 2>&1)

    if echo "$BTREE_ERRORS" | grep -qE "^[0-9]+$"; then
        log "  ✓ B-tree index check passed (amcheck)"
    else
        log "  ⚠ B-tree index check had errors — consider REINDEX"
        ((ISSUES_FOUND++))
    fi
else
    log "  ⚠ pg_amcheck extension not available — skipping corruption check"
    log "    (This is normal for some PostgreSQL installations)"
fi

# ── Check 6: Bloat estimation ────────────────────────────────────────────────

log ""
log "[Check 6] Table bloat estimation"

BLOATED_TABLES=$(psql_exec -c "
    SELECT schemaname || '.' || relname AS table_name,
           n_dead_tup,
           n_live_tup,
           CASE WHEN n_live_tup > 0
                THEN round(100.0 * n_dead_tup / n_live_tup, 1)
                ELSE 0 END AS dead_pct
    FROM pg_stat_user_tables
    WHERE n_dead_tup > 1000
      AND n_live_tup > 0
      AND (100.0 * n_dead_tup / n_live_tup) > 20
    ORDER BY n_dead_tup DESC
    LIMIT 10
")

if [[ -z "$BLOATED_TABLES" ]]; then
    log "  ✓ No significant table bloat detected"
else
    log "  ⚠ Tables with >20% dead tuples:"
    echo "$BLOATED_TABLES" | while IFS='|' read -r tname dead live pct; do
        log "    ${tname}: ${dead} dead / ${live} live (${pct}%)"
    done
    ((ISSUES_FOUND++))
fi

# ── Repair (if requested) ────────────────────────────────────────────────────

if [[ "$DO_REPAIR" == "true" ]]; then
    log ""
    log "============================================================"
    log "  Running repairs..."
    log "============================================================"

    # VACUUM FULL on all tables
    log ""
    log "  Running VACUUM FULL..."
    if psql_exec -c "VACUUM FULL" > /dev/null 2>&1; then
        log "  ✓ VACUUM FULL complete"
        ((REPAIRS_DONE++))
    else
        log "  ✗ VACUUM FULL failed"
    fi

    # ANALYZE to update statistics
    log "  Running ANALYZE..."
    if psql_exec -c "ANALYZE" > /dev/null 2>&1; then
        log "  ✓ ANALYZE complete"
        ((REPAIRS_DONE++))
    else
        log "  ✗ ANALYZE failed"
    fi

    # REINDEX if corruption was detected
    if [[ $ISSUES_FOUND -gt 0 ]]; then
        log "  Running REINDEX DATABASE..."
        if psql_exec -c "REINDEX DATABASE ekamcore" > /dev/null 2>&1; then
            log "  ✓ REINDEX complete"
            ((REPAIRS_DONE++))
        else
            log "  ✗ REINDEX failed"
        fi
    fi

    # Clean up orphaned ingestion_states if found
    if [[ "$ORPHAN_INGESTION" != "0" && "$ORPHAN_INGESTION" != "error" ]]; then
        log "  Cleaning orphaned ingestion_states..."
        psql_exec -c \
            "DELETE FROM ingestion_states WHERE file_id NOT IN (SELECT id FROM files)" > /dev/null 2>&1 \
            && log "  ✓ Orphaned ingestion_states removed" \
            || log "  ✗ Could not remove orphaned ingestion_states"
        ((REPAIRS_DONE++))
    fi

    log ""
    log "  Repairs completed: ${REPAIRS_DONE}"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

log ""
log "============================================================"
if [[ $ISSUES_FOUND -eq 0 ]]; then
    log "  Database is healthy. No issues found."
else
    log "  Issues found: ${ISSUES_FOUND}"
    if [[ "$DO_REPAIR" == "true" ]]; then
        log "  Repairs performed: ${REPAIRS_DONE}"
    else
        log "  Run with --repair to fix issues"
    fi
fi
log "============================================================"

[[ $ISSUES_FOUND -gt 0 && "$DO_REPAIR" != "true" ]] && exit 1
exit 0

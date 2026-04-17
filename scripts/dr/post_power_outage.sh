#!/usr/bin/env bash
# EkamCore Post-Power-Outage Recovery (S15-010 / ART-17)
#
# Run this after an unexpected power loss or forced shutdown.
# Checks Docker daemon, starts all services, verifies data integrity.
#
# Usage:
#   ./scripts/dr/post_power_outage.sh
#
# RTO target: < 5 minutes

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "================================================================"
echo "  EkamCore Post-Power-Outage Recovery"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================================"

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [OK] $label"
        PASS=$((PASS + 1))
    else
        echo "  [!!] $label"
        FAIL=$((FAIL + 1))
    fi
}

# ── Step 1: Check Docker daemon ──────────────────────────────────────────────

echo ""
echo "--- Step 1: Docker Daemon ---"

if docker info >/dev/null 2>&1; then
    echo "  [OK] Docker daemon is running"
    PASS=$((PASS + 1))
else
    echo "  [!!] Docker daemon is NOT running"
    echo "  Attempting to start Docker Desktop..."

    # Try OrbStack first, then Docker Desktop
    if [[ -d "$HOME/.orbstack" ]]; then
        open -a OrbStack 2>/dev/null || true
    else
        open -a "Docker Desktop" 2>/dev/null || open -a Docker 2>/dev/null || true
    fi

    echo "  Waiting up to 60s for Docker..."
    for i in $(seq 1 30); do
        if docker info >/dev/null 2>&1; then
            echo "  [OK] Docker daemon started after $((i * 2))s"
            PASS=$((PASS + 1))
            break
        fi
        sleep 2
    done

    if ! docker info >/dev/null 2>&1; then
        echo "  [FAIL] Docker daemon could not be started"
        echo "  Manual action required: Start Docker Desktop or OrbStack manually"
        FAIL=$((FAIL + 1))
        exit 1
    fi
fi

# ── Step 2: Check for container remnants ─────────────────────────────────────

echo ""
echo "--- Step 2: Clean Up Stale Containers ---"

STALE=$(docker ps -a --filter "label=com.docker.compose.project=ekamcore" \
    --filter "status=exited" --filter "status=dead" -q 2>/dev/null | wc -l | tr -d ' ')
if [[ "$STALE" -gt 0 ]]; then
    echo "  Removing $STALE stale containers..."
    docker ps -a --filter "label=com.docker.compose.project=ekamcore" \
        --filter "status=exited" --filter "status=dead" -q | xargs -r docker rm -f 2>/dev/null || true
    echo "  [OK] Stale containers removed"
else
    echo "  [OK] No stale containers found"
fi
PASS=$((PASS + 1))

# ── Step 3: Start all services ───────────────────────────────────────────────

echo ""
echo "--- Step 3: Start Services ---"

cd "$PROJECT_ROOT"
echo "  Running docker compose up -d..."
docker compose up -d 2>&1 | tail -5

# ── Step 4: Wait for health checks ──────────────────────────────────────────

echo ""
echo "--- Step 4: Health Checks ---"

echo "  Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if docker compose exec -T ekamcore-postgres pg_isready -U ekamcore -d ekamcore >/dev/null 2>&1; then
        echo "  [OK] PostgreSQL ready ($((i * 2))s)"
        PASS=$((PASS + 1))
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        echo "  [!!] PostgreSQL not ready after 60s"
        FAIL=$((FAIL + 1))
    fi
done

echo "  Waiting for Redis..."
for i in $(seq 1 15); do
    if docker compose exec -T ekamcore-redis redis-cli -a "${REDIS_PASSWORD:-ekamcore_redis_dev}" ping 2>/dev/null | grep -q PONG; then
        echo "  [OK] Redis ready ($((i * 2))s)"
        PASS=$((PASS + 1))
        break
    fi
    sleep 2
    if [[ $i -eq 15 ]]; then
        echo "  [!!] Redis not ready after 30s"
        FAIL=$((FAIL + 1))
    fi
done

echo "  Waiting for API..."
for i in $(seq 1 30); do
    if curl -sf --max-time 5 http://localhost:8420/health >/dev/null 2>&1; then
        echo "  [OK] API healthy ($((i * 3))s)"
        PASS=$((PASS + 1))
        break
    fi
    sleep 3
    if [[ $i -eq 30 ]]; then
        echo "  [!!] API not healthy after 90s"
        FAIL=$((FAIL + 1))
    fi
done

# ── Step 5: Verify data integrity ───────────────────────────────────────────

echo ""
echo "--- Step 5: Data Integrity Verification ---"

# Count key tables
TABLE_COUNT=$(docker compose exec -T ekamcore-postgres psql -U ekamcore -d ekamcore -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
check "PostgreSQL tables present (${TABLE_COUNT})" test "${TABLE_COUNT:-0}" -gt 5

# Qdrant collections
QDRANT_OK=$(curl -sf --max-time 5 http://localhost:6333/collections 2>/dev/null)
check "Qdrant collections accessible" test -n "$QDRANT_OK"

# ── Step 6: Run full health verification ─────────────────────────────────────

echo ""
echo "--- Step 6: Full Health Verification ---"

if [[ -x "$SCRIPT_DIR/verify_system_health.sh" ]]; then
    bash "$SCRIPT_DIR/verify_system_health.sh" 2>/dev/null && {
        echo "  [OK] Full health check passed"
        PASS=$((PASS + 1))
    } || {
        echo "  [!!] Full health check reported issues (see system_health_report.json)"
        FAIL=$((FAIL + 1))
    }
else
    echo "  [SKIP] verify_system_health.sh not found"
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "================================================================"
echo "  Post-Power-Outage Recovery Complete"
echo "  Passed: $PASS | Failed: $FAIL"
if [[ $FAIL -eq 0 ]]; then
    echo "  Status: ALL CLEAR"
else
    echo "  Status: $FAIL ISSUES REQUIRE ATTENTION"
fi
echo "================================================================"

exit $FAIL

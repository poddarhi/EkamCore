#!/usr/bin/env bash
# EkamCore comprehensive system health check (G-07 / ART-17)
#
# Verifies all services are operational:
#   - Docker containers running with healthy status
#   - Port accessibility for each service
#   - PostgreSQL connectivity and table count
#   - Redis PING
#   - Qdrant health and collection existence
#   - API /health endpoint and full auth flow
#   - PaperlessNGX (optional)
#   - Ollama (optional, native on host)
#
# Usage:
#   ./scripts/dr/verify_system_health.sh
#
# Output:
#   system_health_report.json  (project root)
#
# Must be run from the EkamCore project root.

set -uo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPORT_FILE="${PROJECT_ROOT}/system_health_report.json"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-ekamcore}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ekamcore_dev_password}"
REDIS_PASSWORD="${REDIS_PASSWORD:-ekamcore_redis_dev}"
QDRANT_API_KEY="${QDRANT_API_KEY:-ekamcore_qdrant_dev}"
QDRANT_HOST="${QDRANT_HOST:-localhost:6333}"

export PGPASSWORD="$POSTGRES_PASSWORD"

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# ── JSON builder ──────────────────────────────────────────────────────────────

CHECKS="[]"

add_check() {
    local name="$1" status="$2" details="$3"
    CHECKS=$(echo "$CHECKS" | python3 -c "
import sys, json
checks = json.load(sys.stdin)
checks.append({'check': '$name', 'status': '$status', 'details': '''$details'''})
print(json.dumps(checks))
")
    case "$status" in
        PASS) ((PASS_COUNT++)) ;;
        FAIL) ((FAIL_COUNT++)) ;;
        WARN) ((WARN_COUNT++)) ;;
    esac
    local icon="✓"
    [[ "$status" == "FAIL" ]] && icon="✗"
    [[ "$status" == "WARN" ]] && icon="⚠"
    echo "  [${icon}] ${name}: ${status} — ${details}"
}

# ── Checks ────────────────────────────────────────────────────────────────────

echo "============================================================"
echo "  EkamCore System Health Check"
echo "  $(date)"
echo "============================================================"
echo ""

# --- 1. Docker daemon ---
echo "  [Docker]"
if docker info > /dev/null 2>&1; then
    add_check "docker_daemon" "PASS" "Docker daemon is running"
else
    add_check "docker_daemon" "FAIL" "Docker daemon is not responding"
    # No point continuing if Docker is down
    echo ""
    echo "  FATAL: Docker daemon is not running. Cannot proceed."
    exit 1
fi

# --- 2. Container status ---
echo ""
echo "  [Containers]"

EXPECTED_CONTAINERS=(
    "ekamcore-postgres"
    "ekamcore-redis"
    "ekamcore-qdrant"
    "ekamcore-api"
    "ekamcore-workers"
    "ekamcore-web"
    "ekamcore-proxy"
)
OPTIONAL_CONTAINERS=(
    "ekamcore-paperless"
)

for name in "${EXPECTED_CONTAINERS[@]}"; do
    status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "not_found")
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$name" 2>/dev/null || echo "unknown")

    if [[ "$status" == "running" ]]; then
        if [[ "$health" == "healthy" || "$health" == "no-healthcheck" ]]; then
            add_check "container_${name}" "PASS" "running (health: ${health})"
        else
            add_check "container_${name}" "WARN" "running but health=${health}"
        fi
    else
        add_check "container_${name}" "FAIL" "status=${status}"
    fi
done

for name in "${OPTIONAL_CONTAINERS[@]}"; do
    status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "not_found")
    if [[ "$status" == "running" ]]; then
        add_check "container_${name}" "PASS" "running (optional)"
    else
        add_check "container_${name}" "WARN" "not running (optional service)"
    fi
done

# --- 3. Port accessibility ---
echo ""
echo "  [Ports]"

check_port() {
    local label="$1" host="$2" port="$3"
    if nc -z -w 3 "$host" "$port" 2>/dev/null; then
        add_check "port_${label}" "PASS" "${host}:${port} open"
    else
        add_check "port_${label}" "FAIL" "${host}:${port} not reachable"
    fi
}

check_port "postgres" "localhost" 5432
check_port "redis" "localhost" 6379
check_port "qdrant" "localhost" 6333
check_port "api" "localhost" 8420
check_port "web" "localhost" 3000

# --- 4. PostgreSQL deep check ---
echo ""
echo "  [PostgreSQL]"

PG_TABLE_COUNT=$(docker compose exec -T ekamcore-postgres \
    psql -U "$POSTGRES_USER" -d ekamcore -t -A \
    -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'" \
    2>/dev/null | tr -d '[:space:]') || PG_TABLE_COUNT="0"

if [[ "$PG_TABLE_COUNT" -ge 16 ]]; then
    add_check "postgres_tables" "PASS" "${PG_TABLE_COUNT} tables found (>= 16 expected)"
else
    add_check "postgres_tables" "FAIL" "Only ${PG_TABLE_COUNT} tables (expected >= 16)"
fi

PG_SELECT=$(docker compose exec -T ekamcore-postgres \
    psql -U "$POSTGRES_USER" -d ekamcore -t -A -c "SELECT 1" 2>/dev/null | tr -d '[:space:]')
if [[ "$PG_SELECT" == "1" ]]; then
    add_check "postgres_query" "PASS" "SELECT 1 succeeded"
else
    add_check "postgres_query" "FAIL" "SELECT 1 failed"
fi

# --- 5. Redis check ---
echo ""
echo "  [Redis]"

REDIS_PONG=$(docker compose exec -T ekamcore-redis \
    redis-cli -a "$REDIS_PASSWORD" --no-auth-warning PING 2>/dev/null | tr -d '[:space:]')
if [[ "$REDIS_PONG" == "PONG" ]]; then
    add_check "redis_ping" "PASS" "PONG received"
else
    add_check "redis_ping" "FAIL" "No PONG response"
fi

# --- 6. Qdrant check ---
echo ""
echo "  [Qdrant]"

QDRANT_HEALTH=$(curl -sf -H "api-key: ${QDRANT_API_KEY}" \
    "http://${QDRANT_HOST}/healthz" 2>/dev/null || echo "")
if [[ -n "$QDRANT_HEALTH" ]]; then
    add_check "qdrant_health" "PASS" "Qdrant /healthz OK"
else
    add_check "qdrant_health" "FAIL" "Qdrant /healthz not reachable"
fi

for collection in document_embeddings photo_embeddings face_embeddings; do
    COL_STATUS=$(curl -sf -H "api-key: ${QDRANT_API_KEY}" \
        "http://${QDRANT_HOST}/collections/${collection}" 2>/dev/null || echo "")
    if echo "$COL_STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['status'])" 2>/dev/null | grep -q "green"; then
        add_check "qdrant_collection_${collection}" "PASS" "collection exists, status=green"
    elif [[ -n "$COL_STATUS" ]]; then
        add_check "qdrant_collection_${collection}" "WARN" "collection exists but status may not be green"
    else
        add_check "qdrant_collection_${collection}" "WARN" "collection not found (may not be created yet)"
    fi
done

# --- 7. API health endpoint ---
echo ""
echo "  [API]"

API_HEALTH=$(curl -sf "http://localhost:8420/health" 2>/dev/null || echo "")
if [[ -n "$API_HEALTH" ]]; then
    API_STATUS=$(echo "$API_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
    if [[ "$API_STATUS" == "healthy" ]]; then
        add_check "api_health" "PASS" "API reports healthy"
    else
        add_check "api_health" "WARN" "API reports status=${API_STATUS}"
    fi
else
    add_check "api_health" "FAIL" "API /health not reachable"
fi

# --- 8. API auth flow ---
echo ""
echo "  [Auth Flow]"

# Try login with test credentials (may fail if no test user exists — that's OK)
AUTH_RESP=$(curl -sf -X POST "http://localhost:8420/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@ekamcore.dev","password":"admin"}' 2>/dev/null || echo "")
if echo "$AUTH_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'access_token' in d" 2>/dev/null; then
    add_check "api_auth_flow" "PASS" "Login endpoint responds with JWT"
else
    # Not necessarily a failure — test user may not exist
    add_check "api_auth_flow" "WARN" "Login test skipped (no test user or wrong credentials)"
fi

# --- 9. PaperlessNGX (optional) ---
echo ""
echo "  [Paperless (optional)]"

PAPERLESS_STATUS=$(docker inspect --format='{{.State.Status}}' ekamcore-paperless 2>/dev/null || echo "not_found")
if [[ "$PAPERLESS_STATUS" == "running" ]]; then
    PAPERLESS_API=$(docker compose exec -T ekamcore-paperless \
        curl -sf http://localhost:8000/api/ 2>/dev/null || echo "")
    if [[ -n "$PAPERLESS_API" ]]; then
        add_check "paperless_health" "PASS" "Paperless API responding"
    else
        add_check "paperless_health" "WARN" "Paperless running but API not responding"
    fi
else
    add_check "paperless_health" "WARN" "Paperless not running (optional)"
fi

# --- 10. Ollama (optional, native on host) ---
echo ""
echo "  [Ollama (optional)]"

OLLAMA_TAGS=$(curl -sf "http://localhost:11434/api/tags" 2>/dev/null || echo "")
if [[ -n "$OLLAMA_TAGS" ]]; then
    MODEL_COUNT=$(echo "$OLLAMA_TAGS" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "0")
    add_check "ollama_health" "PASS" "Ollama running with ${MODEL_COUNT} models"
else
    add_check "ollama_health" "WARN" "Ollama not reachable (optional — runs natively on host)"
fi

# ── Write report ──────────────────────────────────────────────────────────────

TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
OVERALL="HEALTHY"
[[ "$WARN_COUNT" -gt 0 ]] && OVERALL="DEGRADED"
[[ "$FAIL_COUNT" -gt 0 ]] && OVERALL="UNHEALTHY"

python3 -c "
import json, sys
report = {
    'timestamp': '${TIMESTAMP}',
    'overall_status': '${OVERALL}',
    'summary': {
        'total': ${TOTAL},
        'passed': ${PASS_COUNT},
        'failed': ${FAIL_COUNT},
        'warnings': ${WARN_COUNT}
    },
    'checks': ${CHECKS}
}
with open('${REPORT_FILE}', 'w') as f:
    json.dump(report, f, indent=2)
print(json.dumps(report['summary'], indent=2))
"

echo ""
echo "============================================================"
echo "  Overall: ${OVERALL}"
echo "  Passed: ${PASS_COUNT}  |  Failed: ${FAIL_COUNT}  |  Warnings: ${WARN_COUNT}"
echo "  Report: ${REPORT_FILE}"
echo "============================================================"

[[ "$FAIL_COUNT" -gt 0 ]] && exit 1
exit 0

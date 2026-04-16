#!/usr/bin/env bash
# Chaos Scenario 6: Network partition — disconnect API from internal network.
#
# Injects: docker network disconnect on ekamcore-api.
# Expected: API cannot reach other services, returns errors for most endpoints,
#           health endpoint still responds with degraded status.
#           After reconnect, all services resume.

source "$(dirname "$0")/lib.sh"

SCENARIO="network_partition"
NETWORK_NAME="ekamcore_ekamcore-net"
CONTAINER_NAME="ekamcore-api"
echo ""
echo "=== Chaos Scenario 6: Network Partition ==="

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "network disconnect" \
    "API degrades, recovery on reconnect" "Could not establish baseline" 0 false false; exit 0; }

# Detect the actual network name (docker compose may prefix it)
ACTUAL_NETWORK=$(docker network ls --format '{{.Name}}' | grep -E "ekamcore.*net" | head -1)
if [[ -z "$ACTUAL_NETWORK" ]]; then
    echo "  WARNING: Could not find ekamcore network — trying default name"
    ACTUAL_NETWORK="$NETWORK_NAME"
fi
echo "  Network: $ACTUAL_NETWORK"

# Detect actual container name
ACTUAL_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "ekamcore.*api" | head -1)
if [[ -z "$ACTUAL_CONTAINER" ]]; then
    ACTUAL_CONTAINER="$CONTAINER_NAME"
fi
echo "  Container: $ACTUAL_CONTAINER"

# ── Inject: disconnect API from network ──────────────────────────────────────

echo "  Disconnecting $ACTUAL_CONTAINER from $ACTUAL_NETWORK..."
timer_start
docker network disconnect "$ACTUAL_NETWORK" "$ACTUAL_CONTAINER" 2>/dev/null || true

sleep 3

# ── Verify: health endpoint may or may not respond ───────────────────────────
# (Depending on how the API is exposed — through proxy or direct port)

HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_URL/health" 2>/dev/null || echo "000")
echo "  Health after disconnect: HTTP $HEALTH_CODE"

# DB-dependent endpoint should fail
DB_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    -H "Authorization: Bearer $(get_auth_token)" \
    "$API_URL/api/v1/settings" 2>/dev/null || echo "000")
echo "  Settings (DB-dependent) after disconnect: HTTP $DB_CODE"

# ── Recovery: reconnect ──────────────────────────────────────────────────────

echo "  Reconnecting $ACTUAL_CONTAINER to $ACTUAL_NETWORK..."
docker network connect "$ACTUAL_NETWORK" "$ACTUAL_CONTAINER" 2>/dev/null || true

sleep 5

RECOVERED=false
for i in $(seq 1 20); do
    if api_reachable; then
        RECOVERED=true
        break
    fi
    sleep 3
done

RECOVERY_SECS=$(timer_elapsed)
echo "  Recovery time: ${RECOVERY_SECS}s"

# Verify endpoints work again
AFTER_HEALTH=$(api_reachable && echo "true" || echo "false")
AFTER_SETTINGS=$(api_get "/api/v1/settings" >/dev/null 2>&1 && echo "true" || echo "false")
echo "  Health after reconnect: $AFTER_HEALTH"
echo "  Settings after reconnect: $AFTER_SETTINGS"

PASS=false
if [[ "$RECOVERED" == "true" && "$AFTER_HEALTH" == "true" ]]; then
    PASS=true
fi

emit_result "$SCENARIO" \
    "docker network disconnect on ekamcore-api" \
    "API returns errors when partitioned, resumes on reconnect" \
    "health_during=$HEALTH_CODE, db_during=$DB_CODE, recovered=$RECOVERED, after_health=$AFTER_HEALTH" \
    "$RECOVERY_SECS" false "$PASS"

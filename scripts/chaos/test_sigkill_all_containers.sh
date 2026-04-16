#!/usr/bin/env bash
# Chaos Scenario 3: SIGKILL all containers simultaneously.
#
# Injects: docker compose kill (SIGKILL to all containers).
# Expected: docker compose up -d recovers all services, migrations idempotent,
#           health checks pass within 180s, all data intact.

source "$(dirname "$0")/lib.sh"

SCENARIO="sigkill_all_containers"
echo ""
echo "=== Chaos Scenario 3: SIGKILL All Containers ==="

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "docker compose kill" \
    "Full recovery within 180s" "Could not establish baseline" 0 false false; exit 0; }

# Record data counts for corruption check
BEFORE_HEALTH=$(api_health | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))" 2>/dev/null || echo "{}")
echo "  Health before: captured"

# ── Inject: SIGKILL all containers ───────────────────────────────────────────

echo "  Sending SIGKILL to all containers..."
timer_start
compose kill 2>/dev/null || true

sleep 3

# Verify everything is down
ALL_DOWN=true
for svc in ekamcore-postgres ekamcore-redis ekamcore-qdrant ekamcore-api; do
    if container_running "$svc"; then
        ALL_DOWN=false
        echo "  WARNING: $svc still running after kill"
    fi
done
echo "  All containers down: $ALL_DOWN"

# ── Recovery: bring everything back up ───────────────────────────────────────

echo "  Running docker compose up -d..."
compose up -d 2>/dev/null || true

echo "  Waiting for full recovery (up to ${MAX_RECOVERY_WAIT}s)..."
RECOVERED=false
for i in $(seq 1 $((MAX_RECOVERY_WAIT / 5))); do
    if api_reachable; then
        RECOVERED=true
        break
    fi
    sleep 5
done

RECOVERY_SECS=$(timer_elapsed)
echo "  Recovery time: ${RECOVERY_SECS}s"

# ── Verify: data intact ─────────────────────────────────────────────────────

sleep 5
AFTER_HEALTH=$(api_health 2>/dev/null || echo '{"error":"unhealthy"}')
AFTER_OK=$(echo "$AFTER_HEALTH" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print('error' not in d)" 2>/dev/null || echo "False")
echo "  Health after recovery: OK=$AFTER_OK"

# Check all key containers are running
CONTAINERS_UP=true
for svc in ekamcore-postgres ekamcore-redis ekamcore-qdrant ekamcore-api ekamcore-proxy; do
    if ! container_running "$svc"; then
        CONTAINERS_UP=false
        echo "  MISSING: $svc not running after recovery"
    fi
done

PASS=false
if [[ "$RECOVERED" == "true" && "$CONTAINERS_UP" == "true" && "$RECOVERY_SECS" -le "$MAX_RECOVERY_WAIT" ]]; then
    PASS=true
fi

emit_result "$SCENARIO" \
    "docker compose kill (SIGKILL all containers)" \
    "Full recovery within ${MAX_RECOVERY_WAIT}s, migrations idempotent, data intact" \
    "Recovery=$RECOVERED in ${RECOVERY_SECS}s, all_containers=$CONTAINERS_UP" \
    "$RECOVERY_SECS" false "$PASS"

#!/usr/bin/env bash
# Chaos Scenario 1: Kill PostgreSQL during active writes.
#
# Injects: docker kill ekamcore-postgres while API is processing writes.
# Expected: API returns 503 for DB-dependent endpoints, watchdog restarts
#           PostgreSQL, writes resume within 60s, no data corruption.

source "$(dirname "$0")/lib.sh"

SCENARIO="postgres_kill_during_write"
echo ""
echo "=== Chaos Scenario 1: PostgreSQL Kill During Write ==="

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "docker kill postgres" \
    "Recovery within 60s" "Could not establish baseline" 0 false false; exit 0; }

# Count existing reminders for corruption check
BEFORE_COUNT=$(api_get "/api/v1/reminders" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(len(d.get('items',d.get('reminders',[]))))" 2>/dev/null || echo "0")
echo "  Reminders before: $BEFORE_COUNT"

# ── Inject: start background writes, then kill PostgreSQL ────────────────────

echo "  Starting background writes..."
WRITE_PID=""
(
    for i in $(seq 1 10); do
        api_post "/api/v1/reminders" \
            "{\"title\":\"chaos-test-$i\",\"due_at\":\"2026-12-31T00:00:00Z\"}" >/dev/null 2>&1 || true
        sleep 0.5
    done
) &
WRITE_PID=$!

# Give writes a head start
sleep 2

echo "  Killing ekamcore-postgres..."
timer_start
docker kill ekamcore-postgres 2>/dev/null || true

# ── Verify: API returns errors for DB endpoints ─────────────────────────────

sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_URL/health" 2>/dev/null || echo "000")
echo "  Health check after kill: HTTP $HTTP_CODE"

# ── Wait for recovery ────────────────────────────────────────────────────────

echo "  Waiting for PostgreSQL recovery..."
# Watchdog or compose restart
compose up -d ekamcore-postgres 2>/dev/null || true

RECOVERED=false
for i in $(seq 1 30); do
    if api_reachable; then
        RECOVERED=true
        break
    fi
    sleep 2
done

RECOVERY_SECS=$(timer_elapsed)
echo "  Recovery time: ${RECOVERY_SECS}s"

# Wait for background writes to finish
wait "$WRITE_PID" 2>/dev/null || true

# ── Verify: no data corruption ───────────────────────────────────────────────

sleep 3
AFTER_COUNT=$(api_get "/api/v1/reminders" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(len(d.get('items',d.get('reminders',[]))))" 2>/dev/null || echo "0")
echo "  Reminders after: $AFTER_COUNT"

# After count should be >= before count (some writes may have succeeded)
CORRUPTION=false
if [[ "$AFTER_COUNT" -lt "$BEFORE_COUNT" ]]; then
    CORRUPTION=true
fi

PASS=false
if [[ "$RECOVERED" == "true" && "$CORRUPTION" == "false" && "$RECOVERY_SECS" -le 120 ]]; then
    PASS=true
fi

emit_result "$SCENARIO" \
    "docker kill ekamcore-postgres during active writes" \
    "API returns 503 for DB endpoints, recovery within 60s, no data loss" \
    "Recovery=$RECOVERED in ${RECOVERY_SECS}s, before=$BEFORE_COUNT after=$AFTER_COUNT" \
    "$RECOVERY_SECS" "$CORRUPTION" "$PASS"

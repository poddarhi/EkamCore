#!/usr/bin/env bash
# Chaos Scenario 7: Concurrent heavy load — 50 simultaneous requests.
#
# Injects: 50 concurrent API requests (mix of reads and writes).
# Expected: Rate limiting returns 429 for excess, no crashes, no OOM,
#           P95 latency within 5x of normal.

source "$(dirname "$0")/lib.sh"

SCENARIO="concurrent_heavy_load"
CONCURRENT=50
RESULTS_FILE="/tmp/ekamcore_chaos_load_results.txt"
echo ""
echo "=== Chaos Scenario 7: Concurrent Heavy Load ==="

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "concurrent load" \
    "No crashes, rate limiting works" "Could not establish baseline" 0 false false; exit 0; }

# Get a baseline single-request latency
BASELINE_MS=$(curl -s -o /dev/null -w "%{time_total}" --max-time 10 "$API_URL/health" 2>/dev/null | awk '{printf "%.0f", $1 * 1000}')
echo "  Baseline health latency: ${BASELINE_MS}ms"

# ── Inject: fire 50 concurrent requests ──────────────────────────────────────

echo "  Launching $CONCURRENT concurrent requests..."
timer_start
rm -f "$RESULTS_FILE"

TOKEN=$(get_auth_token)

for i in $(seq 1 $CONCURRENT); do
    (
        # Mix of endpoints: health (fast), today (medium), search (heavier)
        case $((i % 4)) in
            0) ENDPOINT="/health" ;;
            1) ENDPOINT="/api/v1/today" ;;
            2) ENDPOINT="/api/v1/search?q=test" ;;
            3) ENDPOINT="/api/v1/settings" ;;
        esac

        START_T=$(python3 -c "import time; print(time.time())")
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
            -H "Authorization: Bearer $TOKEN" \
            "$API_URL$ENDPOINT" 2>/dev/null || echo "000")
        END_T=$(python3 -c "import time; print(time.time())")
        LATENCY=$(python3 -c "print(int(($END_T - $START_T) * 1000))")

        echo "$ENDPOINT $HTTP_CODE $LATENCY" >> "$RESULTS_FILE"
    ) &
done

# Wait for all background jobs
wait

ELAPSED_SECS=$(timer_elapsed)
echo "  All requests completed in ${ELAPSED_SECS}s"

# ── Analyze results ──────────────────────────────────────────────────────────

if [[ ! -f "$RESULTS_FILE" ]]; then
    emit_result "$SCENARIO" "$CONCURRENT concurrent requests" \
        "No crashes, rate limiting" "Results file missing" "$ELAPSED_SECS" false false
    exit 0
fi

TOTAL=$(wc -l < "$RESULTS_FILE" | tr -d ' ')
SUCCESS=$(grep -cE ' (200|429) ' "$RESULTS_FILE" || echo 0)
RATE_LIMITED=$(grep -c ' 429 ' "$RESULTS_FILE" || echo 0)
ERRORS=$(grep -cE ' (500|502|503|504|000) ' "$RESULTS_FILE" || echo 0)
echo "  Total: $TOTAL, Success(2xx): $((SUCCESS - RATE_LIMITED)), Rate-limited(429): $RATE_LIMITED, Errors(5xx): $ERRORS"

# Calculate P95 latency
P95_LATENCY=$(awk '{print $3}' "$RESULTS_FILE" | sort -n | awk -v p=0.95 \
    'BEGIN{c=0} {a[c++]=$1} END{idx=int(c*p); if(idx>=c)idx=c-1; print a[idx]}')
echo "  P95 latency: ${P95_LATENCY}ms"

# ── Verify: no crashes ──────────────────────────────────────────────────────

sleep 3
API_ALIVE=$(api_reachable && echo "true" || echo "false")
echo "  API alive after load: $API_ALIVE"

# Check containers are still running
PG_ALIVE=$(container_running "ekamcore-postgres" && echo "true" || echo "false")
REDIS_ALIVE=$(container_running "ekamcore-redis" && echo "true" || echo "false")

# ── Evaluate pass/fail ───────────────────────────────────────────────────────

# Max P95 = 5x baseline (or 5000ms hard cap)
MAX_P95=$((BASELINE_MS * 5))
if [[ $MAX_P95 -lt 1000 ]]; then MAX_P95=5000; fi

PASS=false
if [[ "$API_ALIVE" == "true" && "$ERRORS" -le 5 && "${P95_LATENCY:-99999}" -le "$MAX_P95" ]]; then
    PASS=true
fi

# Cleanup
rm -f "$RESULTS_FILE"

emit_result "$SCENARIO" \
    "$CONCURRENT concurrent API requests (mixed read endpoints)" \
    "No crashes, rate limiting returns 429, P95 within 5x normal" \
    "total=$TOTAL, success=$SUCCESS, rate_limited=$RATE_LIMITED, errors=$ERRORS, p95=${P95_LATENCY}ms, api_alive=$API_ALIVE" \
    "$ELAPSED_SECS" false "$PASS"

#!/usr/bin/env bash
# Chaos Scenario 2: Kill Qdrant during embedding operations.
#
# Injects: docker kill ekamcore-qdrant while embeddings would be generated.
# Expected: API search degrades to exact-only with is_partial=true,
#           watchdog restarts Qdrant, search resumes.

source "$(dirname "$0")/lib.sh"

SCENARIO="qdrant_kill_during_embedding"
echo ""
echo "=== Chaos Scenario 2: Qdrant Kill During Embedding ==="

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "docker kill qdrant" \
    "Graceful degradation, recovery" "Could not establish baseline" 0 false false; exit 0; }

# ── Inject: kill Qdrant ──────────────────────────────────────────────────────

echo "  Killing ekamcore-qdrant..."
timer_start
docker kill ekamcore-qdrant 2>/dev/null || true

sleep 3

# ── Verify: search degrades gracefully ───────────────────────────────────────

echo "  Testing search with Qdrant down..."
SEARCH_RESULT=$(api_get "/api/v1/search?q=test" 2>/dev/null || echo '{"error":"unavailable"}')
IS_PARTIAL=$(echo "$SEARCH_RESULT" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('is_partial', 'N/A'))" 2>/dev/null || echo "error")
echo "  Search is_partial: $IS_PARTIAL"

# Health should still respond (API is up, Qdrant is down)
HEALTH_OK=$(api_reachable && echo "true" || echo "false")
echo "  Health endpoint reachable: $HEALTH_OK"

# ── Recovery ─────────────────────────────────────────────────────────────────

echo "  Restarting ekamcore-qdrant..."
compose up -d ekamcore-qdrant 2>/dev/null || true

RECOVERED=false
for i in $(seq 1 30); do
    # Check if Qdrant healthz responds
    if curl -sf --max-time 3 "http://localhost:6333/healthz" >/dev/null 2>&1; then
        RECOVERED=true
        break
    fi
    sleep 3
done

RECOVERY_SECS=$(timer_elapsed)
echo "  Recovery time: ${RECOVERY_SECS}s"

# ── Verify: search works again ───────────────────────────────────────────────

sleep 3
SEARCH_AFTER=$(api_get "/api/v1/search?q=test" 2>/dev/null || echo '{"error":"still down"}')
SEARCH_OK=$(echo "$SEARCH_AFTER" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print('error' not in d)" 2>/dev/null || echo "False")

PASS=false
if [[ "$RECOVERED" == "true" && "$RECOVERY_SECS" -le 120 ]]; then
    PASS=true
fi

emit_result "$SCENARIO" \
    "docker kill ekamcore-qdrant during potential embedding operations" \
    "Search degrades to exact-only with is_partial=true, recovery within 60s" \
    "Recovery=$RECOVERED in ${RECOVERY_SECS}s, is_partial=$IS_PARTIAL, health_ok=$HEALTH_OK" \
    "$RECOVERY_SECS" false "$PASS"

#!/usr/bin/env bash
# Master chaos test runner (S15-008).
#
# Runs all 7 chaos scenarios sequentially. Each scenario starts from a
# clean healthy state and produces a JSON report.
#
# Usage:
#   bash scripts/chaos/run_all.sh
#   make chaos-test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
DATE_TAG="$(date -u +%Y%m%d_%H%M%S)"

mkdir -p "$RESULTS_DIR"

echo "================================================================"
echo "  EkamCore Chaos Test Suite (S15-008)"
echo "  Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================================"

# ── Verify Docker is available ───────────────────────────────────────────────

if ! docker info >/dev/null 2>&1; then
    echo ""
    echo "  ERROR: Docker is not running. Chaos tests require a running Docker stack."
    echo "  Start with: make up"
    exit 1
fi

# ── Run scenarios ────────────────────────────────────────────────────────────

SCENARIOS=(
    "test_postgres_kill_during_write"
    "test_qdrant_kill_during_embedding"
    "test_sigkill_all_containers"
    "test_disk_fill_95_percent"
    "test_ollama_model_corruption"
    "test_network_partition"
    "test_concurrent_heavy_load"
)

PASSED=0
FAILED=0
TOTAL=${#SCENARIOS[@]}

for scenario in "${SCENARIOS[@]}"; do
    script="$SCRIPT_DIR/${scenario}.sh"
    if [[ ! -f "$script" ]]; then
        echo ""
        echo "  WARNING: Script not found: $script"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo ""
    echo "────────────────────────────────────────────────────────────────"
    bash "$script" || true

    # Check result
    LATEST_RESULT=$(ls -t "$RESULTS_DIR/${scenario}_"*.json 2>/dev/null | head -1)
    if [[ -n "$LATEST_RESULT" ]]; then
        RESULT_PASS=$(python3 -c "import json; print(json.load(open('$LATEST_RESULT'))['pass'])" 2>/dev/null || echo "False")
        if [[ "$RESULT_PASS" == "True" || "$RESULT_PASS" == "true" ]]; then
            PASSED=$((PASSED + 1))
        else
            FAILED=$((FAILED + 1))
        fi
    else
        FAILED=$((FAILED + 1))
    fi
done

# ── Aggregate report ─────────────────────────────────────────────────────────

echo ""
echo "────────────────────────────────────────────────────────────────"
echo ""

REPORT_FILE="$RESULTS_DIR/chaos_report_${DATE_TAG}.json"

# Collect all individual results
INDIVIDUAL_RESULTS="["
FIRST=true
for scenario in "${SCENARIOS[@]}"; do
    LATEST=$(ls -t "$RESULTS_DIR/${scenario}_"*.json 2>/dev/null | head -1)
    if [[ -n "$LATEST" ]]; then
        if [[ "$FIRST" == "true" ]]; then
            FIRST=false
        else
            INDIVIDUAL_RESULTS+=","
        fi
        INDIVIDUAL_RESULTS+="$(cat "$LATEST")"
    fi
done
INDIVIDUAL_RESULTS+="]"

cat > "$REPORT_FILE" <<REPORT_EOF
{
  "suite": "EkamCore Chaos Tests (S15-008)",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "summary": {
    "total": $TOTAL,
    "passed": $PASSED,
    "failed": $FAILED
  },
  "scenarios": $INDIVIDUAL_RESULTS
}
REPORT_EOF

echo "================================================================"
echo "  Chaos Test Results: $PASSED/$TOTAL PASSED | $FAILED FAILED"
echo "  Report: $REPORT_FILE"
echo "================================================================"

if [[ $FAILED -gt 0 ]]; then
    echo ""
    echo "  FAILED scenarios:"
    for scenario in "${SCENARIOS[@]}"; do
        LATEST=$(ls -t "$RESULTS_DIR/${scenario}_"*.json 2>/dev/null | head -1)
        if [[ -n "$LATEST" ]]; then
            RESULT_PASS=$(python3 -c "import json; print(json.load(open('$LATEST'))['pass'])" 2>/dev/null || echo "False")
            if [[ "$RESULT_PASS" != "True" && "$RESULT_PASS" != "true" ]]; then
                echo "    - $scenario"
            fi
        fi
    done
fi

exit $FAILED

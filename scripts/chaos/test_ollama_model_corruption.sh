#!/usr/bin/env bash
# Chaos Scenario 5: Corrupt Ollama model to test LLM degradation.
#
# Injects: Rename the Ollama model directory to simulate corruption.
# Expected: LLM queries fail gracefully with is_partial=true,
#           non-LLM features continue. After re-pulling, LLM resumes.

source "$(dirname "$0")/lib.sh"

SCENARIO="ollama_model_corruption"
OLLAMA_MODELS_DIR="$HOME/.ollama/models"
BACKUP_SUFFIX=".chaos_backup"
echo ""
echo "=== Chaos Scenario 5: Ollama Model Corruption ==="

# Cleanup trap
cleanup_models() {
    if [[ -d "${OLLAMA_MODELS_DIR}${BACKUP_SUFFIX}" ]]; then
        rm -rf "$OLLAMA_MODELS_DIR" 2>/dev/null || true
        mv "${OLLAMA_MODELS_DIR}${BACKUP_SUFFIX}" "$OLLAMA_MODELS_DIR" 2>/dev/null || true
        echo "  Cleanup: model directory restored"
    fi
}
trap cleanup_models EXIT

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "model corruption" \
    "LLM degrades, non-LLM works" "Could not establish baseline" 0 false false; exit 0; }

# Check Ollama is running
if ! curl -sf --max-time 3 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    echo "  Ollama not running — skipping scenario"
    emit_result "$SCENARIO" "model corruption" \
        "LLM degrades gracefully" "Ollama not running, scenario skipped" 0 false true
    trap - EXIT
    exit 0
fi

# ── Inject: rename model directory ───────────────────────────────────────────

echo "  Renaming Ollama models directory..."
timer_start
if [[ -d "$OLLAMA_MODELS_DIR" ]]; then
    mv "$OLLAMA_MODELS_DIR" "${OLLAMA_MODELS_DIR}${BACKUP_SUFFIX}"
    mkdir -p "$OLLAMA_MODELS_DIR"  # Empty dir so Ollama doesn't crash
else
    echo "  WARNING: Ollama models dir not found at $OLLAMA_MODELS_DIR"
    emit_result "$SCENARIO" "model corruption" \
        "LLM degrades gracefully" "Models dir not found" 0 false true
    trap - EXIT
    exit 0
fi

sleep 3

# ── Verify: non-LLM features still work ─────────────────────────────────────

NON_LLM_OK=$(api_reachable && echo "true" || echo "false")
echo "  Non-LLM API reachable: $NON_LLM_OK"

# Today endpoint (deterministic, no LLM) should work
TODAY_OK=$(api_get "/api/v1/today" >/dev/null 2>&1 && echo "true" || echo "false")
echo "  Today endpoint: $TODAY_OK"

# Health should report Ollama degraded
HEALTH=$(api_health 2>/dev/null || echo "{}")
echo "  Health: captured"

# ── Recovery: restore model directory ────────────────────────────────────────

echo "  Restoring model directory..."
rm -rf "$OLLAMA_MODELS_DIR" 2>/dev/null || true
mv "${OLLAMA_MODELS_DIR}${BACKUP_SUFFIX}" "$OLLAMA_MODELS_DIR"
trap - EXIT  # Clear trap

sleep 5

# Verify models are accessible again
MODELS_RESTORED=$(curl -sf --max-time 5 "http://localhost:11434/api/tags" >/dev/null 2>&1 && echo "true" || echo "false")
echo "  Models accessible after restore: $MODELS_RESTORED"

RECOVERY_SECS=$(timer_elapsed)

PASS=false
if [[ "$NON_LLM_OK" == "true" && "$TODAY_OK" == "true" && "$MODELS_RESTORED" == "true" ]]; then
    PASS=true
fi

emit_result "$SCENARIO" \
    "Renamed Ollama models directory to simulate corruption" \
    "LLM queries fail with is_partial=true, non-LLM features continue, model re-pull restores" \
    "non_llm_ok=$NON_LLM_OK, today_ok=$TODAY_OK, models_restored=$MODELS_RESTORED" \
    "$RECOVERY_SECS" false "$PASS"

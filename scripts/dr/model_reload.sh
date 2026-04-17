#!/usr/bin/env bash
# EkamCore Model Reload/Repair (S15-010 / ART-17)
#
# Reloads AI models when corrupted or missing:
#   - Ollama models (nomic-embed-text, phi3:mini, llama3.1:8b)
#   - InsightFace buffalo_l pack (face detection/recognition)
#
# Usage:
#   ./scripts/dr/model_reload.sh [--ollama] [--face] [--all]
#
# RTO target: < 5 minutes (Ollama), < 10 minutes (face models)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RELOAD_OLLAMA=false
RELOAD_FACE=false

# Parse args
if [[ $# -eq 0 || "$*" == *"--all"* ]]; then
    RELOAD_OLLAMA=true
    RELOAD_FACE=true
else
    [[ "$*" == *"--ollama"* ]] && RELOAD_OLLAMA=true
    [[ "$*" == *"--face"* ]] && RELOAD_FACE=true
fi

echo "================================================================"
echo "  EkamCore Model Reload"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Ollama: $RELOAD_OLLAMA | Face: $RELOAD_FACE"
echo "================================================================"

PASS=0
FAIL=0

# ── Ollama Models ─────────────���──────────────────────────────────────────────

if [[ "$RELOAD_OLLAMA" == "true" ]]; then
    echo ""
    echo "--- Ollama Models ---"

    # Check Ollama is running
    if ! curl -sf --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "  Ollama not running. Starting..."
        ollama serve >/dev/null 2>&1 &
        sleep 5
        if ! curl -sf --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
            echo "  [FAIL] Could not start Ollama"
            FAIL=$((FAIL + 1))
        fi
    fi

    MODELS=(
        "nomic-embed-text"  # Embedding model (768-dim)
        "phi3:mini"         # Fast inference (query classify, simple QA)
        "llama3.1:8b"       # Large inference (complex synthesis)
    )

    for model in "${MODELS[@]}"; do
        echo "  Reloading $model..."

        # Remove existing (may be corrupted)
        ollama rm "$model" 2>/dev/null || true

        # Re-pull
        if ollama pull "$model" 2>&1 | tail -1; then
            echo "  [OK] $model pulled successfully"
            PASS=$((PASS + 1))
        else
            echo "  [!!] $model pull failed"
            FAIL=$((FAIL + 1))
        fi
    done

    # Verify models are loadable
    echo ""
    echo "  Verifying models..."
    LOADED=$(curl -sf --max-time 5 http://localhost:11434/api/tags 2>/dev/null)
    for model in "${MODELS[@]}"; do
        MODEL_BASE="${model%%:*}"
        if echo "$LOADED" | grep -q "$MODEL_BASE"; then
            echo "  [OK] $model available"
        else
            echo "  [!!] $model NOT found in Ollama"
        fi
    done
fi

# ── InsightFace Models ───────────────��───────────────────────────────────────

if [[ "$RELOAD_FACE" == "true" ]]; then
    echo ""
    echo "--- InsightFace Models ---"

    DOWNLOAD_SCRIPT="$PROJECT_ROOT/scripts/face/download_models.sh"
    if [[ -x "$DOWNLOAD_SCRIPT" ]]; then
        echo "  Running download_models.sh (with SHA-256 verification)..."
        if bash "$DOWNLOAD_SCRIPT" 2>&1 | tail -5; then
            echo "  [OK] InsightFace models downloaded and verified"
            PASS=$((PASS + 1))
        else
            echo "  [!!] InsightFace model download failed"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  [SKIP] download_models.sh not found at $DOWNLOAD_SCRIPT"
        echo "  Run: make download-face-models"
    fi
fi

# ── Restart workers to pick up new models ────────��───────────────────────────

echo ""
echo "--- Restart Workers ---"

cd "$PROJECT_ROOT"
docker compose restart ekamcore-workers 2>/dev/null && {
    echo "  [OK] Workers restarted"
    PASS=$((PASS + 1))
} || {
    echo "  [!!] Worker restart failed (may not be running)"
}

# Wait for API health
sleep 5
if curl -sf --max-time 5 http://localhost:8420/health >/dev/null 2>&1; then
    echo "  [OK] API healthy after model reload"
    PASS=$((PASS + 1))
else
    echo "  [!!] API not healthy (may need more time)"
fi

# ── Summary ──────────────────────────────────────────────────────��───────────

echo ""
echo "================================================================"
echo "  Model Reload Complete"
echo "  Passed: $PASS | Failed: $FAIL"
if [[ $FAIL -eq 0 ]]; then
    echo "  Status: ALL MODELS RELOADED"
else
    echo "  Status: $FAIL ISSUES — check above"
fi
echo "================================================================"

exit $FAIL

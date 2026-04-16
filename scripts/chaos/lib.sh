#!/usr/bin/env bash
# Shared helper library for chaos test scripts (S15-008).
# Source this from each scenario: source "$(dirname "$0")/lib.sh"

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
DATE_TAG="$(date -u +%Y%m%d_%H%M%S)"

mkdir -p "$RESULTS_DIR"

# ── Configuration ────────────────────────────────────────────────────────────

API_URL="${API_URL:-http://localhost:8420}"
API_EMAIL="${API_EMAIL:-admin@ekamcore.dev}"
API_PASSWORD="${API_PASSWORD:-admin123}"
COMPOSE_CMD="docker compose -f $PROJECT_ROOT/docker-compose.yml"
MAX_RECOVERY_WAIT="${MAX_RECOVERY_WAIT:-180}"

# ── Auth token ───────────────────────────────────────────────────────────────

_TOKEN=""

get_auth_token() {
    if [[ -n "$_TOKEN" ]]; then
        echo "$_TOKEN"
        return
    fi
    _TOKEN=$(curl -sf --max-time 10 "$API_URL/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$API_EMAIL\",\"password\":\"$API_PASSWORD\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
    echo "$_TOKEN"
}

# ── API helpers ──────────────────────────────────────────────────────────────

api_get() {
    local path="$1"
    local token
    token=$(get_auth_token)
    curl -sf --max-time 10 "$API_URL$path" \
        -H "Authorization: Bearer $token" 2>/dev/null
}

api_post() {
    local path="$1"
    local body="${2:-{}}"
    local token
    token=$(get_auth_token)
    curl -sf --max-time 10 "$API_URL$path" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d "$body" 2>/dev/null
}

api_health() {
    curl -sf --max-time 5 "$API_URL/health" 2>/dev/null
}

api_reachable() {
    curl -sf --max-time 5 -o /dev/null "$API_URL/health" 2>/dev/null
    return $?
}

# ── Docker helpers ───────────────────────────────────────────────────────────

compose() {
    $COMPOSE_CMD "$@"
}

container_running() {
    local name="$1"
    docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null | grep -q "true"
}

wait_container_healthy() {
    local name="$1"
    local timeout="${2:-$MAX_RECOVERY_WAIT}"
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if container_running "$name"; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# ── Health & recovery ────────────────────────────────────────────────────────

wait_all_healthy() {
    local timeout="${1:-$MAX_RECOVERY_WAIT}"
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if api_reachable; then
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    return 1
}

ensure_healthy_baseline() {
    echo "  Ensuring all services are healthy..."
    compose up -d --quiet-pull 2>/dev/null || true
    if ! wait_all_healthy 120; then
        echo "  WARNING: Could not establish healthy baseline within 120s"
        return 1
    fi
    echo "  Baseline healthy."
    return 0
}

# ── Result emission ──────────────────────────────────────────────────────────

emit_result() {
    local scenario="$1"
    local injected="$2"
    local expected="$3"
    local actual="$4"
    local recovery_secs="$5"
    local corruption="$6"
    local pass="$7"
    local outfile="$RESULTS_DIR/${scenario}_${DATE_TAG}.json"

    cat > "$outfile" <<RESULT_EOF
{
  "scenario": "$scenario",
  "injected_failure": "$injected",
  "expected_behavior": "$expected",
  "actual_behavior": "$actual",
  "recovery_time_seconds": $recovery_secs,
  "data_corruption": $corruption,
  "pass": $pass,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
RESULT_EOF
    echo "  Result: $outfile"
    if [[ "$pass" == "true" ]]; then
        echo "  [PASS] $scenario"
    else
        echo "  [FAIL] $scenario"
    fi
}

# ── Timer ────────────────────────────────────────────────────────────────────

_start_time=0

timer_start() {
    _start_time=$(date +%s)
}

timer_elapsed() {
    local now
    now=$(date +%s)
    echo $(( now - _start_time ))
}

#!/usr/bin/env bash
# EkamCore container crash recovery (G-07 / ART-17)
#
# Detects and recovers from container crash scenarios:
#   a. Single container crash: restart + verify health
#   b. Multiple containers down: restart in dependency order
#   c. Docker daemon crash: wait for daemon, then restart stack
#   d. OOM kill: detect via Docker events, restart with current limits
#
# Usage:
#   ./scripts/dr/container_recovery.sh [--check-only] [--service NAME]
#
# Options:
#   --check-only   Report status without attempting recovery
#   --service NAME Only check/recover a specific service
#
# Must be run from the EkamCore project root.

set -uo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────

CHECK_ONLY=false
TARGET_SERVICE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-only) CHECK_ONLY=true; shift ;;
        --service)    TARGET_SERVICE="$2"; shift 2 ;;
        *)            echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Dependency-ordered list (postgres first, proxy last)
SERVICES_ORDERED=(
    "ekamcore-postgres"
    "ekamcore-redis"
    "ekamcore-qdrant"
    "ekamcore-paperless"
    "ekamcore-api"
    "ekamcore-workers"
    "ekamcore-web"
    "ekamcore-proxy"
)

# ── Check Docker daemon ──────────────────────────────────────────────────────

log "============================================================"
log "  EkamCore Container Recovery"
log "============================================================"
log ""

check_docker_daemon() {
    if docker info > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

if ! check_docker_daemon; then
    log "Docker daemon is NOT running."

    if [[ "$CHECK_ONLY" == "true" ]]; then
        log "  Scenario: Docker daemon crash"
        log "  Action needed: Start Docker Desktop or dockerd"
        exit 1
    fi

    log "  Waiting for Docker daemon to come back..."
    WAIT=0
    while ! check_docker_daemon; do
        sleep 5
        WAIT=$((WAIT + 5))
        if [[ $WAIT -ge 120 ]]; then
            log "  ✗ Docker daemon did not start within 120s"
            log "  Manual action required: Start Docker Desktop"
            exit 1
        fi
        log "  Waiting... (${WAIT}s)"
    done

    log "  ✓ Docker daemon is back (waited ${WAIT}s)"
    log "  Restarting full stack..."
    docker compose up -d
    log "  Waiting for health checks..."
    sleep 20
    log "  ✓ Stack restart initiated"
    exit 0
fi

log "Docker daemon: OK"

# ── Check for OOM kills ─────────────────────────────────────────────────────

log ""
log "Checking for recent OOM kills..."

OOM_CONTAINERS=()
for svc in "${SERVICES_ORDERED[@]}"; do
    # Check if container was OOM-killed
    OOM_KILLED=$(docker inspect --format='{{.State.OOMKilled}}' "$svc" 2>/dev/null || echo "false")
    if [[ "$OOM_KILLED" == "true" ]]; then
        OOM_CONTAINERS+=("$svc")
        log "  ⚠ ${svc}: OOM killed"
    fi
done

# Also check docker events for recent OOM events (last 5 minutes)
RECENT_OOM=$(docker events --since "5m" --until "0s" --filter event=oom 2>/dev/null | head -5 || echo "")
if [[ -n "$RECENT_OOM" ]]; then
    log "  Recent OOM events detected in Docker:"
    echo "$RECENT_OOM" | while read -r line; do log "    $line"; done
fi

if [[ ${#OOM_CONTAINERS[@]} -gt 0 ]]; then
    log ""
    log "OOM-killed containers found: ${OOM_CONTAINERS[*]}"
    if [[ "$CHECK_ONLY" == "true" ]]; then
        log "  Scenario: OOM kill"
        log "  Action: Restart affected containers (memory limits unchanged)"
        log "  Consider: Increasing memory limits in docker-compose.yml"
    else
        log "  Restarting OOM-killed containers..."
        for svc in "${OOM_CONTAINERS[@]}"; do
            docker compose restart "$svc" 2>/dev/null \
                && log "  ✓ ${svc} restarted" \
                || log "  ✗ ${svc} restart failed"
        done
    fi
fi

# ── Assess container health ──────────────────────────────────────────────────

log ""
log "Assessing container status..."

DOWN_SERVICES=()
UNHEALTHY_SERVICES=()

for svc in "${SERVICES_ORDERED[@]}"; do
    if [[ -n "$TARGET_SERVICE" && "$svc" != "$TARGET_SERVICE" ]]; then
        continue
    fi

    status=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "not_found")
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$svc" 2>/dev/null || echo "unknown")

    if [[ "$status" != "running" ]]; then
        DOWN_SERVICES+=("$svc")
        log "  ✗ ${svc}: ${status}"
    elif [[ "$health" == "unhealthy" ]]; then
        UNHEALTHY_SERVICES+=("$svc")
        log "  ⚠ ${svc}: running but unhealthy"
    else
        log "  ✓ ${svc}: running (health: ${health})"
    fi
done

# ── Determine scenario and recover ──────────────────────────────────────────

TOTAL_DOWN=$(( ${#DOWN_SERVICES[@]} + ${#UNHEALTHY_SERVICES[@]} ))

if [[ $TOTAL_DOWN -eq 0 ]]; then
    log ""
    log "All containers are running and healthy. No recovery needed."
    exit 0
fi

log ""

if [[ "$CHECK_ONLY" == "true" ]]; then
    if [[ ${#DOWN_SERVICES[@]} -le 1 && ${#UNHEALTHY_SERVICES[@]} -le 1 ]]; then
        log "Scenario: Single container issue"
    else
        log "Scenario: Multiple containers down (${TOTAL_DOWN} affected)"
    fi
    log "Down: ${DOWN_SERVICES[*]:-none}"
    log "Unhealthy: ${UNHEALTHY_SERVICES[*]:-none}"
    log "Run without --check-only to attempt recovery"
    exit 1
fi

# ── Recovery: single container ───────────────────────────────────────────────

if [[ $TOTAL_DOWN -eq 1 ]]; then
    TARGET="${DOWN_SERVICES[0]:-${UNHEALTHY_SERVICES[0]}}"
    log "Single container recovery: ${TARGET}"
    log "  Restarting..."

    docker compose restart "$TARGET" 2>/dev/null

    # Wait for health
    WAIT=0
    while [[ $WAIT -lt 60 ]]; do
        sleep 5
        WAIT=$((WAIT + 5))
        status=$(docker inspect --format='{{.State.Status}}' "$TARGET" 2>/dev/null || echo "not_found")
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$TARGET" 2>/dev/null || echo "unknown")

        if [[ "$status" == "running" && ("$health" == "healthy" || "$health" == "none") ]]; then
            log "  ✓ ${TARGET} recovered (${WAIT}s)"
            exit 0
        fi
        log "  Waiting... (${WAIT}s) status=${status} health=${health}"
    done

    log "  ✗ ${TARGET} did not recover within 60s"
    log "  Trying full recreate..."
    docker compose up -d --force-recreate "$TARGET" 2>/dev/null
    sleep 15

    status=$(docker inspect --format='{{.State.Status}}' "$TARGET" 2>/dev/null || echo "not_found")
    if [[ "$status" == "running" ]]; then
        log "  ✓ ${TARGET} recreated and running"
        exit 0
    else
        log "  ✗ ${TARGET} still not running after recreate"
        log "  Manual intervention required. Check: docker compose logs ${TARGET}"
        exit 1
    fi
fi

# ── Recovery: multiple containers ────────────────────────────────────────────

log "Multiple container recovery (${TOTAL_DOWN} affected)"
log "  Restarting in dependency order..."

# Stop all affected services first
ALL_AFFECTED=("${DOWN_SERVICES[@]}" "${UNHEALTHY_SERVICES[@]}")
for svc in "${ALL_AFFECTED[@]}"; do
    docker compose stop "$svc" 2>/dev/null || true
done

# Start in dependency order
for svc in "${SERVICES_ORDERED[@]}"; do
    # Only restart affected services
    FOUND=false
    for affected in "${ALL_AFFECTED[@]}"; do
        if [[ "$svc" == "$affected" ]]; then
            FOUND=true
            break
        fi
    done
    [[ "$FOUND" != "true" ]] && continue

    log "  Starting ${svc}..."
    docker compose up -d "$svc" 2>/dev/null

    # Wait briefly for services that others depend on
    case "$svc" in
        ekamcore-postgres|ekamcore-redis|ekamcore-qdrant)
            WAIT=0
            while [[ $WAIT -lt 30 ]]; do
                sleep 3
                WAIT=$((WAIT + 3))
                health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$svc" 2>/dev/null || echo "unknown")
                if [[ "$health" == "healthy" || "$health" == "none" ]]; then
                    break
                fi
            done
            ;;
        *)
            sleep 3
            ;;
    esac

    status=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "not_found")
    log "  ${svc}: ${status}"
done

log ""
log "Recovery sequence complete. Verifying..."
sleep 10

# Final check
STILL_DOWN=0
for svc in "${ALL_AFFECTED[@]}"; do
    status=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "not_found")
    if [[ "$status" != "running" ]]; then
        log "  ✗ ${svc} still not running"
        ((STILL_DOWN++))
    else
        log "  ✓ ${svc} running"
    fi
done

if [[ $STILL_DOWN -gt 0 ]]; then
    log ""
    log "WARNING: ${STILL_DOWN} service(s) still down after recovery."
    log "Run: docker compose logs <service-name> to diagnose."
    exit 1
fi

log ""
log "✓ All affected containers recovered successfully."
exit 0

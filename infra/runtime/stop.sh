#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/runtime/docker-compose.yml"

log() {
  printf '[ekamcore-runtime] %s\n' "$*"
}

compose_services() {
  docker compose -f "${COMPOSE_FILE}" config --services 2>/dev/null || true
}

if ! command -v docker >/dev/null 2>&1; then
  log "Docker CLI is not installed. Nothing to stop."
  exit 0
fi

if ! docker info >/dev/null 2>&1; then
  log "Docker Desktop is not reachable. No EkamCore services are running."
  exit 0
fi

if [[ -f "${COMPOSE_FILE}" ]]; then
  services="$(compose_services)"
  if [[ -n "${services}" ]]; then
    log "Stopping EkamCore services from ${COMPOSE_FILE}..."
    docker compose -f "${COMPOSE_FILE}" down --remove-orphans
    log "EkamCore services stopped. Docker Desktop remains running."
    exit 0
  fi
fi

log "Docker Desktop is running, but no EkamCore compose services are defined yet."

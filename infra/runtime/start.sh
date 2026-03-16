#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKER_APP="/Applications/Docker.app"
COMPOSE_FILE="${REPO_ROOT}/infra/runtime/docker-compose.yml"
WAIT_SECONDS="${EKAMCORE_DOCKER_WAIT_SECONDS:-120}"

log() {
  printf '[ekamcore-runtime] %s\n' "$*"
}

fail() {
  printf '[ekamcore-runtime] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' is not available on PATH."
}

docker_ready() {
  docker info >/dev/null 2>&1
}

compose_services() {
  docker compose -f "${COMPOSE_FILE}" config --services 2>/dev/null || true
}

require_command docker
require_command open

[[ -d "${DOCKER_APP}" ]] || fail "Docker Desktop is not installed at ${DOCKER_APP}."

if ! docker_ready; then
  log "Starting Docker Desktop..."
  open "${DOCKER_APP}"
fi

elapsed=0
until docker_ready; do
  if (( elapsed >= WAIT_SECONDS )); then
    fail "Docker Desktop did not become ready within ${WAIT_SECONDS} seconds."
  fi

  sleep 2
  elapsed=$((elapsed + 2))
done

if [[ -f "${COMPOSE_FILE}" ]]; then
  services="$(compose_services)"
  if [[ -n "${services}" ]]; then
    log "Starting EkamCore services from ${COMPOSE_FILE}..."
    docker compose -f "${COMPOSE_FILE}" up -d
    log "EkamCore runtime is ready."
    exit 0
  fi
fi

log "Docker Desktop is ready. No EkamCore compose services are defined yet."

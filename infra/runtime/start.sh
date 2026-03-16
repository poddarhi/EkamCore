#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKER_APP="/Applications/Docker.app"
COMPOSE_FILE="${REPO_ROOT}/infra/runtime/docker-compose.yml"
WAIT_SECONDS="${EKAMCORE_DOCKER_WAIT_SECONDS:-120}"
DOCKER_CONTEXT="${EKAMCORE_DOCKER_CONTEXT:-desktop-linux}"

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

docker_context_exists() {
  docker context inspect "${DOCKER_CONTEXT}" >/dev/null 2>&1
}

docker_ready() {
  docker --context "${DOCKER_CONTEXT}" info >/dev/null 2>&1
}

compose_services() {
  docker --context "${DOCKER_CONTEXT}" compose -f "${COMPOSE_FILE}" config --services 2>/dev/null || true
}

require_command docker
require_command open

[[ -d "${DOCKER_APP}" ]] || fail "Docker Desktop is not installed at ${DOCKER_APP}."
docker_context_exists || fail "Docker context '${DOCKER_CONTEXT}' is not available. Complete Docker Desktop first-run setup or set EKAMCORE_DOCKER_CONTEXT to a valid local context."

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
    docker --context "${DOCKER_CONTEXT}" compose -f "${COMPOSE_FILE}" up -d
    log "EkamCore runtime is ready."
    exit 0
  fi
fi

log "Docker Desktop context '${DOCKER_CONTEXT}' is ready. No EkamCore compose services are defined yet."

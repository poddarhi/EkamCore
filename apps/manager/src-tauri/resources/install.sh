#!/usr/bin/env bash
#
# EkamCore One-Click Installer
# Handles all dependencies and setup for a fresh Mac.
#
# Usage: bash install.sh [phase]
#   Phases: check-deps, install-docker, install-ollama, clone-repo,
#           pull-images, start-stack, run-migrations, pull-models, verify
#
# Each phase prints JSON progress to stdout for the Manager app to parse.

set -uo pipefail

EKAMCORE_DIR="$HOME/EkamCore"
GITHUB_REPO="https://github.com/poddarhi/EkamCore.git"
COMPOSE_FILE="$EKAMCORE_DIR/docker-compose.yml"

progress() {
    echo "{\"phase\":\"$1\",\"status\":\"$2\",\"message\":\"$3\"}"
}

# ── Phase: check-deps ────────────────────────────────────────────────────────

check_deps() {
    progress "check-deps" "running" "Checking system dependencies..."

    DOCKER_OK=false
    OLLAMA_OK=false
    REPO_OK=false

    # Docker
    if docker info >/dev/null 2>&1; then
        DOCKER_OK=true
        progress "check-deps" "info" "Docker is installed and running"
    elif command -v docker >/dev/null 2>&1; then
        progress "check-deps" "info" "Docker is installed but not running"
    else
        progress "check-deps" "info" "Docker is not installed"
    fi

    # Ollama
    if command -v ollama >/dev/null 2>&1; then
        OLLAMA_OK=true
        progress "check-deps" "info" "Ollama is installed"
    else
        progress "check-deps" "info" "Ollama is not installed"
    fi

    # Repo
    if [[ -f "$COMPOSE_FILE" ]]; then
        REPO_OK=true
        progress "check-deps" "info" "EkamCore repo found at $EKAMCORE_DIR"
    else
        progress "check-deps" "info" "EkamCore repo not found"
    fi

    echo "{\"docker\":$DOCKER_OK,\"ollama\":$OLLAMA_OK,\"repo\":$REPO_OK}"
}

# ── Phase: install-docker ────────────────────────────────────────────────────

install_docker() {
    if docker info >/dev/null 2>&1; then
        progress "install-docker" "done" "Docker already running"
        return 0
    fi

    # Check if OrbStack is installed
    if [[ -d "/Applications/OrbStack.app" ]]; then
        progress "install-docker" "running" "Starting OrbStack..."
        open -a OrbStack
        # Wait for Docker daemon
        for i in $(seq 1 30); do
            if docker info >/dev/null 2>&1; then
                progress "install-docker" "done" "OrbStack started"
                return 0
            fi
            sleep 2
        done
        progress "install-docker" "failed" "OrbStack did not start in 60s"
        return 1
    fi

    # Check if Docker Desktop is installed
    if [[ -d "/Applications/Docker.app" ]]; then
        progress "install-docker" "running" "Starting Docker Desktop..."
        open -a Docker
        for i in $(seq 1 60); do
            if docker info >/dev/null 2>&1; then
                progress "install-docker" "done" "Docker Desktop started"
                return 0
            fi
            sleep 2
        done
        progress "install-docker" "failed" "Docker Desktop did not start in 120s"
        return 1
    fi

    # Neither installed — try brew install orbstack (preferred, lighter)
    if command -v brew >/dev/null 2>&1; then
        progress "install-docker" "running" "Installing OrbStack via Homebrew..."
        brew install --cask orbstack 2>&1 | tail -3
        if [[ $? -eq 0 ]]; then
            progress "install-docker" "running" "Starting OrbStack..."
            open -a OrbStack
            for i in $(seq 1 30); do
                if docker info >/dev/null 2>&1; then
                    progress "install-docker" "done" "OrbStack installed and started"
                    return 0
                fi
                sleep 2
            done
        fi
    fi

    # Fallback: download OrbStack DMG
    progress "install-docker" "running" "Downloading OrbStack..."
    curl -fsSL "https://orbstack.dev/download/stable/latest/arm64" -o /tmp/OrbStack.dmg 2>/dev/null
    if [[ -f /tmp/OrbStack.dmg ]]; then
        hdiutil attach /tmp/OrbStack.dmg -quiet
        cp -R "/Volumes/OrbStack/OrbStack.app" /Applications/ 2>/dev/null
        hdiutil detach "/Volumes/OrbStack" -quiet 2>/dev/null
        rm -f /tmp/OrbStack.dmg
        open -a OrbStack
        for i in $(seq 1 30); do
            if docker info >/dev/null 2>&1; then
                progress "install-docker" "done" "OrbStack installed and started"
                return 0
            fi
            sleep 2
        done
    fi

    progress "install-docker" "failed" "Could not install Docker. Please install OrbStack or Docker Desktop manually."
    return 1
}

# ── Phase: install-ollama ────────────────────────────────────────────────────

install_ollama() {
    if command -v ollama >/dev/null 2>&1; then
        progress "install-ollama" "done" "Ollama already installed"
        # Make sure it's running
        if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
            ollama serve >/dev/null 2>&1 &
            sleep 3
        fi
        return 0
    fi

    progress "install-ollama" "running" "Installing Ollama..."

    if command -v brew >/dev/null 2>&1; then
        brew install ollama 2>&1 | tail -3
        if command -v ollama >/dev/null 2>&1; then
            ollama serve >/dev/null 2>&1 &
            sleep 3
            progress "install-ollama" "done" "Ollama installed via Homebrew"
            return 0
        fi
    fi

    # Direct download
    curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -5
    if command -v ollama >/dev/null 2>&1; then
        ollama serve >/dev/null 2>&1 &
        sleep 3
        progress "install-ollama" "done" "Ollama installed"
        return 0
    fi

    progress "install-ollama" "failed" "Could not install Ollama"
    return 1
}

# ── Phase: clone-repo ────────────────────────────────────────────────────────

clone_repo() {
    if [[ -f "$COMPOSE_FILE" ]]; then
        progress "clone-repo" "running" "Updating existing repo..."
        cd "$EKAMCORE_DIR"
        git pull origin development 2>&1 | tail -3
        progress "clone-repo" "done" "Repo updated at $EKAMCORE_DIR"
        return 0
    fi

    progress "clone-repo" "running" "Downloading EkamCore..."

    if command -v git >/dev/null 2>&1; then
        git clone --depth 1 --branch development "$GITHUB_REPO" "$EKAMCORE_DIR" 2>&1 | tail -5
    else
        # Fallback: download ZIP
        progress "clone-repo" "running" "Downloading ZIP archive..."
        curl -fsSL "https://github.com/poddarhi/EkamCore/archive/refs/heads/development.zip" -o /tmp/ekamcore.zip
        unzip -q /tmp/ekamcore.zip -d /tmp/
        mv /tmp/EkamCore-development "$EKAMCORE_DIR"
        rm -f /tmp/ekamcore.zip
    fi

    if [[ -f "$COMPOSE_FILE" ]]; then
        progress "clone-repo" "done" "EkamCore downloaded to $EKAMCORE_DIR"
        return 0
    fi

    progress "clone-repo" "failed" "Failed to download EkamCore"
    return 1
}

# ── Phase: pull-images ───────────────────────────────────────────────────────

pull_images() {
    progress "pull-images" "running" "Pulling Docker images (this may take a few minutes)..."
    cd "$EKAMCORE_DIR"

    # Pull third-party images
    for img in postgres:16.3 redis:7.2-alpine qdrant/qdrant:v1.9.0 caddy:2-alpine; do
        progress "pull-images" "running" "Pulling $img..."
        docker pull "$img" 2>&1 | tail -1
    done

    # Build EkamCore images
    progress "pull-images" "running" "Building EkamCore API image..."
    docker compose build ekamcore-api 2>&1 | tail -3

    progress "pull-images" "running" "Building EkamCore Workers image..."
    docker compose build ekamcore-workers 2>&1 | tail -3

    progress "pull-images" "running" "Building EkamCore Web image..."
    docker compose build ekamcore-web 2>&1 | tail -3

    progress "pull-images" "running" "Building migration runner..."
    docker compose build ekamcore-migrate 2>&1 | tail -3

    progress "pull-images" "done" "All images ready"
    return 0
}

# ── Phase: start-stack ───────────────────────────────────────────────────────

start_stack() {
    progress "start-stack" "running" "Starting EkamCore services..."
    cd "$EKAMCORE_DIR"

    # Create .env if it doesn't exist
    if [[ ! -f .env ]]; then
        cp .env.example .env 2>/dev/null || cat > .env << 'ENVEOF'
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://ekamcore:ekamcore_pg_dev@localhost:5432/ekamcore
REDIS_URL=redis://:ekamcore_redis_dev@localhost:6379/0
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=ekamcore_qdrant_dev
OLLAMA_URL=http://host.docker.internal:11434
JWT_SECRET_KEY=ekamcore-jwt-secret-change-in-production
PAPERLESS_URL=http://ekamcore-paperless:8000
PAPERLESS_TOKEN=change-me
ENVEOF
    fi

    # Start data services first
    progress "start-stack" "running" "Starting PostgreSQL, Redis, Qdrant..."
    docker compose up -d ekamcore-postgres ekamcore-redis ekamcore-qdrant 2>&1 | tail -3

    # Wait for health
    progress "start-stack" "running" "Waiting for databases..."
    for i in $(seq 1 30); do
        PG_OK=$(docker compose exec -T ekamcore-postgres pg_isready -U ekamcore 2>/dev/null && echo "1" || echo "0")
        if [[ "$PG_OK" == "1" ]]; then break; fi
        sleep 2
    done

    # Run migrations
    progress "start-stack" "running" "Running database migrations..."
    docker compose run --rm ekamcore-migrate 2>&1 | tail -3
    # If migrate fails (stale image), try from host
    if [[ $? -ne 0 ]]; then
        if command -v poetry >/dev/null 2>&1 && [[ -f apps/api/alembic.ini ]]; then
            cd apps/api && PYTHONPATH=. poetry run alembic stamp head 2>/dev/null; cd ../..
        fi
    fi

    # Start application services
    progress "start-stack" "running" "Starting API, Workers, Web, Proxy..."
    docker compose up -d --no-deps ekamcore-api 2>&1 | tail -3
    sleep 5
    docker compose up -d --no-deps ekamcore-workers ekamcore-web ekamcore-proxy 2>&1 | tail -3

    # Wait for API
    progress "start-stack" "running" "Waiting for API to be healthy..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:8420/health >/dev/null 2>&1; then
            progress "start-stack" "done" "All services running"
            return 0
        fi
        sleep 3
    done

    progress "start-stack" "failed" "API did not become healthy in 90s"
    return 1
}

# ── Phase: pull-models ───────────────────────────────────────────────────────

pull_models() {
    progress "pull-models" "running" "Downloading AI models (this takes a few minutes)..."

    # Ensure Ollama is running
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        ollama serve >/dev/null 2>&1 &
        sleep 3
    fi

    for model in nomic-embed-text phi3:mini; do
        progress "pull-models" "running" "Pulling $model..."
        ollama pull "$model" 2>&1 | tail -1
    done

    progress "pull-models" "done" "AI models ready"
    return 0
}

# ── Phase: verify ────────────────────────────────────────────────────────────

verify() {
    progress "verify" "running" "Verifying installation..."

    ERRORS=0

    docker info >/dev/null 2>&1 || { progress "verify" "info" "Docker not running"; ERRORS=$((ERRORS+1)); }
    curl -sf http://localhost:8420/health >/dev/null 2>&1 || { progress "verify" "info" "API not responding"; ERRORS=$((ERRORS+1)); }
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 || { progress "verify" "info" "Ollama not responding"; ERRORS=$((ERRORS+1)); }

    if [[ $ERRORS -eq 0 ]]; then
        progress "verify" "done" "EkamCore is ready! Open https://localhost in your browser."
        return 0
    else
        progress "verify" "failed" "$ERRORS checks failed"
        return 1
    fi
}

# ── Phase: full (run everything) ─────────────────────────────────────────────

full_install() {
    install_docker || return 1
    install_ollama || return 1
    clone_repo || return 1
    pull_images || return 1
    start_stack || return 1
    pull_models || return 1
    verify || return 1
    progress "complete" "done" "EkamCore installation complete!"
}

# ── Main ─────────────────────────────────────────────────────────────────────

PHASE="${1:-full}"
case "$PHASE" in
    check-deps)     check_deps ;;
    install-docker) install_docker ;;
    install-ollama) install_ollama ;;
    clone-repo)     clone_repo ;;
    pull-images)    pull_images ;;
    start-stack)    start_stack ;;
    pull-models)    pull_models ;;
    verify)         verify ;;
    full)           full_install ;;
    *)              echo "Unknown phase: $PHASE"; exit 1 ;;
esac

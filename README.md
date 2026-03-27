# EkamCore

Privacy-first, local-only life assistant running entirely on Apple Silicon. Connects files, photos, contacts, calendars, and reminders through local AI — no cloud, no telemetry, no external APIs. Powered by Ollama (LLMs + embeddings), PostgreSQL, Qdrant, Redis, and PaperlessNGX, all orchestrated via Docker Compose on a 16GB Mac.

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| OrbStack (or Docker Desktop) | latest | [orbstack.dev](https://orbstack.dev) |
| Python | 3.12+ | `brew install python@3.12` |
| Poetry | 2.x | `pip install poetry` |
| Node.js | 20+ | `brew install node@20` |
| pnpm | 9+ | `npm install -g pnpm` |
| Ollama | latest | [ollama.com](https://ollama.com) |
| Rust | stable | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |

## Quick Start

```bash
git clone <repo-url> && cd EkamCore
make setup    # Install deps, create .env
make up       # Start 9 containers + Ollama
```

Open [https://localhost](https://localhost) (accept the self-signed cert).

## Make Targets

| Target | Description |
|---|---|
| `make setup` | Install all dependencies and create `.env` |
| `make up` | Start all services (auto-starts Ollama) |
| `make down` | Stop containers (Ollama keeps running) |
| `make clean` | Stop + remove containers and volumes |
| `make logs` | Tail all service logs |
| `make restart` | Restart all services |
| `make migrate` | Run Alembic database migrations |
| `make migration name=X` | Create new migration |
| `make seed` | Seed database with dev data |
| `make test` | Run all tests |
| `make test-api` | Run API tests with coverage |
| `make test-web` | Run web tests |
| `make test-integration` | Run integration tests (Docker) |
| `make lint` | Run all linters |
| `make format` | Format all code |
| `make benchmark` | Run performance benchmarks |
| `make dev-api` | Run API locally (no Docker) |
| `make dev-web` | Run web locally (no Docker) |
| `make shell-api` | Shell into API container |
| `make shell-db` | Shell into PostgreSQL |
| `make shell-redis` | Shell into Redis |
| `make ollama-start` | Start Ollama natively |
| `make ollama-stop` | Stop Ollama |
| `make ollama-status` | Show loaded models |
| `make paperless-logs` | Tail Paperless logs |
| `make paperless-token` | Create Paperless API token |

## Project Structure

```
EkamCore/
  apps/
    api/             # Python FastAPI backend
    web/             # React + Vite + TypeScript
    mobile/          # React Native (future)
    manager/         # Tauri 2 manager app (future)
  packages/
    shared-types/    # Shared TypeScript types
  infra/
    caddy/           # Reverse proxy config
    docker/          # Dockerfiles and init scripts
    backup/          # Backup scripts
  openapi/           # OpenAPI 3.1 spec (source of truth)
  alembic/           # Database migrations
  config/            # Feature flags, quality config
  scripts/           # Dev utilities and benchmarks
  tests/             # Integration and E2E tests
  ci/                # CI quality thresholds
  docs/              # Architecture docs
  docker-compose.yml # 9-service stack
  Makefile           # All dev commands
```

## Architecture

- **9 Docker containers** + native Ollama (~4.75G steady, 6.25G peak on 16GB Mac)
- **Caddy** reverse proxy with auto-TLS: `/api/*` and `/health` to API, `/paperless/*` to PaperlessNGX, `/*` to web
- **Ollama** runs natively for direct Apple Silicon GPU access (not in Docker)
- **PaperlessNGX** handles document OCR/ingestion; EkamCore adds embeddings + semantic search on top

See `docs/architecture/` for detailed documentation.

## License

Proprietary. All rights reserved.

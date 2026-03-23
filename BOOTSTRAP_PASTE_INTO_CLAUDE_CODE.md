Read this entire file and execute all 9 phases in order. Take it step by step. Complete each phase fully before moving to the next. Commit to git after each phase.

You are bootstrapping EkamCore — a private, local-first life assistant that runs entirely on Apple silicon Mac. This machine IS the target deployment machine. Build it as a real product that a consumer will run. 9 Docker containers orchestrated by Docker Compose.

## PHASE 1: Prerequisites

Check and install each tool. Treat this Mac as a clean consumer machine.

1. Homebrew: `which brew` — if missing: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` then run the PATH commands it outputs.
2. OrbStack (lightweight Docker runtime): `which docker` — if missing: `brew install orbstack`. Verify: `docker --version` and `docker compose version`.
3. Node.js 20: `node --version` — if missing: `brew install node@20` and ensure it's on PATH.
4. Python 3.12: `python3 --version` — if missing: `brew install python@3.12`.
5. Rust: `rustc --version` — if missing: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && source "$HOME/.cargo/env"`.
6. pnpm 9: `pnpm --version` — if missing: `npm install -g pnpm@9`.
7. Poetry: `poetry --version` — if missing: `curl -sSL https://install.python-poetry.org | python3 -` and add ~/.local/bin to PATH.
8. Ollama: `ollama --version` — if missing: `brew install ollama`. Start: `ollama serve &`. Pull: `ollama pull llama3.2:1b && ollama pull nomic-embed-text`.

Print version summary when done.

## PHASE 2: Project Structure

Preserve ALL existing files. Create directories and files that don't exist. Target structure:

```
EkamCore/
├── apps/
│   ├── api/                    # Python FastAPI backend
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── errors.py
│   │   │   ├── routers/ (health.py)
│   │   │   ├── services/
│   │   │   ├── db/ (session.py, models/)
│   │   │   ├── schemas/
│   │   │   ├── middleware/ (correlation.py, error_handler.py, logging.py)
│   │   │   └── workers/
│   │   ├── tests/ (test_health.py)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── Dockerfile.workers
│   ├── web/                    # React + Vite + TypeScript
│   ├── mobile/ (placeholder)
│   └── manager/ (placeholder)
├── packages/shared-types/
├── infra/
│   ├── caddy/Caddyfile
│   └── backup/
├── alembic/ (migrations)
├── config/feature-flags.json
├── ci/quality-config.json
├── scripts/
├── tests/integration/
├── docs/
├── docker-compose.yml
├── docker-compose.test.yml
├── Makefile
├── .env.example
└── .gitignore
```

## PHASE 3: Skill Files

Create `.claude/skills/ekamcore-skills/` with these files:

### SKILL.md (Master)
Frontmatter: name=ekamcore, description="Master skill for EkamCore. Read FIRST for any task."
Body: tech stack (FastAPI, PostgreSQL 16, Qdrant, Redis 7, Ollama, React, Tauri 2, Caddy, Docker), monorepo structure (apps/api, apps/web, etc.), 7 Golden Rules (workspace_id filtering, no raw SQL, structured errors, no PII in logs, feature flags, auth everywhere, tests always), routing table to workstream skills, phase system (0-4).

### backend/SKILL.md
Frontmatter: name=ekamcore-backend, description="Python FastAPI backend. API routes, services, SQLAlchemy, Pydantic, auth, tests."
Body: apps/api structure, exception hierarchy (EkamCoreError→8 subclasses), route pattern (require_flag+get_current_user+get_db), service pattern (db+workspace_ids params), response envelope, DB model pattern (UUID v7, workspace_id, timestamps, soft delete), auth (JWT RS256, argon2id), ingestion stages, query routing (5 steps), Today assembly engine, Python conventions (Ruff 120, mypy strict, async).

### infrastructure/SKILL.md
Frontmatter: name=ekamcore-infrastructure, description="Docker, CI/CD, Caddy, Makefile, scripts."
Body: 9 services with images/ports/volumes/health checks/resource limits, dependency chain, Caddyfile, Makefile targets, CI/CD pipelines, Dockerfile pattern, quality-config schema, feature-flags schema.

### frontend/SKILL.md (stub)
React 18, TypeScript strict, Vite, Tailwind with tokens (primary=#1F3864), SWR, Lucide icons, useFlag() gating, auth in memory only, WCAG 2.1 AA.

### mobile/SKILL.md (stub)
React Native, React Navigation, 6-state connectivity, SQLCipher, react-native-keychain, 44px targets.

### ml-ai/SKILL.md (stub)
Ollama (llama3.2:1b dev, nomic-embed-text), grounded QA only, prompt injection defense, face pipeline, Qdrant with workspace_id always.

### manager-app/SKILL.md (stub)
Tauri 2, Rust, Keychain (security-framework), Docker API (bollard), FSEvents (notify), watchdog.

## PHASE 4: Docker Compose

Create docker-compose.yml with 9 services:
1. ekamcore-postgres: postgres:16.3, shared_buffers=512MB, 2G mem limit, pg_isready health
2. ekamcore-redis: redis:7.2-alpine, password, 4 DBs, 512M limit, redis-cli ping health
3. ekamcore-qdrant: qdrant/qdrant:v1.9.0, API key, 3G limit, curl /healthz health
4. ekamcore-ollama: ollama/ollama:latest, MAX_LOADED_MODELS=2, 8G limit, curl /api/tags health
5. ekamcore-api: build from apps/api/Dockerfile, depends on pg+redis+qdrant healthy + migrate done, 2G limit, curl /health
6. ekamcore-workers: build from apps/api/Dockerfile.workers, depends on api healthy, 4G limit
7. ekamcore-web: build from apps/web/Dockerfile
8. ekamcore-proxy: caddy:2-alpine, ports 443+80 to host, Caddyfile mount, depends on api
9. ekamcore-migrate: build from apps/api, runs alembic upgrade head, depends on pg, restart=no

Network: ekamcore-net (bridge). Volumes: pgdata, redis-data, qdrant-data, models, caddy-data, caddy-config.
All passwords from env vars with dev defaults. Create .env.example and copy to .env.

Also create docker-compose.test.yml and infra/caddy/Caddyfile.

## PHASE 5: Python API

Set up apps/api/ with Poetry:
- pyproject.toml with: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, pydantic, pydantic-settings, python-jose[cryptography], argon2-cffi, httpx, redis, structlog, alembic. Dev: pytest, pytest-asyncio, pytest-cov, ruff, mypy.
- Run `cd apps/api && poetry install`
- api/main.py: FastAPI factory, lifespan, routers, middleware, CORS
- api/config.py: Pydantic BaseSettings (DATABASE_URL, REDIS_URL, QDRANT_URL, OLLAMA_URL, JWT_SECRET_KEY)
- api/errors.py: Full hierarchy (8 exception classes)
- api/middleware/correlation.py: UUID per request, X-Correlation-ID header
- api/middleware/error_handler.py: Catch EkamCoreError, format JSON, never expose stack traces
- api/middleware/logging.py: structlog JSON, never log PII
- api/routers/health.py: GET /health checking postgres+redis+qdrant connectivity
- api/db/session.py: async SQLAlchemy engine + sessionmaker
- Dockerfile: multi-stage (poetry export → pip install → runtime with USER nobody)
- Dockerfile.workers: same base, different CMD (placeholder worker)
- tests/test_health.py: basic health endpoint test

## PHASE 6: Web Scaffold

Set up apps/web/:
```bash
cd apps/web && pnpm create vite . --template react-ts
pnpm add -D tailwindcss @tailwindcss/vite
pnpm add lucide-react swr react-router-dom
```
- tailwind.config.ts with EkamCore tokens
- src/design-system/tokens.css with CSS custom properties
- src/App.tsx with router placeholder
- Dockerfile: multi-stage (node build → nginx serve)

## PHASE 7: Config Files

- config/feature-flags.json: All 19 flags (phase, consent, system types)
- ci/quality-config.json: current_phase=0, coverage thresholds
- Makefile: targets for setup, up, down, clean, logs, restart, migrate, test, lint, dev-api, dev-web, shell-api, shell-db

## PHASE 8: Alembic Migration

- Set up alembic/ with env.py reading DATABASE_URL
- Create 001_initial_schema.py: users, workspaces, workspace_members, sessions, settings tables
- All: UUID PK, created_at, updated_at. Content tables: workspace_id FK, deleted_at.
- Include upgrade() AND downgrade()

## PHASE 9: Boot and Verify

1. `docker compose build`
2. `docker compose up -d`
3. Wait for health checks (up to 3 min)
4. `docker compose ps` — all healthy
5. `curl http://localhost:8420/health` — 200 with service status
6. If failure: check logs, fix, retry
7. `git add . && git commit -m "feat: EkamCore initial scaffold — 9 Docker services, FastAPI API, React web, skill files"`

Print final summary: what's running, what was created, what to do next.

## RULES
- ONE PHASE AT A TIME. Fix failures before proceeding.
- NEVER delete existing files.
- Use `docker compose` (v2), NOT `docker-compose` (v1).
- All Dockerfiles: multi-stage, non-root user.
- All Python: type hints, async, Ruff-formatted.
- All TypeScript: strict mode.
- If Docker/OrbStack not installed, STOP and tell user: `brew install orbstack`

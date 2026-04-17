---
name: ekamcore-infrastructure
description: Use when working on Docker Compose, CI/CD pipelines, Caddy configuration, Makefile targets, shell scripts, benchmarks, backup/restore, or any code in infrastructure/, .github/workflows/, scripts/, or the root docker-compose.yml and Makefile.
---

# EkamCore Infrastructure Skill

**Always read Master SKILL.md first.**

## Docker Compose Stack (9 containers + Ollama native)

Ollama runs **natively on the host Mac** for direct Apple Silicon Metal/ANE GPU access — NOT in Docker.

| Service | Image | Health Check | Memory limit |
|---|---|---|---|
| ekamcore-postgres | postgres:16.3 | pg_isready -U ekamcore | 768M |
| ekamcore-redis | redis:7.2-alpine | redis-cli -a $PASS ping | 192M |
| ekamcore-qdrant | qdrant/qdrant:v1.9.0 | TCP probe :6333 | 1G |
| ekamcore-paperless | ghcr.io/paperless-ngx/paperless-ngx:latest | curl http://localhost:8000/api/ | 1G |
| ekamcore-api | (build ./apps/api) | curl http://localhost:8420/health | 768M |
| ekamcore-workers | (build ./apps/api Dockerfile.workers) | depends on api healthy | 768M |
| ekamcore-web | (build ./apps/web) | — | 128M |
| ekamcore-proxy | caddy:2-alpine | — | 128M |
| ekamcore-migrate | (build ./apps/api) | Exits 0 after alembic upgrade head | 256M |
| **Ollama (native)** | ollama CLI on host | ollama list | 0 idle / ~1.5G when model loaded |

**Memory budget (steady state):** ~3.75G containers + ~1G Paperless = **4.75G total**
**Peak (LLM active):** ~6.25G. Leaves 9.75G free on 16GB Mac.
Ollama auto-unloads models after 5 min idle (`~/.ollama/config.json: {"keep_alive": "5m"}`).

## Startup / Dependency Order

```
postgres + redis + qdrant      (parallel, no deps)
     ↓
migrate (needs postgres healthy)
paperless (needs postgres + redis healthy)
     ↓
api (needs postgres + redis + qdrant healthy + migrate completed)
     ↓
workers (needs api healthy)
web (standalone, any time)
proxy/Caddy (needs api healthy)
```

## Caddy Routes (infra/caddy/Caddyfile)

```
/api/*        → ekamcore-api:8420
/health       → ekamcore-api:8420
/paperless/*  → ekamcore-paperless:8000  (strips /paperless prefix)
/*            → ekamcore-web:3000
```

TLS: Caddy auto-cert for localhost (self-signed). Use `-k` with curl for dev.

## Network & Volumes

- Network: `ekamcore-net` bridge. Only proxy exposes 443/80 to host.
- Dev: also expose Qdrant(6333), API(8420), Web(3000).
- Named volumes: `ekamcore-pgdata`, `ekamcore-redis-data`, `ekamcore-qdrant-data`, `ekamcore-caddy-data`, `ekamcore-caddy-config`, `ekamcore-paperless-data`, `ekamcore-paperless-media`.
- Bind mount: `./infra/docker/postgres-init:/docker-entrypoint-initdb.d:ro` (creates paperless DB on first start).
- Consume dir: `./consume` → Paperless inbox (gitignored).

## PaperlessNGX Role

- Handles: document ingestion, OCR, tagging, full-text search, thumbnails.
- EkamCore adds on top: embeddings, semantic search, LLM grounded QA, People Graph.
- Access: `https://localhost/paperless/` (admin login: check `.env`).
- API token: `make paperless-token`.
- Uses DB `paperless` on same PostgreSQL instance (created by init script).
- Uses Redis db2 (EkamCore uses db0).

## Makefile Targets

setup, up, down, clean, logs, restart, migrate, migration, test, test-api, test-web, test-integration, coverage, lint, format, dev-api, dev-web, shell-api, shell-db, ollama-start, ollama-stop, ollama-status, paperless-logs, paperless-token, paperless-shell.

`make up` automatically runs `ollama-start` first.

## PostgreSQL Tuning (right-sized for 16GB Mac)

```
shared_buffers=192MB   work_mem=4MB   max_connections=50
```

## CI/CD Pipelines (.github/workflows/)

- **ci.yml**: PR pipeline. Path-filtered jobs. lint→typecheck→unit-test→integration-build. <15min.
- **nightly.yml**: 2am UTC. Full tests + integration + E2E + security scan + perf regression.
- **release.yml**: Manual dispatch. Full test → approval gate → build images → scan → SBOM → DMG → changelog → GitHub Release.
- **security.yml**: Weekly. pip-audit, pnpm audit, cargo audit, Trivy, license check.

## Dockerfile Pattern (multi-stage)

```dockerfile
FROM python:3.12-slim AS builder
# Install deps only
FROM python:3.12-slim AS runtime
COPY --from=builder /install /usr/local
USER nobody
```

## Backup (2am daily)

pg_dump (custom format) + Qdrant snapshot API + config backup. Retain: 7 daily + 4 weekly. Restore: <30 minutes.

## Manager App Architecture (Sprint 15)

Tauri 2 native macOS app in `apps/manager/`. Rust backend (`src-tauri/src/`) + React frontend (`src/`).

**Rust modules (18 total):**
`hardware`, `disk`, `docker`, `tailscale` — system checks.
`keychain` — macOS Keychain via security-framework (8 service secrets).
`container_runtime` — `ContainerRuntime` trait + `DockerRuntime` (bollard + compose CLI).
`startup` — 15-step startup sequence with event emission.
`wizard_state` — setup-state.json persistence.
`setup` — pull images, DB init, admin creation, permissions, folder picker.
`watchdog` — 30s health polling, exponential backoff (5/15/45/120/300s), macOS notifications.
`dashboard` — aggregated health + disk + API counts.
`diagnostics` — offline ZIP bundle (8 sections, no PII).
`launchd` — login item + backup schedule via ~/Library/LaunchAgents/ plists.
`secret_injection` — Keychain → temp .env (0600) → compose up → secure delete.
`update` — 8-step atomic update with auto-rollback on failure.
`commands` — S15-001 IPC bridge. `state` — AppState with Arc<Mutex<Watchdog>>.

**React pages (8):** SetupWizard, StartupSequence, Dashboard, Jobs, Storage, Diagnostics, Updates, ManagerSettings.
**Sidebar tabs:** Dashboard / Jobs / Storage / Diagnostics / Updates / Settings.

**Key patterns:**
- `ContainerRuntime` trait allows `NoopRuntime` fallback when Docker unavailable at startup.
- Watchdog spawns only after setup wizard completes.
- Secret injection: never writes secrets to persistent disk — temp file with 0600 permissions, zero-overwritten after compose reads it.
- Update rollback: saves old docker-compose.yml content + backup path in rollback-manifest.json, restores on any failure at steps 5/6/7.

## Chaos Testing (Sprint 15)

7 scenarios in `scripts/chaos/`, each with JSON pass/fail report:
1. PostgreSQL kill during writes — recovery < 60s
2. Qdrant kill — search degrades to exact-only
3. SIGKILL all containers — full recovery < 180s
4. Disk fill simulation — reads continue
5. Ollama model corruption — non-LLM features continue
6. Network partition — API returns errors, reconnect resumes
7. Concurrent heavy load — rate limiting, no crashes

Run: `make chaos-test` or `bash scripts/chaos/run_all.sh`.

## Release Pipeline (Sprint 15)

9-step `release.yml` (workflow_dispatch):
validate-version → full-test-suite → build-container-images (ghcr.io) → Trivy scan → SBOM (Syft SPDX) → build-manager-DMG (macOS runner) → changelog → distribution ZIP → GitHub Release.

Local: `make release-check`, `make release-build`, `make release-package VERSION=X.Y.Z`.

## DR Scripts (Sprint 15)

| Script | Purpose |
|--------|---------|
| `scripts/dr/container_recovery.sh` | Detect + restart unhealthy containers |
| `scripts/dr/database_repair.sh` | VACUUM, REINDEX, orphan cleanup |
| `scripts/dr/restore_from_backup.sh` | Full pg_restore + Qdrant snapshot recovery |
| `scripts/dr/verify_system_health.sh` | Comprehensive health check → JSON report |
| `scripts/dr/post_power_outage.sh` | Docker daemon + services + integrity check |
| `scripts/dr/disk_full_recovery.sh` | Log truncation + backup rotation + prune |
| `scripts/dr/model_reload.sh` | Ollama + InsightFace re-download with checksum |

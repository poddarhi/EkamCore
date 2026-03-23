---
name: ekamcore-infrastructure
description: Use when working on Docker Compose, CI/CD pipelines, Caddy configuration, Makefile targets, shell scripts, benchmarks, backup/restore, or any code in infrastructure/, .github/workflows/, scripts/, or the root docker-compose.yml and Makefile.
---

# EkamCore Infrastructure Skill

**Always read Master SKILL.md first.**

## Docker Compose Stack (9 services)
| Service | Image | Health Check | Memory (ref/min) |
|---|---|---|---|
| ekamcore-postgres | postgres:16.3 | pg_isready -U ekamcore | 2G/1.5G |
| ekamcore-redis | redis:7.2-alpine | redis-cli -a $PASS ping | 512M/256M |
| ekamcore-qdrant | qdrant/qdrant:v1.9.0 | curl -f localhost:6333/healthz | 3G/2G |
| ekamcore-ollama | ollama/ollama:latest | curl -f localhost:11434/api/tags | 12G/8G |
| ekamcore-api | ghcr.io/ekamcore/api | curl -f localhost:8420/health | 2G/1.5G |
| ekamcore-workers | ghcr.io/ekamcore/workers | Redis ping | 4G/2G |
| ekamcore-web | ghcr.io/ekamcore/web | — | 512M |
| ekamcore-proxy | ghcr.io/ekamcore/proxy | curl -f localhost:80/health | 256M |
| ekamcore-migrate | (same as api) | Exits after alembic upgrade head | — |

Startup order: PG+Redis+Qdrant+Ollama (parallel) → migrate (needs PG) → API (needs PG+Redis+Qdrant+migrate) → workers (needs API) → web (any time) → proxy (needs API+web).

## Network
- ekamcore-net bridge. Only proxy exposes 443/80 to host.
- Dev: also expose Qdrant(6333), Ollama(11434), API(8420), Web(3000).

## Volumes
Named: ekamcore-pgdata, ekamcore-qdrant-data, ekamcore-redis-data, ekamcore-models, ekamcore-caddy-data, ekamcore-caddy-config.
Bind: derivatives(thumbnails/OCR), logs.

## CI/CD Pipelines (.github/workflows/)
- **ci.yml**: PR pipeline. Path-filtered jobs. lint→typecheck→unit-test→integration-build. <15min.
- **nightly.yml**: 2am UTC. Full tests + integration + E2E + security scan + perf regression.
- **release.yml**: Manual dispatch. Full test → approval gate → build images → scan → SBOM → DMG → changelog → GitHub Release.
- **security.yml**: Weekly. pip-audit, pnpm audit, cargo audit, Trivy, license check.

## Makefile Targets
setup, up, down, clean, logs, restart, migrate, migration, seed, test, test-api, test-web, test-mobile, test-integration, coverage, lint, format, generate-clients, benchmark, rebuild, shell-api, shell-db, shell-redis.

## Dockerfile Pattern (multi-stage)
```dockerfile
FROM python:3.12-slim AS builder
# Install deps only
FROM python:3.12-slim AS runtime
COPY --from=builder /install /usr/local
USER nobody
```

## Caddyfile Pattern
```
localhost {
  handle /api/* { reverse_proxy ekamcore-api:8420 }
  handle /health { reverse_proxy ekamcore-api:8420 }
  handle { reverse_proxy ekamcore-web:3000 }
  log { output file /data/access.log { roll_size 100MiB roll_keep 7 } format json }
}
```

## Backup (2am daily)
pg_dump (custom format) + Qdrant snapshot API + config backup. Retain: 7 daily + 4 weekly. Restore: <30 minutes.

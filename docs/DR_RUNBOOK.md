# EkamCore Disaster Recovery Runbook (G-07 / ART-17)

Operational procedures for recovering from failure scenarios.
All scripts are in `scripts/dr/` and must be run from the project root.

## Quick Reference

| Scenario | Script | RTO Target |
|----------|--------|------------|
| Single container crash | `scripts/dr/container_recovery.sh` | < 2 min |
| Multiple containers down | `scripts/dr/container_recovery.sh` | < 5 min |
| Docker daemon crash | `scripts/dr/container_recovery.sh` | < 3 min after daemon returns |
| Database corruption | `scripts/dr/database_repair.sh --repair` | < 10 min |
| Full restore from backup | `scripts/dr/restore_from_backup.sh <path>` | < 15 min |
| Post-power-outage | `scripts/dr/post_power_outage.sh` | < 5 min |
| Disk full | `scripts/dr/disk_full_recovery.sh` | < 10 min |
| Model loading failure | `scripts/dr/model_reload.sh --all` | < 5 min |

---

## 1. Container Crash

### Symptoms
- Web UI unreachable or showing errors
- API returns 502/503
- `docker compose ps` shows exited/unhealthy containers
- Health endpoint returns `"degraded"` status

### Diagnosis
```bash
# Check which containers are down
docker compose ps

# Check container logs for the failing service
docker compose logs --tail=50 ekamcore-api

# Check for OOM kills
docker inspect --format='{{.State.OOMKilled}}' ekamcore-api

# Check Docker events for recent issues
docker events --since "10m" --until "0s" --filter event=die
```

### Recovery

**Automated (recommended):**
```bash
# Detect and recover automatically
./scripts/dr/container_recovery.sh

# Check only (no changes)
./scripts/dr/container_recovery.sh --check-only

# Recover a specific service
./scripts/dr/container_recovery.sh --service ekamcore-api
```

**Manual (single container):**
```bash
docker compose restart ekamcore-api
# Wait 15s, then verify
docker compose ps ekamcore-api
curl -s http://localhost:8420/health | python3 -m json.tool
```

**Manual (multiple containers — dependency order):**
```bash
# 1. Data layer first
docker compose up -d ekamcore-postgres ekamcore-redis ekamcore-qdrant
# Wait for healthy
sleep 15

# 2. Application layer
docker compose up -d ekamcore-api
sleep 10

# 3. Support services
docker compose up -d ekamcore-workers ekamcore-paperless ekamcore-web ekamcore-proxy
```

### Verification
```bash
./scripts/dr/verify_system_health.sh
```

---

## 2. Database Corruption

### Symptoms
- API returns 500 errors on data queries
- PostgreSQL logs show "invalid page" or "could not read block" errors
- `pg_amcheck` reports failures
- Unexpected empty results from queries that should return data

### Diagnosis
```bash
# Check PostgreSQL logs
docker compose logs --tail=100 ekamcore-postgres | grep -i "error\|corrupt\|invalid"

# Run integrity check (read-only)
./scripts/dr/database_repair.sh --verbose

# Manual check: verify table existence
docker compose exec ekamcore-postgres \
    psql -U ekamcore -d ekamcore \
    -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"

# Check for orphaned records
docker compose exec ekamcore-postgres \
    psql -U ekamcore -d ekamcore \
    -c "SELECT count(*) FROM ingestion_states ist LEFT JOIN files f ON ist.file_id=f.id WHERE f.id IS NULL"
```

### Recovery

**Automated repair (VACUUM, REINDEX, orphan cleanup):**
```bash
./scripts/dr/database_repair.sh --repair --verbose
```

**If repair fails — restore from backup:**
```bash
# List available backups
make backup-list

# Restore from most recent
./scripts/dr/restore_from_backup.sh /backups/YYYY-MM-DD_HH-MM-SS --yes
```

**If no backup available — rebuild from migrations:**
```bash
# WARNING: This loses all data
docker compose stop ekamcore-api ekamcore-workers

docker compose exec ekamcore-postgres \
    psql -U ekamcore -d postgres \
    -c "DROP DATABASE IF EXISTS ekamcore; CREATE DATABASE ekamcore OWNER ekamcore;"

docker compose run --rm ekamcore-migrate
docker compose up -d
```

### Verification
```bash
./scripts/dr/database_repair.sh --verbose
./scripts/dr/verify_system_health.sh
```

---

## 3. Backup Restore

### Symptoms
- Data loss discovered (accidental deletion, corruption)
- Need to roll back to a known good state
- Migration to new hardware

### Diagnosis
```bash
# List available backups with sizes
make backup-list
# or
ls -lh /backups/

# Inspect backup contents
ls -la /backups/YYYY-MM-DD_HH-MM-SS/
ls -la /backups/YYYY-MM-DD_HH-MM-SS/postgres/
ls -la /backups/YYYY-MM-DD_HH-MM-SS/qdrant/
```

### Recovery
```bash
# Full restore (interactive — asks for confirmation)
./scripts/dr/restore_from_backup.sh /backups/YYYY-MM-DD_HH-MM-SS

# Non-interactive (for automation)
./scripts/dr/restore_from_backup.sh /backups/YYYY-MM-DD_HH-MM-SS --yes
```

**What the restore does:**
1. Stops API, workers, web, proxy, paperless
2. Keeps postgres, redis, qdrant running
3. Drops and recreates `ekamcore` and `paperless` databases
4. Restores from pg_dump (custom format)
5. Copies Qdrant snapshots back, recovers collections
6. Runs `alembic upgrade head` (in case schema changed)
7. Starts all services
8. Verifies table counts and collection status
9. Writes `restore_report.json`

### Verification
```bash
# Check the restore report
cat restore_report.json | python3 -m json.tool

# Run full health check
./scripts/dr/verify_system_health.sh

# Spot-check key data
docker compose exec ekamcore-postgres \
    psql -U ekamcore -d ekamcore \
    -c "SELECT count(*) FROM users; SELECT count(*) FROM calendar_events; SELECT count(*) FROM files;"
```

---

## 4. Ollama Model Loading Failure

### Symptoms
- LLM queries return "AI features are starting up" errors
- Health endpoint shows `ollama: unhealthy`
- `ollama list` returns error or empty

### Diagnosis
```bash
# Check if Ollama process is running (native on Mac, not Docker)
pgrep -f ollama || echo "Ollama not running"

# Check available models
ollama list

# Check Ollama logs
cat ~/.ollama/logs/server.log | tail -50

# Test connectivity
curl -s http://localhost:11434/api/tags | python3 -m json.tool
```

### Recovery
```bash
# Start Ollama if not running
ollama serve &

# Wait for startup
sleep 5

# Pull required models if missing
ollama pull phi3:mini
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Verify models are loaded
ollama list

# Test inference
curl -s http://localhost:11434/api/generate \
    -d '{"model":"phi3:mini","prompt":"hello","stream":false}' | python3 -m json.tool
```

### Verification
```bash
curl -s http://localhost:8420/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Ollama:', d['services']['ollama']['status'])
"
```

---

## 5. Disk Full

### Symptoms
- PostgreSQL stops accepting writes ("no space left on device")
- Docker containers fail to start
- Backup script fails
- Ingestion pipeline stalls at EMBEDDING_QUEUED

### Diagnosis
```bash
# Check disk usage
df -h /

# Check Docker disk usage
docker system df

# Check volume sizes
docker system df -v | grep ekamcore

# Check largest directories
du -sh /backups/* 2>/dev/null | sort -rh | head -5
docker compose exec ekamcore-postgres du -sh /var/lib/postgresql/data
```

### Recovery

**Step 1: Free space immediately**
```bash
# Remove old Docker images and build cache
docker system prune -f

# Remove old backups (keep last 3)
ls -t /backups/ | tail -n +4 | xargs -I{} rm -rf /backups/{}

# Remove Docker build cache
docker builder prune -f
```

**Step 2: If PostgreSQL is in recovery mode**
```bash
# Restart postgres to clear WAL
docker compose restart ekamcore-postgres
sleep 10

# VACUUM to reclaim space
docker compose exec ekamcore-postgres \
    psql -U ekamcore -d ekamcore -c "VACUUM FULL"
```

**Step 3: If Qdrant storage is large**
```bash
# Check Qdrant storage
docker compose exec ekamcore-qdrant du -sh /qdrant/storage/

# Remove old snapshots (not current collections)
docker compose exec ekamcore-qdrant rm -rf /qdrant/snapshots/
```

### Verification
```bash
df -h /
./scripts/dr/verify_system_health.sh
```

---

## 6. Post-Power-Outage Recovery

### Symptoms
- Mac rebooted unexpectedly
- All services are down
- Docker Desktop may not have auto-started

### Recovery

**Step 1: Start Docker**
```bash
# On macOS, Docker Desktop should auto-start.
# If not:
open -a Docker

# Wait for Docker daemon
until docker info > /dev/null 2>&1; do
    echo "Waiting for Docker..."
    sleep 5
done
echo "Docker is ready"
```

**Step 2: Start EkamCore stack**
```bash
cd /path/to/EkamCore

# Start all services (Makefile handles Ollama too)
make up

# Or manually:
docker compose up -d
ollama serve &
```

**Step 3: Wait for health**
```bash
# Wait 30s for all services to initialize
sleep 30

# Run container recovery in case anything is stuck
./scripts/dr/container_recovery.sh

# Verify
./scripts/dr/verify_system_health.sh
```

**Step 4: Check data integrity**
```bash
# Quick DB check (non-destructive)
./scripts/dr/database_repair.sh

# If issues found:
./scripts/dr/database_repair.sh --repair
```

### Verification
```bash
./scripts/dr/verify_system_health.sh
curl -s http://localhost:8420/health | python3 -m json.tool
```

---

## 7. Automated Recovery Scripts (S15-010)

In addition to the manual procedures above, three automated scripts handle the most common recovery scenarios end-to-end:

### Post-Power-Outage (automated)
```bash
./scripts/dr/post_power_outage.sh
```
Performs all 6 steps automatically: checks Docker daemon (starts if needed), cleans stale containers, starts all services, waits for health checks (PostgreSQL, Redis, API), verifies data integrity (table counts, Qdrant collections), and runs the full health verification. Outputs pass/fail summary.

### Disk Full Recovery (automated)
```bash
./scripts/dr/disk_full_recovery.sh
```
Identifies space consumers, truncates oversized container logs, removes old backups (keeps last 3), runs `docker system prune`, checks Ollama cache, and restarts services if space was recovered. Skips cleanup if disk already has >= 30 GB free.

### Model Reload (automated)
```bash
# Reload all models
./scripts/dr/model_reload.sh --all

# Reload only Ollama models
./scripts/dr/model_reload.sh --ollama

# Reload only InsightFace models
./scripts/dr/model_reload.sh --face
```
Removes and re-pulls Ollama models (nomic-embed-text, phi3:mini, llama3.1:8b) with verification. Re-downloads InsightFace buffalo_l pack with SHA-256 checksum validation. Restarts workers to pick up new models.

---

## 8. Getting Help

EkamCore is a personal, local-first system. For troubleshooting:

1. **Check logs first:** `docker compose logs --tail=100 <service>`
2. **Run diagnostics:** Export a diagnostics bundle from the Manager app (Diagnostics tab)
3. **System health:** `./scripts/dr/verify_system_health.sh` generates a complete health report
4. **GitHub Issues:** File issues at the project repository with the diagnostics bundle attached (no personal data is included in the bundle)

---

## Appendix: Service Dependency Map

```
                    ┌─────────────┐
                    │   Ollama     │  (native on host)
                    │  :11434      │
                    └──────────────┘

┌──────────┐  ┌──────────┐  ┌──────────┐
│ Postgres │  │  Redis   │  │  Qdrant  │
│  :5432   │  │  :6379   │  │  :6333   │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │              │
     └──────┬──────┘──────────────┘
            │
     ┌──────┴──────┐
     │   Migrate   │  (one-shot)
     └──────┬──────┘
            │
     ┌──────┴──────┐  ┌────────────┐
     │     API     │  │ Paperless  │
     │   :8420     │  │  (internal)│
     └──┬───┬──────┘  └────────────┘
        │   │
   ┌────┘   └────┐
   │             │
┌──┴───┐  ┌─────┴────┐  ┌─────────┐
│Workers│  │   Web    │  │  Caddy  │
│      │  │  :3000   │  │ :80/443 │
└──────┘  └──────────┘  └─────────┘
```

## Appendix: Backup Schedule

| Type | Schedule | Retention | Location |
|------|----------|-----------|----------|
| Daily | 02:00 UTC | 7 days | `/backups/YYYY-MM-DD_HH-MM-SS/` |
| Weekly | Sundays | 4 weeks | Same directory, rotation keeps Sunday backups |

Run `make backup` manually or configure via cron:
```cron
0 2 * * * cd /path/to/EkamCore && make backup >> /var/log/ekamcore-backup.log 2>&1
```

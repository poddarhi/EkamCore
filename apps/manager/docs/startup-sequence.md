# Startup Sequence Specification (S03-006)

> **Implementation status:** Placeholder — full Tauri 2 implementation starts Sprint 3.
> This document is the authoritative spec for the 15-step cold-start sequence.
> Reference: ArchSpec § 4.2.

---

## Overview

Every time EkamCore Manager starts (or the user clicks "Restart Stack" in the
Dashboard), it executes a **sequential** 15-step sequence that brings up the entire
Docker stack in dependency order.

Each step:
- Emits a `startup_progress` event to the React frontend (`{step, total, label, status}`).
- Has an individual timeout.  On timeout, the step is retried up to **3 times** with a
  fixed 5 s delay between retries.  After 3 failures the sequence halts and the error
  is surfaced.
- On success, advances immediately to the next step (no artificial delay).
- Writes its result to the in-memory `StartupState` struct (Rust side) and emits a
  final `startup_step_result` event so the UI can persist state if needed.

**Total cold-start budget (first run, all images pre-pulled):** ≤ 120 s on M-series
hardware with SSD storage.

---

## Step 1 — Hardware Check

| | |
|-|-|
| **What** | Verify CPU is Apple Silicon, RAM ≥ 16 GB, macOS ≥ 13.0 |
| **Rust call** | `sysctl hw.optional.arm64`, `hw.memsize`, `sw_vers` |
| **Pass condition** | All three assertions hold |
| **Timeout** | 5 s |
| **On failure** | Halt startup. Display hardware requirements dialog. |
| **Frontend label** | "Checking hardware" |

This is identical to Setup Wizard Step 1 but runs every cold-start to catch the case
where the app is launched on an incompatible machine (e.g., after migration via
Migration Assistant from an Intel Mac — theoretically impossible with Rosetta, but
defended against regardless).

---

## Step 2 — Disk Space Check

| | |
|-|-|
| **What** | Verify ≥ 5 GB free on the boot volume (`statvfs "/"`) |
| **Pass condition** | `f_bavail × f_frsize ≥ 5 × 1024³` |
| **Timeout** | 5 s |
| **On failure** | Halt. Show "Low Disk Space" dialog with current free/used and a "Open Storage Settings" shortcut. |
| **Frontend label** | "Checking disk space" |

Note: The threshold at startup (5 GB) is lower than the Setup Wizard's (30 GB) because
images are already downloaded.  5 GB guards against Docker volume operations failing
mid-run due to disk full.

---

## Step 3 — Docker Daemon Check

| | |
|-|-|
| **What** | Verify Docker / OrbStack daemon is running and responsive |
| **Rust call** | `docker info` via bollard `DockerBuilder::connect_with_local_defaults()` |
| **Pass condition** | `docker_api.info().await` returns `Ok(_)` |
| **Timeout** | 10 s |
| **On failure** | Attempt to launch Docker Desktop (`open -a "Docker"`) or OrbStack (`open -a OrbStack`), wait 15 s, retry. If still failing, halt with "Docker is not running" dialog. |
| **Frontend label** | "Connecting to Docker" |

---

## Step 4 — Pull / Verify Images

| | |
|-|-|
| **What** | Check that all required images are present at the expected digest; pull any that are missing or outdated |
| **Rust call** | `docker image inspect <image>` per image; bollard `create_image` stream for missing ones |
| **Pass condition** | All images present |
| **Timeout** | 300 s (network pull; waived if all images already present) |
| **On failure** | Show which image failed to pull and the Docker error. Offer "Retry". |
| **Frontend label** | "Verifying Docker images" |

On a warm start where all images are present this step completes in < 1 s (inspect
only, no network I/O).

---

## Step 5 — Create Docker Network

| | |
|-|-|
| **What** | Ensure the `ekamcore-net` bridge network exists |
| **Rust call** | `docker network inspect ekamcore-net`; create if absent |
| **Pass condition** | Network exists with driver `bridge` |
| **Timeout** | 10 s |
| **On failure** | Log error and halt — network creation failure is fatal. |
| **Frontend label** | "Preparing network" |

Idempotent: if the network already exists, this step returns immediately.

---

## Step 6 — Start PostgreSQL

| | |
|-|-|
| **What** | Start the `ekamcore-postgres` container and wait until the database accepts connections |
| **Rust call** | bollard `start_container("ekamcore-postgres", None)` → poll `pg_isready` |
| **Health probe** | `pg_isready -h localhost -p 5432 -U ekamcore` every 2 s |
| **Pass condition** | `pg_isready` exits 0 |
| **Timeout** | 30 s |
| **On failure** | Tail last 20 lines of container logs, surface in "Database failed to start" dialog. |
| **Frontend label** | "Starting PostgreSQL" |

If the container is already running and healthy, the start call is a no-op and the
health probe passes immediately.

---

## Step 7 — Run Database Migrations

| | |
|-|-|
| **What** | Run the `ekamcore-migrate` container to apply any pending Alembic migrations |
| **Rust call** | bollard `create_container` + `start_container("ekamcore-migrate", None)` → wait for exit |
| **Pass condition** | Container exits with code 0 |
| **Timeout** | 60 s |
| **On failure** | Capture full stdout/stderr, display migration failure dialog with last 30 lines and a "View full log" link. |
| **Frontend label** | "Running migrations" |

The migrate container is short-lived — it runs to completion and exits.  This step
waits for the exit code before advancing.  Alembic's `upgrade head` is idempotent:
if the schema is already at the latest revision, it exits 0 immediately.

---

## Step 8 — Start Redis

| | |
|-|-|
| **What** | Start `ekamcore-redis` and wait until it accepts connections |
| **Rust call** | bollard `start_container` → probe with `redis-cli PING` |
| **Health probe** | TCP connect `localhost:6379` then `PING` command every 1 s |
| **Pass condition** | Response is `+PONG` |
| **Timeout** | 20 s |
| **On failure** | Show Redis container logs in error dialog. |
| **Frontend label** | "Starting Redis" |

---

## Step 9 — Start Qdrant

| | |
|-|-|
| **What** | Start `ekamcore-qdrant` and wait for the HTTP health endpoint |
| **Rust call** | bollard `start_container` → HTTP GET `http://localhost:6333/healthz` |
| **Health probe** | GET `/healthz` every 2 s; expect 200 `{"title": "qdrant - version ..."}` |
| **Pass condition** | HTTP 200 |
| **Timeout** | 30 s |
| **On failure** | Show Qdrant container logs in error dialog. |
| **Frontend label** | "Starting Qdrant" |

---

## Step 10 — Start Ollama

| | |
|-|-|
| **What** | Verify the Ollama native process is running (Ollama runs on the host, not in Docker) |
| **Rust call** | HTTP GET `http://localhost:11434/api/tags` |
| **Health probe** | GET `/api/tags` every 2 s |
| **Pass condition** | HTTP 200 |
| **Timeout** | 20 s |
| **On failure** | Attempt `open -a Ollama` (launches macOS app bundle). Retry after 10 s. If still failing, show "Ollama is not running" dialog with a [Download Ollama] link. |
| **Frontend label** | "Connecting to Ollama" |

Note: The Manager does **not** manage the Ollama process via Docker. Ollama runs
natively for Apple Neural Engine access.  EkamCore only checks that it is running.

---

## Step 11 — Verify / Pull Ollama Models

| | |
|-|-|
| **What** | Check that the required Ollama models are present; pull any that are missing |
| **Required models** | `phi3:mini` (language, ~2.2 GB), `llama3.1:8b` (language, ~4.7 GB), `nomic-embed-text` (embeddings, ~0.3 GB) |
| **Rust call** | GET `http://localhost:11434/api/tags` to list present models; POST `/api/pull` for missing ones |
| **Pass condition** | All three models present |
| **Timeout** | 600 s (network pull; waived if all present) |
| **Progress** | Emit per-model download progress events to frontend. Show model name, size downloaded, speed, and ETA. |
| **On failure** | Surface which model failed, show Ollama error. Offer "Retry". |
| **Frontend label** | "Checking AI models" |

On warm starts all models are present; this step completes in < 2 s (list check only).

---

## Step 12 — Start API

| | |
|-|-|
| **What** | Start `ekamcore-api` and wait for the health endpoint to return ready |
| **Rust call** | bollard `start_container` → HTTP GET `http://localhost:8420/health` |
| **Health probe** | GET `/health` every 2 s; expect `{"status": "ok", ...}` |
| **Pass condition** | HTTP 200 with `status == "ok"` |
| **Timeout** | 30 s |
| **On failure** | Capture API container logs (last 50 lines), surface in error dialog. |
| **Frontend label** | "Starting API" |

The API's lifespan startup (Qdrant collection init, feature flags load, Redis ping)
must complete before it returns 200 from `/health`. This is the correct readiness
signal.

---

## Step 13 — Start Workers

| | |
|-|-|
| **What** | Start `ekamcore-workers` and wait for the ARQ worker heartbeat |
| **Rust call** | bollard `start_container` → poll Redis key `arq:health:{worker_id}` |
| **Health probe** | Check Redis `arq:health:*` keys every 2 s (ARQ workers write a heartbeat on startup) |
| **Pass condition** | At least one heartbeat key present and timestamp within last 10 s |
| **Timeout** | 30 s |
| **On failure** | Show workers container logs. |
| **Frontend label** | "Starting background workers" |

---

## Step 14 — Start Proxy (Caddy)

| | |
|-|-|
| **What** | Start `ekamcore-proxy` (Caddy) and wait for TLS to be ready |
| **Rust call** | bollard `start_container` → HTTP GET `https://localhost/health` (self-signed cert, skip verify for health check) |
| **Health probe** | GET `https://localhost/health` every 2 s; expect 200 |
| **Pass condition** | HTTP 200 |
| **Timeout** | 30 s |
| **On failure** | Show Caddy container logs. Common failure: port 443 already in use — surface "Port 443 is in use by another process" with `lsof -i :443` output. |
| **Frontend label** | "Starting proxy" |

---

## Step 15 — System Ready

| | |
|-|-|
| **What** | Final end-to-end health verification and startup completion |
| **Checks** | Re-verify all six container health endpoints in parallel (PG, Redis, Qdrant, API, Workers, Proxy) |
| **Pass condition** | All six respond healthy within 5 s |
| **Timeout** | 10 s |
| **On completion** | Emit `startup_complete` event; transition Dashboard to "Running" state; start the 30-second watchdog polling loop. |
| **Frontend label** | "System ready" |

---

## Event Contract (Tauri → Frontend)

```typescript
// Emitted once per step as it begins
interface StartupProgressEvent {
  step: number;          // 1–15
  total: 15;
  label: string;         // Human-readable step name
  status: "in_progress";
}

// Emitted when a step completes (pass or fail)
interface StartupStepResultEvent {
  step: number;
  status: "passed" | "failed" | "retrying";
  attempt: number;       // 1, 2, or 3
  error?: string;        // Present on failure
  duration_ms: number;
}

// Emitted after Step 15 passes
interface StartupCompleteEvent {
  total_duration_ms: number;
  services: {
    postgres: "healthy";
    redis: "healthy";
    qdrant: "healthy";
    ollama: "healthy";
    api: "healthy";
    workers: "healthy";
    proxy: "healthy";
  };
}
```

---

## Timeout and Retry Table

| Step | Timeout | Max retries |
|------|---------|-------------|
| 1 Hardware | 5 s | 0 (no retry — not transient) |
| 2 Disk | 5 s | 0 |
| 3 Docker | 10 s | 1 (launch Docker, wait 15 s) |
| 4 Pull images | 300 s | 3 |
| 5 Network | 10 s | 3 |
| 6 PostgreSQL | 30 s | 3 |
| 7 Migrations | 60 s | 1 (idempotent but not retried aggressively) |
| 8 Redis | 20 s | 3 |
| 9 Qdrant | 30 s | 3 |
| 10 Ollama | 20 s | 1 (then launch app) |
| 11 Models | 600 s | 3 |
| 12 API | 30 s | 3 |
| 13 Workers | 30 s | 3 |
| 14 Proxy | 30 s | 3 |
| 15 Ready | 10 s | 3 |

---

## Warm Start vs. Cold Start

| Step | Cold start | Warm start (all containers running) |
|------|-----------|-------------------------------------|
| Pull images | May pull (network) | < 1 s (inspect only) |
| Start PG | ~3–5 s | ~0.5 s (already healthy) |
| Migrations | ~1–2 s (no-op if up to date) | ~1 s |
| Start Redis | ~1–2 s | ~0.5 s |
| Start Qdrant | ~5–8 s | ~0.5 s |
| Ollama models | May pull (network) | < 2 s |
| Start API | ~5–10 s | ~0.5 s |
| Start Workers | ~3–5 s | ~0.5 s |
| **Total** | **~30–60 s** | **~5–10 s** |

---

## Error State Transitions

```
Startup not started
     │ Manager launches
     ▼
Step N: in_progress
     │ pass
     ▼
Step N+1: in_progress ──────┐ (repeat until Step 15)
     │ fail (attempt < 3)   │
     ▼                       │
Step N: retrying (2 or 3)   │
     │ still failing         │
     ▼                       │
STARTUP HALTED              │
  Show error dialog          │
  Options:                   │
    • Retry from step N      │
    • View logs              │
    • Open Docker Desktop    │
     │ user retries          │
     └────────────────────── ┘
```

---

## Relationship to the Watchdog (S04-005)

Once `startup_complete` fires, the startup sequence hands off to the Watchdog
(`watchdog.rs`).  The Watchdog:
- Polls `docker inspect` every **30 seconds** for each container.
- On unhealthy → restart with exponential backoff: 5 s → 15 s → 45 s → 135 s → 300 s.
- After **5 consecutive failures** on one container: stops auto-restart, sends a
  macOS notification, and shows a red status tile in the Dashboard.
- If any container restarts > 3 times within 1 hour → prompts diagnostics export.

The startup sequence itself is **not** responsible for health monitoring after
Step 15 — that is entirely the Watchdog's domain.

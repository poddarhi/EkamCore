# Container Watchdog Specification (S04-005)

> **Implementation status:** Specification — Tauri 2 implementation starts Sprint 5.
> This document is the authoritative spec for Docker container health monitoring
> and automatic restart behavior.

---

## Overview

The Watchdog is a Rust background task inside the EkamCore Manager that monitors
every Docker container in the `ekamcore` project.  It detects health failures,
automatically restarts containers with exponential backoff, and escalates to the
user when automatic recovery is exhausted.

The Watchdog starts after Startup Sequence step 15 completes and runs until the
Manager process exits or the user clicks "Stop Stack."

---

## Health Check Loop

| | |
|-|-|
| **Interval** | 30 seconds |
| **Method** | `docker inspect --format='{{.State.Health.Status}}'` for containers with HEALTHCHECK; `docker inspect --format='{{.State.Status}}'` for those without |
| **Healthy** | Health status is `healthy` or running status is `running` (for containers without HEALTHCHECK) |
| **Unhealthy** | Health status is `unhealthy`, or container status is `exited` / `dead` / `restarting` |

Each tick:

1. List all containers with label `com.docker.compose.project=ekamcore`.
2. For each container, read health/running status.
3. If healthy: reset that container's consecutive failure counter to 0.
4. If unhealthy: increment failure counter, enter Restart Flow.

The loop emits a `watchdog_tick` Tauri event with the full status map so the
Dashboard can render live container status indicators.

---

## Restart Flow

When a container is detected as unhealthy:

### Step 1 — Exponential Backoff Delay

Wait before restarting.  The delay is determined by the consecutive failure count:

| Consecutive Failure | Delay |
|---------------------|-------|
| 1 | 5 s |
| 2 | 15 s |
| 3 | 45 s |
| 4 | 135 s |
| 5+ | 300 s (cap) |

Formula: `min(5 * 3^(n-1), 300)` seconds, where `n` is the failure count.

### Step 2 — Restart Attempt

```
docker restart <container_name> --time 10
```

Timeout: 30 seconds.  If the restart command itself times out, it counts as
another failure.

### Step 3 — Post-Restart Health Verification

Wait up to 60 seconds for the container to report `healthy` (or `running` for
containers without HEALTHCHECK).  Poll every 5 seconds.

- If healthy within 60 s: log success, reset failure counter.
- If still unhealthy: increment failure counter, loop back to Step 1.

### Step 4 — Failure Escalation (5 consecutive failures)

After **5 consecutive failures** for a single container:

1. **Stop auto-restart** for that container.  It remains in whatever state it is in.
2. **Send macOS notification** via `NSUserNotificationCenter` (or `UNUserNotificationCenter`):
   - Title: "EkamCore: {container_name} needs attention"
   - Body: "Automatic restart failed 5 times. Open EkamCore Manager to investigate."
   - Action button: opens the Manager Dashboard.
3. **Emit Tauri event** `watchdog_escalation` with `{ container, failures, last_error }`.
4. The Dashboard shows a persistent error banner for the affected container.

The user can manually retry from the Dashboard, which resets the failure counter
and re-enables auto-restart for that container.

---

## Chronic Instability Detection

A container is considered **chronically unstable** if it accumulates **more than
3 restarts within any rolling 1-hour window**.

When detected:

1. Emit `watchdog_chronic_instability` Tauri event with `{ container, restart_count, window_start }`.
2. Log a structured warning: `watchdog_chronic_instability, container=..., restarts=...`.
3. The Dashboard marks the container with an amber "Unstable" badge (distinct from
   the red "Failed" state of a hard escalation).
4. If the user has enabled notifications in Settings, send a macOS notification:
   - Title: "EkamCore: {container_name} is unstable"
   - Body: "{n} restarts in the last hour."

Chronic instability does **not** disable auto-restart — it is an informational
escalation.  The container continues to be auto-restarted per the normal flow.

---

## Restart History

The Watchdog maintains an in-memory restart history per container:

```rust
struct RestartRecord {
    container: String,
    timestamp: DateTime<Utc>,
    trigger: RestartTrigger,    // AutoRestart | ManualRetry
    outcome: RestartOutcome,    // Success | Failure(String)
    attempt_number: u32,        // 1-indexed within the current failure sequence
    delay_secs: u32,            // Backoff delay applied before this attempt
}
```

History is capped at **100 records per container** (ring buffer, oldest evicted).
It is not persisted to disk — it resets on Manager restart.

The Dashboard queries this history via a Tauri command:

```
#[tauri::command]
async fn get_restart_history(container: String) -> Vec<RestartRecord>
```

---

## Container-Specific Notes

| Container | HEALTHCHECK | Notes |
|-----------|-------------|-------|
| `ekamcore-postgres` | Yes (`pg_isready`) | Critical dependency — if down, API is non-functional |
| `ekamcore-redis` | Yes (`redis-cli ping`) | Critical dependency |
| `ekamcore-api` | Yes (`/api/v1/health`) | Depends on postgres + redis |
| `ekamcore-qdrant` | Yes (HTTP health endpoint) | Degraded search if down, but core queries still work |
| `ekamcore-paperless` | No | Optional; uses running status check |

---

## Configuration

All values are compile-time constants in the initial implementation.  Sprint 6+
may expose them in Settings.

| Constant | Value | Description |
|----------|-------|-------------|
| `WATCHDOG_INTERVAL_SECS` | 30 | Health check poll interval |
| `BACKOFF_BASE_SECS` | 5 | Initial restart delay |
| `BACKOFF_MULTIPLIER` | 3 | Exponential multiplier |
| `BACKOFF_CAP_SECS` | 300 | Maximum restart delay |
| `MAX_CONSECUTIVE_FAILURES` | 5 | Failures before disabling auto-restart |
| `CHRONIC_RESTART_THRESHOLD` | 3 | Restarts within window to trigger instability |
| `CHRONIC_WINDOW_SECS` | 3600 | Rolling window for chronic detection |
| `RESTART_TIMEOUT_SECS` | 30 | Timeout for `docker restart` command |
| `POST_RESTART_VERIFY_SECS` | 60 | Max wait for post-restart health check |
| `HISTORY_CAP_PER_CONTAINER` | 100 | Ring buffer size for restart records |

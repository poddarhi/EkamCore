# Resource Limits & Memory Budget (S04-005)

> **Implementation status:** Specification — enforced via `docker-compose.yml`
> memory limits and Manager thermal state management.
> Reference: ArchSpec § 3.1 (Hardware Requirements).

---

## Overview

EkamCore targets a **16 GB Apple Silicon Mac** as the minimum supported hardware.
Of that 16 GB, macOS, Finder, Safari, and other user apps typically consume 5-7 GB,
leaving ~9-10 GB for the EkamCore stack.  The memory budget below ensures the stack
runs comfortably alongside normal desktop use without swapping.

---

## Container Memory Limits

All limits are set via `deploy.resources.limits.memory` in `docker-compose.yml`.
Containers that exceed their limit are OOM-killed by Docker and restarted by the
Watchdog.

| Container | Memory Limit | Typical Usage | Notes |
|-----------|-------------|---------------|-------|
| `ekamcore-postgres` | 1.5 GB | 800 MB - 1.2 GB | `shared_buffers=256MB`, `work_mem=16MB`, `effective_cache_size=512MB` |
| `ekamcore-redis` | 512 MB | 100 - 300 MB | `maxmemory 384mb`, `maxmemory-policy allkeys-lru` |
| `ekamcore-api` | 1 GB | 300 - 600 MB | Uvicorn with 2 workers. Ingestion pipeline batches limited to prevent spikes. |
| `ekamcore-qdrant` | 1.5 GB | 500 MB - 1 GB | HNSW index lives in memory. Scales with collection count. |
| `ekamcore-paperless` | 1 GB | 400 - 700 MB | Optional. OCR processing can spike; limit prevents runaway. |
| **Container total** | **5.5 GB** | | |

### Ollama (Native — Not Containerized)

Ollama runs natively on the host (not in Docker) to access the Apple Neural Engine
and unified memory directly.

| Setting | Value | Rationale |
|---------|-------|-----------|
| `OLLAMA_KEEP_ALIVE` | `5m` | Unloads model from memory 5 minutes after last request. Frees 4-5 GB when idle. |
| `OLLAMA_NUM_PARALLEL` | `1` | Single concurrent request prevents memory doubling from parallel context windows. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Only one model loaded at a time. Switching models evicts the previous one. |

**Peak memory when model loaded:** ~4-5 GB (llama3.1:8b quantized).
**Memory when idle (after keepalive):** ~50 MB (Ollama server process only).

### Total Memory Budget

| State | Container Stack | Ollama | Total EkamCore | Remaining for macOS + Apps |
|-------|----------------|--------|----------------|---------------------------|
| Idle (no active query) | ~3 GB | ~50 MB | ~3 GB | ~13 GB |
| Active query (model loaded) | ~4 GB | ~5 GB | ~9 GB | ~7 GB |
| Peak (query + ingestion + sync) | ~5 GB | ~5 GB | ~10 GB | ~6 GB |

On a 16 GB machine, the worst-case peak leaves 6 GB for macOS and user apps,
which is sufficient for normal desktop use (browsing, mail, notes).

---

## Thermal State Management

The Manager app monitors system thermal pressure and publishes a state to Redis
so the API resource controller can throttle background work.

### Thermal States

| State | Redis Value | Trigger | API Behavior |
|-------|------------|---------|--------------|
| **Nominal** | `nominal` | Thermal pressure is `nominal` | All tasks run normally |
| **Fair** | `fair` | Thermal pressure is `fair` | No throttling (early warning only) |
| **Serious** | `serious` | Thermal pressure is `serious` | P4 batch size halved. P3 continues normally. |
| **Critical** | `critical` | Thermal pressure is `critical` | All P3 and P4 tasks paused. Only P1 (interactive) and P2 (pack execution) proceed. |

### Implementation

The Manager reads macOS thermal state via IOKit:

```rust
// Simplified — actual implementation uses IOKit bindings
fn read_thermal_pressure() -> ThermalState {
    // NSProcessInfo.processInfo.thermalState
    // Maps: .nominal → Nominal, .fair → Fair, .serious → Serious, .critical → Critical
}
```

The state is published to Redis key `rc:thermal_state` on DB 3 (cache) every
30 seconds (aligned with the Watchdog tick).  The key has a 90-second TTL so it
auto-expires if the Manager crashes, causing the API to fall back to `nominal`.

### Resource Controller Integration

The API resource controller (`api/services/resource_controller.py`) reads
`rc:thermal_state` before granting slots to P3/P4 tasks:

- **Critical:** `acquire_slot(P3)` and `acquire_slot(P4)` raise `ResourceThrottledError`.
  Workers catch this and defer the task.
- **Serious:** `get_p4_batch_size(default)` returns `default // 2` (minimum 1).
  Workers process fewer items per batch.
- **Nominal/Fair:** No throttling.

### Ollama Thermal Response

When thermal state reaches **serious** or **critical**, the Manager additionally:

1. Sends `POST /api/generate` with an empty prompt and `keep_alive: 0` to Ollama,
   which unloads the model from memory immediately (freeing ~4-5 GB).
2. The API query router's Ollama health check will return `unavailable`, causing
   queries to fall back to deterministic/search results with a degraded banner.
3. Once thermal state returns to **nominal** or **fair**, the next user query
   will reload the model on demand (cold start ~10-15 s).

---

## Swap Prevention

To avoid macOS memory pressure warnings and SSD wear from swap:

1. Container memory limits are hard caps (OOM kill, not swap).
2. Ollama keepalive ensures model memory is released when idle.
3. Ingestion pipeline processes files in batches of 10 (configurable) to bound
   peak memory from text extraction + embedding.
4. Qdrant uses mmap for large collections, keeping resident memory bounded.
5. The Watchdog monitors container memory via `docker stats` and logs a warning
   if any container exceeds 80% of its limit.

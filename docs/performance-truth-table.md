# Performance Truth Table

Sprint tasks: `S0-019`, `S0-020`  
Date: 2026-03-16

## Purpose

This document captures the first grounded performance baseline for EkamCore's Sprint 0 stack. The goal is not to claim polished production performance. The goal is to replace guesswork with measured or explicitly estimated values.

## Measurement Caveats

- Host: see [reference-host-and-test-assumptions.md](/Users/hiteshpoddar/EkamCore/docs/reference-host-and-test-assumptions.md)
- These numbers were captured on a real development machine, not on a controlled benchmark host.
- Docker Desktop was already installed and running.
- No EkamCore compose services are defined yet, so Docker numbers reflect substrate overhead rather than the future full stack.
- Backend measurements used `pnpm dev:backend`, which currently runs `uvicorn --reload`.
- Manager app measurements used `pnpm dev:manager`, which currently runs the Tauri development shell plus Vite and incremental Rust build steps.
- Memory values are best-effort summed resident memory snapshots across visible processes. They should be treated as directional upper bounds for Sprint 0 planning.
- CPU values are lightweight idle snapshots, not long-run benchmark averages.

## Startup And Readiness

| Surface | Metric | Value | Confidence | Notes |
| --- | --- | --- | --- | --- |
| Runtime bootstrap | `pnpm runtime:start` warm start | `0.55s` | Measured | Docker Desktop already running; no compose services defined yet. |
| Backend stub | `pnpm dev:backend` to `GET /v1/health = 200` | `0.74s` | Measured | Warm start on the reference host. |
| Manager app shell | Vite dev server ready | `~0.10s` | Measured | Vite reported `94ms` to `109ms` across warm launches. |
| Manager app shell | Incremental Rust desktop handoff | `~0.12s` to `0.14s` | Measured | Cargo incremental build step reported by Tauri dev logs. |
| Manager app shell | Warm end-to-end dev-shell launch | `~1s` to `3s` | Estimated | Reasonable estimate from repeated warm launches; exact packaged `.app` launch time is still pending. |
| Docker Desktop cold launch | App launch to engine ready | Pending | Placeholder | Not measured in Sprint 0 because this machine is being used as a live development environment. |

## Idle Resource Snapshot

| Surface | Memory | CPU | Confidence | Notes |
| --- | --- | --- | --- | --- |
| Docker Desktop substrate | `~793 MB` RSS | `~0.7%` | Measured | Substrate-only overhead before future EkamCore data and model services are added. |
| Backend stub in dev mode | `~102 MB` RSS | `~34%` | Measured with caveat | CPU is dominated by `uvicorn --reload` file-watch behavior and should not be treated as a production target. |
| Manager app dev shell | `~462 MB` RSS | `~0%` | Estimated from captured process snapshots | Includes `pnpm`, Tauri CLI, Vite, and the debug app process together, so it overstates a packaged app footprint. |
| Reference Sprint 0 live slice subtotal | `~1.36 GB` RSS | Low single-digit to moderate | Estimated | Docker Desktop + backend dev shell + manager dev shell, excluding future data services and local model runtime. |

## Local Responsiveness

| Surface | Metric | Value | Confidence | Notes |
| --- | --- | --- | --- | --- |
| Backend `GET /v1/health` | Warm local response | `0.9 ms avg` | Measured | `10` requests against `127.0.0.1:8808`. |
| Backend `GET /v1/version` | Warm local response | `0.8 ms avg` | Measured | `10` requests against `127.0.0.1:8808`. |
| Backend `GET /v1/workspaces/personal/today` | Warm local response | `1.1 ms avg` | Measured | `10` requests against `127.0.0.1:8808`. |
| Manager shell HTTP surface | Warm local response | `0.2 ms avg` | Measured | `10` requests against `127.0.0.1:1420` while the Tauri dev shell was running. |

## Interpretation

- Docker Desktop already consumes meaningful memory before PostgreSQL, Qdrant, Ollama, workers, thumbnails, or photo processing are introduced.
- The Sprint 0 backend itself is lightweight in memory, but the current development-mode reloader creates misleadingly high idle CPU. Future resource planning should re-measure the backend in non-reload service mode.
- The manager app is acceptable for Sprint 0 as a development shell, but its current dev-mode memory number should not be confused with the eventual packaged macOS app footprint.
- A `16 GB` caution host is still plausible for future support, but it will need tighter concurrency limits and honest caveats once the real service stack grows.

## Pending Follow-Up Measurements

- Cold Docker Desktop launch time on a clean machine
- Manager packaged `.app` launch time instead of Tauri dev-shell proxy timing
- Backend CPU and memory in non-reload service mode
- Full-stack measurements once PostgreSQL, Qdrant, and workers are added
- Lower-profile `16 GB` host validation

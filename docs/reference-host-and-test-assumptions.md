# Reference Host And Test Assumptions

Sprint task: `S0-018`  
Date: 2026-03-16

## Purpose

This note defines the concrete machine assumptions for early EkamCore runtime and performance work so Sprint 0 and Sprint 1 discussions refer to the same baseline.

## Reference Host

The current Sprint 0 reference host is the machine used for the runtime spike and thin-slice measurements:

- Model: MacBook Air (`Mac16,12`)
- Chip: Apple M4
- CPU: 10 cores (`4` performance, `6` efficiency)
- Memory: `24 GB`
- OS: macOS `26.1` (`25B78`)
- Architecture: Apple silicon

## Working Assumptions

- Early runtime and performance work targets a `24 GB` Apple silicon Mac first.
- The v1 host expectation is an always-on Mac, even if Sprint 0 development happens on a laptop-form machine.
- Docker Desktop is part of the accepted v1 runtime path and therefore part of the host resource budget.
- Sprint 0 numbers are gathered on a real development machine, not a controlled benchmark rig.
- Sprint 0 measurements should be treated as grounding data, not as product marketing claims.

## Lower-Profile Caveat Host

Sprint 0 should keep one lower-profile host in view even though it is not fully measured yet:

- Profile: Apple silicon Mac with `16 GB` memory
- Examples: MacBook Air or Mac mini class hardware

Expected caveats on that lower profile:

- Docker Desktop overhead consumes a meaningful part of available memory before PostgreSQL, Qdrant, model runtime, OCR, or photo-processing workloads are added.
- Local AI, embeddings, and media/background work will compete more aggressively with the foreground Today/Recap experience.
- Cold starts and recovery actions will likely be slower than the reference host.
- The manager app and backend may remain usable, but feature concurrency and background throughput will require tighter limits.

## Explicit Non-Target For Sprint 0

- `8 GB` Apple silicon Macs are not a Sprint 0 validation target.
- The team should not imply comfortable v1 support on `8 GB` machines until real end-to-end validation proves otherwise.

## Team Guidance

- Treat the `24 GB` Apple silicon profile as the reference host for early acceptance conversations.
- Treat the `16 GB` Apple silicon profile as the caution host that still needs dedicated validation.
- Do not generalize Sprint 0 performance numbers beyond these assumptions.
- Revisit minimum supported hardware before Sprint 1 exits or before any public-facing system requirement claim is made.

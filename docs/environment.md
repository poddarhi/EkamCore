# Environment Variables

This document is the index for environment-variable documentation used by the current Sprint 0 runtime and demo slice.

## Scope

Every new runtime variable should be documented in two places:

1. The nearest `.env.example` file for the app or package that uses it.
2. This index, so new engineers can find the right source quickly.

## Placeholder Map

| Area | Placeholder file | Status |
| --- | --- | --- |
| Repository-wide tooling | `.env.example` | Runtime overrides documented |
| Backend service | `apps/backend/.env.example` | Placeholder only |
| Manager app | `apps/manager-app/.env.example` | Live thin-slice backend URL documented |
| Mobile app | `apps/mobile/.env.example` | Placeholder only |

## Current Variables

| Variable | Area | Default | Purpose |
| --- | --- | --- | --- |
| `EKAMCORE_DOCKER_CONTEXT` | Repository runtime scripts | `desktop-linux` | Selects the local Docker context used by `pnpm runtime:start` and `pnpm runtime:stop`. |
| `EKAMCORE_DOCKER_WAIT_SECONDS` | Repository runtime scripts | `120` | Sets how long the runtime bootstrap waits for Docker Desktop readiness. |
| `VITE_EKAMCORE_BACKEND_BASE_URL` | Manager app | `http://127.0.0.1:8808` | Points the manager app live Sprint 0 slice at the local FastAPI stub backend. |

## Documentation Rules

- Prefer explicit variable names and defaults once a service is runnable.
- Keep secrets out of the repository.
- Update this file when a new app or package introduces its own env file.
- Keep the contract server URL, manager app defaults, and backend dev commands aligned when the local API port changes.

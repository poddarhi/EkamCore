# EkamCore

EkamCore is a private local life assistant for your knowledge, memory, and daily operations.

This repository is currently in Sprint 0. The goal of `S0-001` is to establish the monorepo layout, baseline tooling direction, and onboarding docs before runnable services are added.

## Repository Layout

- `apps/backend` - Python backend service (`FastAPI` planned in `S0-015`)
- `apps/manager-app` - macOS manager app (`Tauri + React/TypeScript` planned in `S0-007`)
- `apps/mobile` - mobile client (`React Native` planned later in Sprint 0 / Sprint 3)
- `packages/shared-types` - shared TypeScript types and generated client artifacts
- `infra` - runtime, container, and local orchestration assets
- `docs/adr` - architecture decision records
- `docs/contracts` - API contract source and notes
- `test-fixtures` - reusable sparse-data, multi-user, photo, and file fixtures

## Tooling Direction

- `pnpm` workspaces manage the JavaScript and TypeScript surfaces plus shared packages.
- `apps/backend` is intentionally kept as a standalone Python app directory until its packaging is added in `S0-015`.
- Repository-wide documentation, contracts, and ADRs live under `docs/`.

## Prerequisites

- macOS on Apple silicon
- [Homebrew](https://brew.sh/)
- Node.js `22.x`
- `pnpm` `10.x` or newer
- Python `3.13.x`
- Docker Desktop for the upcoming runtime substrate spike

## Bootstrap

Install the baseline toolchain:

```sh
brew install node pnpm python@3.13
brew install --cask docker-desktop
```

Install workspace dependencies:

```sh
pnpm install
```

The backend does not yet have a committed Python package manager. That choice is intentionally deferred until the backend skeleton is added in `S0-015`.

## Development Expectations

- Keep app-specific notes in each app directory `README.md`.
- Add environment variable documentation before introducing new runtime configuration.
- Prefer shared contract types over hand-maintained duplicate client models.
- Capture repository-level decisions in `docs/adr` once the ADR workflow is added.
- Follow the engineering workflow in `docs/engineering-workflow.md` for branches, pull requests, merge rules, and foundational artifact changes.

## Current Status

The repository currently contains structure and placeholders only. Framework bootstrap, runtime orchestration, API contracts, and runnable services will be added in later Sprint 0 tasks.

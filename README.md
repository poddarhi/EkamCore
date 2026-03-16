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
- Node.js `24.14.0` (LTS)
- `pnpm` `10.x` or newer
- Python `3.13.x`
- Rust stable toolchain with `cargo` on `PATH`
- Docker Desktop for the accepted v1 local runtime substrate

## Bootstrap

Install the baseline toolchain:

```sh
brew install node@24 pnpm python@3.13
brew link --overwrite --force node@24
brew pin node@24
brew install rustup-init
brew install --cask docker-desktop
```

Initialize Rust if it is not already configured:

```sh
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
rustup default stable
```

The manager app package scripts already include the common macOS `rustup` paths above, so once Rust is initialized you should not need to re-export that `PATH` for every new terminal session.

Install workspace dependencies:

```sh
pnpm install
```

The backend now uses a simple `requirements.txt` bootstrap for Sprint 0 so the FastAPI stub service can run without adding extra packaging complexity early.

Validate the canonical API contract and regenerate the shared TypeScript package:

```sh
pnpm lint:api
pnpm generate:shared-types
```

## Development Expectations

- Keep app-specific notes in each app directory `README.md`.
- Add environment variable documentation before introducing new runtime configuration.
- Prefer shared contract types over hand-maintained duplicate client models.
- Capture repository-level decisions in `docs/adr` once the ADR workflow is added.
- Follow the engineering workflow in `docs/engineering-workflow.md` for branches, pull requests, merge rules, and foundational artifact changes.
- Use `pnpm dev:manager` to launch the desktop manager app shell once the manager app dependencies are installed.
- Use `pnpm dev:backend` to run the FastAPI stub service once the backend virtualenv dependencies are installed.

## Current Status

The repository now includes a runnable Sprint 0 manager app shell, a service supervision adapter, the canonical OpenAPI contract, generated shared TypeScript types, and a FastAPI stub backend. Real source adapters, storage, auth enforcement, and richer operational features will be added in later Sprint 0 tasks.

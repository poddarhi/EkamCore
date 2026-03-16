# Manager App

This directory hosts the EkamCore macOS manager app.

Current Sprint 0 direction:

- platform: `Tauri`
- UI: `React + TypeScript`
- milestone: `S0-026` thin end-to-end live slice implemented

## Included in the Current Sprint 0 Shell

- Tauri desktop shell
- React + TypeScript frontend
- service supervision snapshot with Tauri-first runtime checks
- live backend health, version, and Today polling with fallback behavior
- navigation and content for:
  - Setup
  - Service Status
  - Logs
  - Settings
  - Diagnostics

## Prerequisites

- Node `24.14.0`
- `pnpm`
- Rust stable toolchain with `cargo` on `PATH`
- Apple command line developer tools

If you are using Homebrew `rustup`, initialize and expose it before running the app:

```sh
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
rustup default stable
```

The package scripts already include the common macOS `rustup` paths, so after that one-time initialization you should not need to re-export `PATH` in every new terminal session.

## Commands

Set the backend URL if you are not using the default contract address:

```sh
cp .env.example .env.local
```

Default value:

```sh
VITE_EKAMCORE_BACKEND_BASE_URL=http://127.0.0.1:8808
```

Start the FastAPI stub backend first:

```sh
pnpm dev:backend
```

Run the desktop app in development mode:

```sh
pnpm --filter @ekamcore/manager-app tauri:dev
```

Run only the web shell:

```sh
pnpm --filter @ekamcore/manager-app dev
```

Build the frontend bundle:

```sh
pnpm --filter @ekamcore/manager-app build
```

The manager app is currently a Sprint 0 shell plus the first live manager-to-backend demo path. Auth enforcement, richer actions, and deeper source integration will be layered in later tasks.

# Manager App

This directory hosts the EkamCore macOS manager app.

Current Sprint 0 direction:

- platform: `Tauri`
- UI: `React + TypeScript`
- milestone: `S0-007` project skeleton implemented

## Included in the S0-007 Shell

- Tauri desktop shell
- React + TypeScript frontend
- placeholder navigation and content for:
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

## Commands

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

The manager app is currently a Sprint 0 shell. Real runtime supervision, health polling, logs, and diagnostics behavior will be layered in later tasks.

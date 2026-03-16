# Infrastructure

This directory will hold local runtime and orchestration assets for EkamCore.

Current Sprint 0 uses:

- runtime substrate notes and comparison artifacts
- local runtime bootstrap scripts in `infra/runtime`
- container or service orchestration assets once the runtime decision is locked

The runtime direction is now locked to Docker Desktop for v1. End-user onboarding should assume a clean Mac with no preinstalled Homebrew or Docker Desktop.

Use one of these commands to work with the local runtime bootstrap:

```sh
pnpm runtime:start
pnpm runtime:stop
```

See `infra/runtime/README.md` for the current bootstrap procedure and known failure modes.

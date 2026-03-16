# Runtime Bootstrap

This directory contains the local runtime bootstrap procedure for EkamCore's accepted v1 substrate: Docker Desktop behind the manager app.

## Scope

At this stage of Sprint 0, the bootstrap scripts do two things:

- ensure Docker Desktop is installed and reachable
- prepare the Docker runtime so later Sprint 0 tasks can add real EkamCore services

The repository does not yet define a real EkamCore Docker Compose stack. Until service scaffolding exists, `start` means "Docker Desktop is up and ready for EkamCore" and `stop` means "tear down any EkamCore compose project if one exists."

## Commands

Preferred commands:

```sh
pnpm runtime:start
pnpm runtime:stop
```

Direct script usage also works:

```sh
./infra/runtime/start.sh
./infra/runtime/stop.sh
```

## Current Compose Convention

When the first EkamCore service stack is added, the bootstrap scripts will look for:

```text
infra/runtime/docker-compose.yml
```

If that file does not exist yet, `start` still validates the runtime substrate and exits successfully.

## Prerequisites

- macOS on Apple silicon
- Docker Desktop installed
- Docker Desktop first-run setup completed
- `docker` available on `PATH`

## What Start Does

1. Verifies the Docker CLI is installed.
2. Verifies `/Applications/Docker.app` exists.
3. Launches Docker Desktop if the engine is not yet ready.
4. Waits for the Docker engine to become reachable.
5. If `infra/runtime/docker-compose.yml` exists and defines services, runs `docker compose up -d`.
6. If no compose file exists yet, reports that the substrate is ready for later tasks.

## What Stop Does

1. Verifies whether Docker is installed and reachable.
2. If `infra/runtime/docker-compose.yml` exists and defines services, runs `docker compose down --remove-orphans`.
3. If no EkamCore compose file exists yet, exits successfully with a no-op message.

The stop script intentionally does not quit Docker Desktop itself. Docker Desktop may be used for other work on the machine, and EkamCore should not shut down unrelated containers as a side effect.

## Common Failure Modes

### Docker Desktop Not Installed

Symptoms:

- `docker` command missing
- `/Applications/Docker.app` missing

Resolution:

- install Docker Desktop
- complete the first-run setup

### Docker Desktop Installed but Engine Not Ready

Symptoms:

- Docker app opens but `docker info` still fails

Resolution:

- wait for Docker Desktop to finish starting
- check first-run prompts or macOS approvals
- rerun `pnpm runtime:start`

### First-Run Prompts or Privileged Setup Required

Symptoms:

- Docker Desktop asks for admin approval, helper install, or macOS permissions

Resolution:

- complete the prompts in Docker Desktop
- rerun `pnpm runtime:start`

### Compose File Missing

Symptoms:

- start command reports that no EkamCore compose file exists yet

Resolution:

- this is expected until later Sprint 0 tasks add real services

### Compose File Exists but Services Fail

Symptoms:

- `docker compose up -d` exits with an error

Resolution:

- inspect the compose file
- inspect `docker compose logs`
- confirm Docker Desktop still reports a healthy engine

## Validation Notes

This bootstrap path was exercised on the reference Mac after Docker Desktop installation and first-run setup. Full EkamCore service startup validation will happen once the first backend/service scaffolding exists.

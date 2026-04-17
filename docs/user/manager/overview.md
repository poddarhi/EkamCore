# Manager Overview

The Manager is a native macOS application that serves as the control centre
for EkamCore. It handles every operational task so you never need to touch
Docker or the terminal.

## What the Manager does

- **Service lifecycle** -- Starts, stops, and restarts the Docker containers
  that make up EkamCore (PostgreSQL, Meilisearch, Ollama, the API server,
  and others).
- **Setup wizard** -- Guides you through first-run configuration: agreeing to
  privacy terms, choosing source folders, and starting services for the
  first time.
- **Dashboard** -- A single-screen view of service health, storage usage, and
  key metrics. See [Dashboard](dashboard.md) for details.
- **Jobs** -- Lists background tasks such as folder scans, face clustering
  runs, and PLA Pack generation. You can view progress, cancel a running job,
  or re-run a completed one.
- **Storage** -- Shows disk usage per service, lets you clean Docker build
  cache, and provides a shortcut to prune unused images.
- **Diagnostics** -- Collects logs from all services into a single view. You
  can filter by service, severity, or time range and export a support bundle.
- **Updates** -- Checks for new EkamCore releases, downloads them, and applies
  them in place with automatic rollback on failure. See
  [Updates](updates.md) for the full process.
- **Backup** -- Runs scheduled and on-demand backups of the database and
  configuration. Backups are stored in
  `~/Library/Application Support/EkamCore/backups/`.

## Auto-start on login

By default the Manager launches when you log in to macOS and immediately
starts all services. You can disable this in **Manager Settings > Auto-start
on login**. When disabled, you must open the Manager manually and click
**Start All**.

The Manager itself runs as a menu-bar app. Click the EkamCore icon in the
menu bar to open the Manager window at any time.

## Watchdog

The Manager includes a watchdog process that monitors every container.

1. Every 30 seconds the watchdog pings each service's health endpoint.
2. If a service fails three consecutive health checks it is marked
   **Unhealthy** and the watchdog automatically restarts it.
3. If the restart fails, the service is marked **Down** and an alert banner
   appears on the dashboard.
4. The watchdog logs every event to **Diagnostics > Watchdog Log**.

You do not need to configure the watchdog. It runs whenever services are
active and stops when you click **Stop All**.

## System requirements

The Manager itself is lightweight (under 30 MB of RAM). Resource usage
comes from the Docker services it manages. See
[System Requirements](../getting-started/system-requirements.md) for
recommended hardware.

## Next step

Read [Dashboard](dashboard.md) to understand the real-time monitoring
view, or [Updates](updates.md) to learn how updates are applied.

# EkamCore Manager App

> **Status: Placeholder — Full Tauri 2 implementation starts Sprint 3 (S03-005, S03-006).**

The Manager App is a macOS-native desktop application built with [Tauri 2](https://tauri.app/) (Rust backend + React frontend). It is the control plane for the entire EkamCore stack — it owns secrets, starts containers, watches files, and monitors health.

---

## Responsibilities

| Concern | Detail |
|---|---|
| **Secrets management** | Stores all service credentials in the macOS Keychain. Injects them into containers at startup via a transient `.env` file that is deleted after Docker reads it. |
| **Startup orchestration** | Executes a 15-step startup sequence: hardware check → disk → Docker → pull images → PG → migrations → Redis → Qdrant → Ollama → models → API → workers → proxy → ready. |
| **Watchdog** | Polls Docker inspect every 30 s. Auto-restarts unhealthy containers with exponential backoff (5 s → 15 s → 45 s → 135 s → 300 s cap). Escalates to macOS notification after 5 consecutive failures. |
| **File watching** | Uses FSEvents (via the `notify` crate) to detect changes in source folders and push `fs-event` notifications to the API. |
| **EventKit bridge** | Reads Calendar, Reminders, and Contacts via Objective-C/Swift bridge. Pushes data to the API's internal ingestion endpoints. |
| **Thermal monitoring** | Reads IOKit thermal pressure every 10 s and publishes to Redis (`rc:thermal_state`). |
| **Setup wizard** | 8-step first-run wizard: hardware → disk → Docker → pull → migrate → admin account → source permissions → Tailscale. State persisted to `~/Library/Application Support/EkamCore/setup-state.json`. |
| **Diagnostics export** | Collects container stats, system info, watchdog history, ingestion status (no personal data) and writes a ZIP to a user-chosen path. |

---

## Technology Stack

| Layer | Technology |
|---|---|
| App framework | Tauri 2 (Rust + WebView2 / WKWebView) |
| Rust async runtime | tokio |
| Docker Engine API | bollard |
| Keychain access | security-framework |
| File watching | notify (FSEvents on macOS) |
| macOS notifications | notify-rust |
| HTTP client | reqwest |
| Serialisation | serde / serde_json |
| Frontend | React + TypeScript (same design system as `apps/web`) |

---

## Directory Layout (Sprint 3 target)

```
apps/manager/
  src-tauri/
    src/
      main.rs              # Tauri entry point, command registration
      keychain.rs          # store/read/delete secrets via security-framework
      docker.rs            # Container lifecycle via bollard
      startup.rs           # 15-step startup sequence with progress events
      watchdog.rs          # Health polling, restart logic, escalation
      calendar.rs          # EventKit calendar bridge
      reminders.rs         # EventKit reminders bridge
      reminders_write.rs   # Write-through to Apple Reminders
      contacts.rs          # Contacts framework bridge
      fs_watcher.rs        # FSEvents file monitoring
      thermal.rs           # IOKit thermal pressure
      diagnostics.rs       # Diagnostics ZIP export
    Cargo.toml
  src/
    pages/
      SetupWizard.tsx
      Dashboard.tsx
      JobsPage.tsx
      LogsPage.tsx
      Settings.tsx
    components/
      ServiceHealthTile.tsx
      DiskUsageBar.tsx
      IngestionProgress.tsx
      StartupProgress.tsx
  package.json
  tauri.conf.json
```

---

## Window Behaviour

- Default size: 900 × 640 px. Minimum: 700 × 500 px.
- Menu bar icon with right-click menu (Show / Hide / Quit).
- Closing the window **hides** it (watchdog keeps running).
- Cmd+Q confirms before quitting if containers are running.
- Setup wizard tab is visible only on first run; Dashboard is default after completion.

---

## Security Notes

- Secrets never touch disk except during the brief container-start window (see `docs/keychain-design.md`).
- The transient `.env` file is written to a `0700` temporary directory and deleted immediately after `docker compose up` returns.
- The app requests only the Keychain items it owns (access control via `kSecAttrService`).
- EventKit access is requested at runtime with the minimum required permission scope.

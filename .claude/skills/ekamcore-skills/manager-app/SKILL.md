---
name: ekamcore-manager-app
description: Use when writing Tauri 2 / Rust code for the EkamCore manager app — Keychain access, Docker Engine API, FSEvents file watching, setup wizard, startup sequence, watchdog, health dashboard, diagnostics, or any code in the manager/ directory (both src-tauri/ Rust and src/ React).
---

# EkamCore Manager App Skill

**Always read Master SKILL.md first.**

## Project Structure
```
manager/
  src-tauri/
    src/
      main.rs            # Tauri app entry
      keychain.rs         # macOS Keychain read/write/delete via security-framework
      docker.rs           # Docker Engine API via bollard crate
      startup.rs          # 15-step startup sequence
      watchdog.rs         # Health polling + auto-restart + escalation
      calendar.rs         # EventKit calendar bridge (objc2 or swift-bridge)
      reminders.rs        # EventKit reminders bridge
      contacts.rs         # Contacts framework bridge
      reminders_write.rs  # EventKit write (for write-through)
      fs_watcher.rs       # FSEvents via notify crate
      diagnostics.rs      # Generate diagnostics ZIP
      thermal.rs          # IOKit thermal pressure reading
    Cargo.toml
  src/
    pages/               # SetupWizard.tsx, Dashboard.tsx, JobsPage.tsx, LogsPage.tsx, Settings.tsx
    components/          # ServiceHealthTile, DiskUsageBar, IngestionProgress, StartupProgress
  package.json
```

## Key Rust Crates
- **bollard**: Docker Engine API (create/start/stop/inspect/stats containers)
- **security-framework**: macOS Keychain access
- **notify**: Cross-platform file watching (uses FSEvents on macOS)
- **notify-rust**: macOS system notifications
- **reqwest**: HTTP client for API health checks
- **tokio**: Async runtime
- **serde/serde_json**: Serialization

## Keychain Operations
```rust
pub fn store_secret(service: &str, account: &str, secret: &str) -> Result<()>
pub fn read_secret(service: &str, account: &str) -> Result<String>
pub fn delete_secret(service: &str, account: &str) -> Result<()>
```
Services: EkamCore-PostgreSQL, EkamCore-Redis, EkamCore-Qdrant, EkamCore-JWT-Private, EkamCore-JWT-Public, EkamCore-DataEncryption.

## Startup Sequence (15 steps, sequential)
1. Hardware check 2. Disk check 3. Docker check 4. Pull/verify images 5. Create network 6. Start PG (wait pg_isready) 7. Run migrations 8. Start Redis (wait PONG) 9. Start Qdrant (wait /healthz) 10. Start Ollama (wait /api/tags) 11. Check/pull models 12. Start API (wait /health) 13. Start Workers (wait heartbeat) 14. Start Proxy (wait TLS) 15. System ready.
Each step: emit status event to frontend. Timeout per step. Retry up to 3x.

## Watchdog
- Poll Docker inspect every 30 seconds for each container health.
- Unhealthy → restart with backoff: 5s, 15s, 45s, 135s, 300s (cap).
- After 5 consecutive failures → stop auto-restart, macOS notification, red indicator in dashboard.
- Chronic instability: >3 restarts in 1 hour → prompt diagnostics export.

## Setup Wizard (8 steps, state persisted to ~/Library/Application Support/EkamCore/setup-state.json)
1. Hardware check (sysctl, uname, sw_vers) 2. Disk space (statvfs) 3. Docker Desktop status 4. Pull images (progress events) 5. DB init (run migrate container) 6. Admin account (internal API call) 7. Source permissions (Contacts, Calendar, Reminders + folder picker) 8. Tailscale (optional, skippable).

## Thermal Monitoring
Read IOKit thermal pressure every 10 seconds. Publish to Redis key rc:thermal_state. Values: nominal, fair, serious, critical.

## Window Behavior
- Default: 900x640. Min: 700x500. Menu bar icon with right-click menu.
- Close window → hide (watchdog continues). Cmd+Q → confirm if services running.
- Setup wizard tab: visible only during first run. After completion → Dashboard default.

## Diagnostics Export
Collect: container inspect, Docker stats, system info, disk usage, Tailscale status, watchdog history, ingestion status. Exclude: query logs, personal data, file paths, biometric data. Output: ZIP to user-selected location.

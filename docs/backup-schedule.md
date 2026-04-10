# EkamCore Backup Schedule (S08-004)

EkamCore stores three categories of data that require backup:

| Data | Location | Method |
|---|---|---|
| PostgreSQL | `ekamcore` + `paperless` DBs | `pg_dump -Fc` (custom format) |
| Qdrant vectors | `document_embeddings`, `photo_embeddings`, `face_embeddings` | Snapshot API + `docker cp` |
| Paperless documents | Container media + export | `document_exporter` + `docker cp` |
| Config | `.env`, `docker-compose.yml`, `config/` | `cp` |

**Retention policy:** 7 daily backups + 4 weekly backups (Sundays). Managed by `infra/backup/rotate.py`.

---

## Running a Backup Manually

```bash
# From the EkamCore project root
make backup

# Custom backup directory
EKAMCORE_BACKUP_DIR=/Volumes/ExternalDrive/ekamcore-backups make backup

# Dry run (shows what would happen, no actual backup)
bash infra/backup/backup.sh --dry-run
```

---

## Scheduling with launchd (macOS)

The Tauri manager app will configure this automatically in production. For manual setup:

### 1. Create the launchd plist

Save as `~/Library/LaunchAgents/dev.ekamcore.backup.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.ekamcore.backup</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/EkamCore/infra/backup/backup.sh</string>
    </array>

    <!-- Run at 2:00 AM every day -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>WorkingDirectory</key>
    <string>/path/to/EkamCore</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>EKAMCORE_BACKUP_DIR</key>
        <string>/Users/YOUR_USERNAME/ekamcore-backups</string>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/ekamcore-backup.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/ekamcore-backup.error.log</string>

    <!-- Re-run if missed (e.g., Mac was asleep) -->
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Replace `/path/to/EkamCore` and `YOUR_USERNAME` with actual values.

### 2. Load the agent

```bash
launchctl load ~/Library/LaunchAgents/dev.ekamcore.backup.plist
launchctl start dev.ekamcore.backup  # test run immediately
```

### 3. Verify

```bash
launchctl list | grep ekamcore
cat /tmp/ekamcore-backup.log
make backup-list
```

### 4. Unload

```bash
launchctl unload ~/Library/LaunchAgents/dev.ekamcore.backup.plist
```

---

## Restoring from Backup

```bash
# List available backups
make backup-list

# Restore (prompts for confirmation — overwrites current data)
make restore BACKUP_PATH=/backups/2026-04-10_02-00-00
```

The restore script:
1. Stops API, workers, web, proxy, and Paperless
2. Drops and recreates `ekamcore` and `paperless` PostgreSQL databases
3. Restores Qdrant collection snapshots via the recovery API
4. Imports Paperless documents via `document_importer`
5. Runs Alembic migrations (no-op if schema is current)
6. Restarts all services

**Target RTO: < 30 minutes** for a typical backup with < 10 GB of data.

---

## External Drive / NAS

For resilience, point `EKAMCORE_BACKUP_DIR` at an external drive or Time Machine excluded path:

```bash
# In .env or environment
EKAMCORE_BACKUP_DIR=/Volumes/MyBackupDrive/ekamcore-backups
```

The backup script creates `$EKAMCORE_BACKUP_DIR` if it does not exist.

---

## Tauri Manager Integration (Phase 4)

In production, the Tauri manager app (`apps/manager`) will:

1. Read `EKAMCORE_BACKUP_DIR` from the app's preferences store.
2. Register and manage the launchd plist via `launchctl` APIs.
3. Surface backup status and last-run time in the manager UI.
4. Send a macOS notification on backup failure.

The shell scripts and Python rotation logic are intentionally manager-agnostic — they run identically whether invoked by launchd, the manager, or the developer CLI.

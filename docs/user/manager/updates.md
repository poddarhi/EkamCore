# Updates

EkamCore updates are managed entirely through the Manager app. Updates
replace Docker images and apply database migrations while keeping your data
safe.

## Checking for updates

The Manager checks for new releases automatically on launch and once every
24 hours. You can also check manually:

1. Open the Manager.
2. Click **Updates** in the sidebar.
3. Click **Check Now**.

If a new version is available you will see the version number, a short
changelog, and an **Update Now** button. A blue banner also appears on the
dashboard.

## Applying an update

Click **Update Now** to begin. The Manager runs an eight-step process with
a progress bar for each step.

| Step | What happens |
|------|-------------|
| 1. **Pre-flight check** | Verifies disk space, Docker availability, and network connectivity. |
| 2. **Backup** | Creates a full backup of the database and configuration before any changes. |
| 3. **Download images** | Pulls the new Docker images for every updated service. |
| 4. **Stop services** | Gracefully stops all running containers. Active jobs finish first. |
| 5. **Apply migrations** | Runs any database schema migrations included in the release. |
| 6. **Start new containers** | Starts services using the new images. |
| 7. **Health check** | Waits up to 60 seconds for all services to pass health checks. |
| 8. **Cleanup** | Removes old Docker images to reclaim disk space. |

The entire process typically takes two to five minutes depending on download
speed and the number of changed images.

## Automatic rollback on failure

If any step from 4 onward fails, the Manager automatically rolls back:

1. Stops any partially started new containers.
2. Restores the database from the backup created in step 2.
3. Restarts the previous version of all services.
4. Shows an error banner with the failure reason and a link to the
   diagnostics log.

You do not need to intervene. After a rollback, EkamCore is running the
same version it was before the update attempt.

## Manual rollback

If you experience issues after a successful update, you can roll back
manually:

1. Open the Manager and go to **Updates > Backup History**.
2. Select the backup taken immediately before the update.
3. Click **Restore This Backup**.
4. The Manager stops services, restores the database, switches to the
   previous Docker images, and restarts.

Backup history is retained according to your configured retention period
(default: 7 days). See [Settings Reference](../settings/settings-reference.md)
for backup retention options.

## Backup before update

The automatic pre-update backup is stored alongside your regular scheduled
backups in `~/Library/Application Support/EkamCore/backups/`. Pre-update
backups are labeled with the prefix `pre-update-` followed by the target
version number, for example `pre-update-1.1.0-2026-04-16.tar.gz`.

These backups follow the same retention rules as scheduled backups unless
you pin them. To pin a backup, select it in **Backup History** and click
**Pin** -- pinned backups are never automatically deleted.

## Update notifications

You can configure update behavior in **Manager Settings**:

- **Auto-check** (default on) -- Check for updates in the background.
- **Notify only** (default) -- Show a banner but do not install automatically.
- **Auto-install** -- Apply updates automatically when your Mac is idle and
  no jobs are running.

## Next step

For general Manager functionality, see [Manager Overview](overview.md). If
an update leaves a service unhealthy, see
[Hub Unreachable](../troubleshooting/hub-unreachable.md).

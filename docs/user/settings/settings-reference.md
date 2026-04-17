# Settings Reference

EkamCore settings are split across three surfaces: the **Web UI**, the
**Manager** app, and the **Mobile** app. This page documents every setting
in each.

---

## Web UI Settings

Open settings from the gear icon in the top-right corner of the web
interface.

### General

| Setting | Default | Description |
|---------|---------|-------------|
| Date format | `YYYY-MM-DD` | Choose between ISO, US (`MM/DD/YYYY`), or EU (`DD/MM/YYYY`). |
| Time format | 24-hour | Toggle between 12-hour and 24-hour clocks. |
| Week starts on | Monday | Set to Sunday or Monday. Affects calendar views and the Today briefing. |
| Language | English | Display language for the web interface. |

### Sources

| Setting | Description |
|---------|-------------|
| Add folder | Click **Add Folder** and select a directory on your Mac. EkamCore indexes all supported files inside it. |
| Remove folder | Click the trash icon next to any folder to stop indexing. Existing indexed data is retained until you click **Purge Index**. |
| Re-scan now | Triggers an immediate re-scan of all configured folders. |
| Ignore patterns | Glob patterns for files and folders to skip (for example `node_modules`, `.git`). |

### Photo Intelligence

| Setting | Default | Description |
|---------|---------|-------------|
| Face clustering | Off | Enable to let EkamCore detect and group faces in your photos. Requires explicit consent toggle. |
| Consent acknowledgement | -- | You must check "I understand face data is stored locally" before clustering activates. |
| Minimum cluster size | 3 | Faces must appear in at least this many photos before a cluster is created. |
| Re-cluster now | -- | Discards current clusters and re-runs face detection on all indexed photos. |

### PLA Pack

| Setting | Default | Description |
|---------|---------|-------------|
| Enable PLA | Off | Master switch for the Personal Life Assistant suggestion engine. |
| Workflow toggles | All on | Enable or disable individual workflows: Morning Briefing, Evening Recap, Contact Follow-up, Photo Memories, Document Digest. |
| Schedule | 07:00 / 21:00 | Set the times for Morning Briefing and Evening Recap delivery. |

---

## Manager Settings

Open the Manager app and click the gear icon in the toolbar.

| Setting | Default | Description |
|---------|---------|-------------|
| Auto-start on login | On | Launch the Manager and start all services when you log in to macOS. |
| Backup schedule | Daily at 02:00 | Frequency and time for automatic backups. Options: hourly, daily, weekly, manual only. |
| Backup retention | 7 days | Number of days to keep old backups before automatic deletion. |
| Secrets | -- | View and rotate the internal API key and database credentials. Values are stored in the macOS Keychain. |
| Reset EkamCore | -- | Stops all services, deletes Docker volumes, and removes all indexed data. This action is irreversible. |
| Log level | Info | Set to Debug for more verbose logs when troubleshooting. |

---

## Mobile Settings

Open the **Settings** tab in the EkamCore mobile app.

| Setting | Default | Description |
|---------|---------|-------------|
| Hub URL | -- | The Tailscale IP or MagicDNS name of your Mac (for example `https://100.64.1.10:443`). |
| Test connection | -- | Button that verifies the app can reach the hub. |
| Cache size | 500 MB | Maximum on-device cache. Range: 50 MB to 2 GB. |
| Biometric unlock | Off | Use Face ID or Touch ID instead of password on app launch. |
| Appearance | System | Light, Dark, or follow system setting. |
| Log out | -- | Clears session, cache, and biometric data. See [Offline Behavior](../mobile/offline-behavior.md) for details. |

---

## Resetting a single setting

Most settings can be returned to their default by clicking the reset arrow
next to the field. To reset all settings in a section, click **Restore
Defaults** at the bottom of that section.

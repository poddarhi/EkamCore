//! S15-005 — macOS launchd integration.
//!
//! Login Item registration (auto-start on login) and backup scheduling
//! via LaunchAgents plists in ~/Library/LaunchAgents/.
//!
//! - com.ekamcore.manager.plist — Login Item (RunAtLoad)
//! - com.ekamcore.backup.plist  — Daily backup at configurable hour

use serde::Serialize;
use std::path::PathBuf;
use std::process::Command;

// ── Types ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct LaunchdStatus {
    pub login_item_registered: bool,
    pub backup_scheduled: bool,
    pub backup_hour: u8,
    pub backup_minute: u8,
}

const MANAGER_LABEL: &str = "com.ekamcore.manager";
const BACKUP_LABEL: &str = "com.ekamcore.backup";

// ── Login Item ──────────────────────────────────────────────────────────────

/// Register EkamCore Manager as a macOS Login Item via LaunchAgents plist.
#[tauri::command]
pub fn register_login_item() -> Result<(), String> {
    let plist_path = launch_agents_dir()?.join(format!("{MANAGER_LABEL}.plist"));
    let app_path = resolve_app_path();

    let plist = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MANAGER_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{app_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>"#
    );

    std::fs::write(&plist_path, plist)
        .map_err(|e| format!("Failed to write plist: {e}"))?;

    launchctl_load(&plist_path)?;
    tracing::info!("login_item_registered");
    Ok(())
}

/// Unregister EkamCore Manager from Login Items.
#[tauri::command]
pub fn unregister_login_item() -> Result<(), String> {
    let plist_path = launch_agents_dir()?.join(format!("{MANAGER_LABEL}.plist"));

    if plist_path.exists() {
        let _ = launchctl_unload(&plist_path);
        std::fs::remove_file(&plist_path)
            .map_err(|e| format!("Failed to remove plist: {e}"))?;
    }

    tracing::info!("login_item_unregistered");
    Ok(())
}

/// Check if login item is currently registered.
#[tauri::command]
pub fn is_login_item_registered() -> bool {
    let plist_path = launch_agents_dir()
        .map(|d| d.join(format!("{MANAGER_LABEL}.plist")))
        .unwrap_or_default();
    plist_path.exists()
}

// ── Backup Schedule ─────────────────────────────────────────────────────────

/// Install the daily backup schedule via launchd.
#[tauri::command]
pub fn install_backup_schedule(hour: u8, minute: u8) -> Result<(), String> {
    let plist_path = launch_agents_dir()?.join(format!("{BACKUP_LABEL}.plist"));
    let backup_script = resolve_backup_script();
    let log_dir = ensure_log_dir()?;

    let plist = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{BACKUP_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{backup_script}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/backup.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/backup-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>"#,
        log_dir = log_dir.display()
    );

    // Unload existing if present
    if plist_path.exists() {
        let _ = launchctl_unload(&plist_path);
    }

    std::fs::write(&plist_path, plist)
        .map_err(|e| format!("Failed to write backup plist: {e}"))?;

    launchctl_load(&plist_path)?;
    tracing::info!("backup_schedule_installed: hour={hour} minute={minute}");
    Ok(())
}

/// Uninstall the backup schedule.
#[tauri::command]
pub fn uninstall_backup_schedule() -> Result<(), String> {
    let plist_path = launch_agents_dir()?.join(format!("{BACKUP_LABEL}.plist"));

    if plist_path.exists() {
        let _ = launchctl_unload(&plist_path);
        std::fs::remove_file(&plist_path)
            .map_err(|e| format!("Failed to remove backup plist: {e}"))?;
    }

    tracing::info!("backup_schedule_uninstalled");
    Ok(())
}

/// Get status of both launchd jobs.
#[tauri::command]
pub fn get_launchd_status() -> LaunchdStatus {
    let agents_dir = launch_agents_dir().unwrap_or_default();

    let login_registered = agents_dir.join(format!("{MANAGER_LABEL}.plist")).exists();
    let backup_plist = agents_dir.join(format!("{BACKUP_LABEL}.plist"));
    let backup_scheduled = backup_plist.exists();

    // Parse hour/minute from backup plist if present
    let (hour, minute) = if backup_scheduled {
        parse_backup_time(&backup_plist).unwrap_or((2, 0))
    } else {
        (2, 0) // default
    };

    LaunchdStatus {
        login_item_registered: login_registered,
        backup_scheduled,
        backup_hour: hour,
        backup_minute: minute,
    }
}

/// Run a backup immediately (one-shot, not via launchd).
#[tauri::command]
pub async fn run_backup_now() -> Result<String, String> {
    let script = resolve_backup_script();

    let output = Command::new("/bin/bash")
        .arg(&script)
        .env("PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin")
        .output()
        .map_err(|e| format!("Failed to run backup: {e}"))?;

    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        tracing::info!("backup_completed");
        Ok(stdout)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        Err(format!("Backup failed: {stderr}"))
    }
}

// ── Helpers ─────────────────────────────────────────────────────────────────

fn launch_agents_dir() -> Result<PathBuf, String> {
    let home = std::env::var("HOME")
        .map_err(|_| "HOME not set".to_string())?;
    let dir = PathBuf::from(&home).join("Library/LaunchAgents");
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("Failed to create LaunchAgents dir: {e}"))?;
    Ok(dir)
}

fn ensure_log_dir() -> Result<PathBuf, String> {
    let home = std::env::var("HOME")
        .map_err(|_| "HOME not set".to_string())?;
    let dir = PathBuf::from(&home).join("Library/Logs/EkamCore");
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("Failed to create log dir: {e}"))?;
    Ok(dir)
}

fn resolve_app_path() -> String {
    // In dev: use the current executable. In prod: use the .app bundle path.
    std::env::current_exe()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| {
            "/Applications/EkamCore Manager.app/Contents/MacOS/EkamCore Manager".to_string()
        })
}

fn resolve_backup_script() -> String {
    // Try env var first, then relative from CARGO_MANIFEST_DIR, then fallback
    if let Ok(dir) = std::env::var("EKAMCORE_COMPOSE_DIR") {
        let candidate = PathBuf::from(&dir).join("infrastructure/backup/backup.sh");
        if candidate.exists() {
            return candidate.to_string_lossy().to_string();
        }
    }

    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let candidate = manifest.join("../../../infrastructure/backup/backup.sh");
    if candidate.exists() {
        return candidate
            .canonicalize()
            .unwrap_or(candidate)
            .to_string_lossy()
            .to_string();
    }

    // Fallback for production install
    "/usr/local/share/ekamcore/infrastructure/backup/backup.sh".to_string()
}

fn launchctl_load(plist: &PathBuf) -> Result<(), String> {
    let output = Command::new("launchctl")
        .args(["load", "-w"])
        .arg(plist)
        .output()
        .map_err(|e| format!("launchctl load failed: {e}"))?;

    if output.status.success() {
        Ok(())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        // "already loaded" is not a real error
        if stderr.contains("already loaded") || stderr.contains("service already loaded") {
            Ok(())
        } else {
            Err(format!("launchctl load failed: {stderr}"))
        }
    }
}

fn launchctl_unload(plist: &PathBuf) -> Result<(), String> {
    let output = Command::new("launchctl")
        .args(["unload", "-w"])
        .arg(plist)
        .output()
        .map_err(|e| format!("launchctl unload failed: {e}"))?;

    if output.status.success() {
        Ok(())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("launchctl unload failed: {stderr}"))
    }
}

/// Parse Hour and Minute from a backup plist file.
fn parse_backup_time(plist_path: &PathBuf) -> Option<(u8, u8)> {
    let content = std::fs::read_to_string(plist_path).ok()?;
    // Simple XML parsing — find <key>Hour</key><integer>N</integer>
    let hour = extract_plist_integer(&content, "Hour")?;
    let minute = extract_plist_integer(&content, "Minute").unwrap_or(0);
    Some((hour, minute))
}

fn extract_plist_integer(content: &str, key: &str) -> Option<u8> {
    let key_tag = format!("<key>{key}</key>");
    let pos = content.find(&key_tag)?;
    let after = &content[pos + key_tag.len()..];
    let int_start = after.find("<integer>")? + 9;
    let int_end = after[int_start..].find("</integer>")?;
    after[int_start..int_start + int_end].trim().parse().ok()
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manager_label_correct() {
        assert_eq!(MANAGER_LABEL, "com.ekamcore.manager");
    }

    #[test]
    fn backup_label_correct() {
        assert_eq!(BACKUP_LABEL, "com.ekamcore.backup");
    }

    #[test]
    fn extract_plist_integer_parses_hour() {
        let plist = r#"<key>Hour</key>
        <integer>14</integer>
        <key>Minute</key>
        <integer>30</integer>"#;
        assert_eq!(extract_plist_integer(plist, "Hour"), Some(14));
        assert_eq!(extract_plist_integer(plist, "Minute"), Some(30));
    }

    #[test]
    fn extract_plist_integer_missing_key() {
        let plist = "<key>Other</key><integer>5</integer>";
        assert_eq!(extract_plist_integer(plist, "Hour"), None);
    }

    #[test]
    fn launch_agents_dir_valid() {
        // Should not fail on macOS
        let dir = launch_agents_dir();
        assert!(dir.is_ok());
        assert!(dir.unwrap().to_string_lossy().contains("LaunchAgents"));
    }

    #[test]
    fn launchd_status_serializable() {
        let status = LaunchdStatus {
            login_item_registered: true,
            backup_scheduled: true,
            backup_hour: 2,
            backup_minute: 0,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"login_item_registered\":true"));
        assert!(json.contains("\"backup_hour\":2"));
    }

    #[test]
    fn resolve_app_path_not_empty() {
        let path = resolve_app_path();
        assert!(!path.is_empty());
    }
}

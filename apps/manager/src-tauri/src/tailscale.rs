//! Step 8 — Tailscale Check (optional)
//!
//! Checks whether Tailscale is installed and connected.
//! This step is skippable — Tailscale enables remote access but is not required.

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct TailscaleCheckResult {
    pub installed: bool,
    pub connected: bool,
    pub hostname: Option<String>,
    pub ip: Option<String>,
}

/// Check Tailscale installation and connectivity.
#[tauri::command]
pub fn check_tailscale() -> TailscaleCheckResult {
    let output = std::process::Command::new("tailscale")
        .args(["status", "--json"])
        .output();

    match output {
        Err(_) => TailscaleCheckResult {
            installed: false,
            connected: false,
            hostname: None,
            ip: None,
        },
        Ok(out) => {
            if !out.status.success() {
                // Installed but daemon not running / not logged in
                return TailscaleCheckResult {
                    installed: true,
                    connected: false,
                    hostname: None,
                    ip: None,
                };
            }
            let json: serde_json::Value =
                serde_json::from_slice(&out.stdout).unwrap_or(serde_json::Value::Null);
            let connected = json["BackendState"].as_str() == Some("Running");
            let hostname = json["Self"]["HostName"].as_str().map(str::to_string);
            let ip = json["Self"]["TailscaleIPs"]
                .as_array()
                .and_then(|arr| arr.first())
                .and_then(|v| v.as_str())
                .map(str::to_string);
            TailscaleCheckResult {
                installed: true,
                connected,
                hostname,
                ip,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_tailscale_does_not_panic() {
        // Tailscale may or may not be installed in CI; just verify it doesn't panic.
        let _r = check_tailscale();
    }
}

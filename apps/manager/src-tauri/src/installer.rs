//! Self-contained installer — runs the bundled install.sh and streams progress.
//!
//! The install.sh script handles: Docker install, Ollama install, repo clone,
//! image pull/build, stack start, model download, verification.

use std::io::BufRead;
use std::process::{Command, Stdio};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Debug, Clone, Serialize)]
pub struct InstallerProgress {
    pub phase: String,
    pub status: String,
    pub message: String,
}

/// Run the full installer or a specific phase.
/// Streams JSON progress lines via the "installer-progress" Tauri event.
#[tauri::command]
pub async fn run_installer(app: AppHandle, phase: String) -> Result<String, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Cannot find resource dir: {e}"))?;

    let script = resource_dir.join("resources/install.sh");
    if !script.exists() {
        return Err(format!("Installer script not found at: {}", script.display()));
    }

    tracing::info!("running_installer: phase={phase} script={}", script.display());

    let mut child = Command::new("/bin/bash")
        .arg(&script)
        .arg(&phase)
        .env("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        .env("HOME", std::env::var("HOME").unwrap_or_default())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to run installer: {e}"))?;

    let stdout = child.stdout.take().ok_or("No stdout")?;
    let reader = std::io::BufReader::new(stdout);

    let mut last_message = String::new();

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => continue,
        };

        // Try to parse JSON progress
        if line.starts_with('{') {
            if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&line) {
                let progress = InstallerProgress {
                    phase: parsed["phase"].as_str().unwrap_or("unknown").to_string(),
                    status: parsed["status"].as_str().unwrap_or("running").to_string(),
                    message: parsed["message"].as_str().unwrap_or("").to_string(),
                };
                last_message = progress.message.clone();
                let _ = app.emit("installer-progress", &progress);
            }
        }
    }

    let status = child.wait().map_err(|e| format!("Installer wait failed: {e}"))?;

    if status.success() {
        Ok(last_message)
    } else {
        Err(format!("Installer failed (exit {}): {last_message}", status.code().unwrap_or(-1)))
    }
}

/// Check what dependencies are already installed.
#[tauri::command]
pub fn check_system_deps() -> serde_json::Value {
    let docker = Command::new("docker")
        .args(["info"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    let ollama = Command::new("which")
        .arg("ollama")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    let ollama_running = Command::new("curl")
        .args(["-sf", "--max-time", "2", "http://localhost:11434/api/tags"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    let repo_exists = std::path::Path::new(&format!(
        "{}/EkamCore/docker-compose.yml",
        std::env::var("HOME").unwrap_or_default()
    ))
    .exists();

    let api_healthy = Command::new("curl")
        .args(["-sf", "--max-time", "3", "http://localhost:8420/health"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    let brew = Command::new("which")
        .arg("brew")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    serde_json::json!({
        "docker_running": docker,
        "ollama_installed": ollama,
        "ollama_running": ollama_running,
        "repo_exists": repo_exists,
        "api_healthy": api_healthy,
        "homebrew_available": brew,
    })
}

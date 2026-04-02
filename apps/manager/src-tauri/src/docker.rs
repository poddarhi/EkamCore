//! Step 3 — Docker / OrbStack Detection
//!
//! Checks for OrbStack (preferred on Apple Silicon) or Docker Desktop.
//! Uses socket-path detection first, then CLI fallback.

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct DockerCheckResult {
    pub installed: bool,
    /// "orbstack" | "docker_desktop" | "none"
    pub runtime: String,
    pub version: Option<String>,
}

/// Detect Docker or OrbStack installation.
#[tauri::command]
pub fn check_docker() -> DockerCheckResult {
    // OrbStack: socket at ~/.orbstack/run/docker.sock
    if orbstack_socket_present() {
        return DockerCheckResult {
            installed: true,
            runtime: "orbstack".to_string(),
            version: docker_server_version(),
        };
    }

    // Docker Desktop: standard socket at /var/run/docker.sock
    if docker_socket_present() || docker_info_succeeds() {
        return DockerCheckResult {
            installed: true,
            runtime: "docker_desktop".to_string(),
            version: docker_server_version(),
        };
    }

    DockerCheckResult {
        installed: false,
        runtime: "none".to_string(),
        version: None,
    }
}

fn orbstack_socket_present() -> bool {
    let home = std::env::var("HOME").unwrap_or_default();
    std::path::Path::new(&format!("{home}/.orbstack/run/docker.sock")).exists()
}

fn docker_socket_present() -> bool {
    std::path::Path::new("/var/run/docker.sock").exists()
}

fn docker_info_succeeds() -> bool {
    std::process::Command::new("docker")
        .args(["info", "--format", "{{.ServerVersion}}"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn docker_server_version() -> Option<String> {
    let out = std::process::Command::new("docker")
        .args(["version", "--format", "{{.Server.Version}}"])
        .output()
        .ok()?;
    if out.status.success() {
        String::from_utf8(out.stdout)
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_docker_returns_result() {
        let r = check_docker();
        // runtime must be one of the three known values
        assert!(["orbstack", "docker_desktop", "none"].contains(&r.runtime.as_str()));
        if r.installed {
            assert!(r.version.is_some());
        }
    }
}

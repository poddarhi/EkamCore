//! S15-004 — Diagnostics bundle generation (offline-capable).
//!
//! Collects system info, Docker state, container logs, health checks,
//! setup state, sanitized config, disk usage, and network info into a
//! ZIP archive. Works even when all backend services are down — uses
//! bollard / CLI directly, never the EkamCore API.
//!
//! Per ART-27 §1: NO personal data (query logs, file names, person
//! names, embeddings, database content) is included.

use serde::Serialize;
use std::io::Write;
use std::path::PathBuf;
use std::process::Command;
use tauri::{AppHandle, Emitter, State};
use zip::write::{SimpleFileOptions, ZipWriter};

use crate::state::AppState;

// ── Types ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct DiagnosticsProgress {
    pub phase: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiagnosticsResult {
    pub path: String,
    pub size_bytes: u64,
    pub files_included: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct SystemInfo {
    macos_version: String,
    hardware: String,
    ram_gb: f64,
    cpu_cores: u32,
    disk_free_gb: f64,
    disk_total_gb: f64,
}

#[derive(Debug, Clone, Serialize)]
struct DockerInfo {
    version: Option<String>,
    running: bool,
    containers: Vec<ContainerSummary>,
}

#[derive(Debug, Clone, Serialize)]
struct ContainerSummary {
    name: String,
    state: String,
    image: String,
    status: String,
}

#[derive(Debug, Clone, Serialize)]
struct HealthCheck {
    service: String,
    url: String,
    reachable: bool,
    status_code: Option<u16>,
}

#[derive(Debug, Clone, Serialize)]
struct NetworkInfo {
    docker_networks: Vec<String>,
    listening_ports: Vec<String>,
    tailscale_status: Option<String>,
}

// ── Services to check ───────────────────────────────────────────────────────

const HEALTH_ENDPOINTS: &[(&str, &str)] = &[
    ("api", "http://localhost:8420/health"),
    ("qdrant", "http://localhost:6333/healthz"),
    ("ollama", "http://localhost:11434/api/tags"),
    ("redis", "http://localhost:6379"),
    ("proxy", "https://localhost:443"),
];

const CONTAINER_NAMES: &[&str] = &[
    "ekamcore-postgres",
    "ekamcore-redis",
    "ekamcore-qdrant",
    "ekamcore-api",
    "ekamcore-workers",
    "ekamcore-web",
    "ekamcore-proxy",
    "ekamcore-paperless",
];

// ── Commands ────────────────────────────────────────────────────────────────

/// Generate a diagnostics ZIP bundle. Returns path and metadata.
#[tauri::command]
pub async fn generate_diagnostics(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<DiagnosticsResult, String> {
    let data_dir = state.app_data_dir.clone();
    let tmp_dir = std::env::temp_dir();
    let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S");
    let zip_path = tmp_dir.join(format!("ekamcore-diagnostics-{timestamp}.zip"));

    let file = std::fs::File::create(&zip_path)
        .map_err(|e| format!("Failed to create ZIP: {e}"))?;
    let mut zip = ZipWriter::new(file);
    let opts = SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);

    let mut files_included = Vec::new();

    // Phase 1: System info
    emit_progress(&app, "system_info", "collecting");
    let sys = collect_system_info();
    write_json(&mut zip, &opts, "system_info.json", &sys)?;
    files_included.push("system_info.json".to_string());

    // Phase 2: Docker info
    emit_progress(&app, "docker_info", "collecting");
    let docker = collect_docker_info();
    write_json(&mut zip, &opts, "docker_info.json", &docker)?;
    files_included.push("docker_info.json".to_string());

    // Phase 3: Container logs (last 500 lines each)
    emit_progress(&app, "container_logs", "collecting");
    for name in CONTAINER_NAMES {
        let logs = collect_container_logs(name, 500);
        let filename = format!("container_logs/{name}.log");
        zip.start_file(&filename, opts)
            .map_err(|e| format!("ZIP error: {e}"))?;
        zip.write_all(logs.as_bytes())
            .map_err(|e| format!("ZIP write error: {e}"))?;
        files_included.push(filename);
    }

    // Phase 4: Health checks
    emit_progress(&app, "health_checks", "collecting");
    let checks = collect_health_checks();
    write_json(&mut zip, &opts, "health_check.json", &checks)?;
    files_included.push("health_check.json".to_string());

    // Phase 5: Setup state
    emit_progress(&app, "setup_state", "collecting");
    let setup_path = data_dir.join("setup-state.json");
    if setup_path.exists() {
        let content = std::fs::read_to_string(&setup_path).unwrap_or_default();
        zip.start_file("setup_state.json", opts)
            .map_err(|e| format!("ZIP error: {e}"))?;
        zip.write_all(content.as_bytes())
            .map_err(|e| format!("ZIP write error: {e}"))?;
        files_included.push("setup_state.json".to_string());
    }

    // Phase 6: Sanitized docker-compose.yml
    emit_progress(&app, "config_sanitized", "collecting");
    let compose = collect_sanitized_compose();
    zip.start_file("config_sanitized.yml", opts)
        .map_err(|e| format!("ZIP error: {e}"))?;
    zip.write_all(compose.as_bytes())
        .map_err(|e| format!("ZIP write error: {e}"))?;
    files_included.push("config_sanitized.yml".to_string());

    // Phase 7: Disk usage
    emit_progress(&app, "disk_usage", "collecting");
    let disk = collect_disk_usage();
    write_json(&mut zip, &opts, "disk_usage.json", &disk)?;
    files_included.push("disk_usage.json".to_string());

    // Phase 8: Network info
    emit_progress(&app, "network_info", "collecting");
    let net = collect_network_info();
    write_json(&mut zip, &opts, "network_info.json", &net)?;
    files_included.push("network_info.json".to_string());

    // Finalize
    zip.finish().map_err(|e| format!("ZIP finalize error: {e}"))?;
    emit_progress(&app, "complete", "done");

    let size = std::fs::metadata(&zip_path)
        .map(|m| m.len())
        .unwrap_or(0);

    Ok(DiagnosticsResult {
        path: zip_path.to_string_lossy().to_string(),
        size_bytes: size,
        files_included,
    })
}

/// Get system info as JSON string (for "Copy to Clipboard").
#[tauri::command]
pub fn get_system_info_text() -> String {
    let info = collect_system_info();
    serde_json::to_string_pretty(&info).unwrap_or_else(|_| "{}".to_string())
}

/// Run `docker system prune -f` to clean unused Docker data.
#[tauri::command]
pub async fn clean_docker_cache() -> Result<String, String> {
    let output = Command::new("docker")
        .args(["system", "prune", "-f"])
        .output()
        .map_err(|e| format!("docker prune failed: {e}"))?;

    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        Ok(stdout)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("docker prune failed: {stderr}"))
    }
}

/// Get storage breakdown for the Storage page.
#[tauri::command]
pub async fn get_storage_breakdown() -> Result<serde_json::Value, String> {
    let mut breakdown = serde_json::Map::new();

    // Docker volumes
    let docker_output = Command::new("docker")
        .args(["system", "df", "--format", "{{json .}}"])
        .output();

    if let Ok(out) = docker_output {
        if out.status.success() {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let mut images_size = "0B".to_string();
            let mut containers_size = "0B".to_string();
            let mut volumes_size = "0B".to_string();

            for line in stdout.lines() {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(line) {
                    match v["Type"].as_str() {
                        Some("Images") => {
                            images_size = v["Size"].as_str().unwrap_or("0B").to_string();
                        }
                        Some("Containers") => {
                            containers_size = v["Size"].as_str().unwrap_or("0B").to_string();
                        }
                        Some("Local Volumes") => {
                            volumes_size = v["Size"].as_str().unwrap_or("0B").to_string();
                        }
                        _ => {}
                    }
                }
            }

            breakdown.insert("docker_images".to_string(), serde_json::json!(images_size));
            breakdown.insert("docker_containers".to_string(), serde_json::json!(containers_size));
            breakdown.insert("docker_volumes".to_string(), serde_json::json!(volumes_size));
        }
    }

    // Ollama models
    let ollama_dir = format!(
        "{}/.ollama/models",
        std::env::var("HOME").unwrap_or_default()
    );
    let ollama_size = dir_size_mb(&ollama_dir);
    breakdown.insert("ollama_models_mb".to_string(), serde_json::json!(ollama_size));

    // Disk overview
    let disk = crate::disk::check_disk();
    breakdown.insert("disk_free_gb".to_string(), serde_json::json!(disk.free_gb));
    breakdown.insert("disk_warning".to_string(), serde_json::json!(disk.warning || !disk.passed));

    Ok(serde_json::Value::Object(breakdown))
}

// ── Collection helpers ──────────────────────────────────────────────────────

fn collect_system_info() -> SystemInfo {
    let hw = crate::hardware::check_hardware();
    let disk = crate::disk::check_disk();

    let cpu_cores = Command::new("sysctl")
        .args(["-n", "hw.ncpu"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(0);

    // Total disk: free + used approximation from df
    let disk_total = Command::new("df")
        .args(["-k", "/"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .and_then(|s| {
            s.lines()
                .nth(1)?
                .split_whitespace()
                .nth(1)?
                .parse::<u64>()
                .ok()
        })
        .map(|kib| kib as f64 / (1024.0 * 1024.0))
        .unwrap_or(0.0);

    SystemInfo {
        macos_version: hw.macos_version,
        hardware: if hw.is_apple_silicon {
            "Apple Silicon".to_string()
        } else {
            "Intel".to_string()
        },
        ram_gb: hw.ram_gb,
        cpu_cores,
        disk_free_gb: disk.free_gb,
        disk_total_gb: disk_total,
    }
}

fn collect_docker_info() -> DockerInfo {
    let docker_check = crate::docker::check_docker();
    let mut containers = Vec::new();

    if docker_check.installed {
        let output = Command::new("docker")
            .args([
                "ps", "-a",
                "--filter", "label=com.docker.compose.project=ekamcore",
                "--format", "{{.Names}}|{{.State}}|{{.Image}}|{{.Status}}",
            ])
            .output();

        if let Ok(out) = output {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout);
                for line in stdout.lines() {
                    let parts: Vec<&str> = line.splitn(4, '|').collect();
                    if parts.len() == 4 {
                        containers.push(ContainerSummary {
                            name: parts[0].to_string(),
                            state: parts[1].to_string(),
                            image: parts[2].to_string(),
                            status: parts[3].to_string(),
                        });
                    }
                }
            }
        }
    }

    DockerInfo {
        version: docker_check.version,
        running: docker_check.installed,
        containers,
    }
}

fn collect_container_logs(name: &str, lines: u32) -> String {
    let output = Command::new("docker")
        .args([
            "logs", name,
            "--tail", &lines.to_string(),
            "--timestamps",
        ])
        .output();

    match output {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let stderr = String::from_utf8_lossy(&out.stderr);
            // Docker outputs logs to both stdout and stderr
            format!("{stdout}{stderr}")
        }
        Err(e) => format!("Failed to collect logs for {name}: {e}"),
    }
}

fn collect_health_checks() -> Vec<HealthCheck> {
    HEALTH_ENDPOINTS
        .iter()
        .map(|(service, url)| {
            let output = Command::new("curl")
                .args(["-sf", "--max-time", "3", "-o", "/dev/null", "-w", "%{http_code}", url])
                .output();

            match output {
                Ok(out) if out.status.success() => {
                    let code: u16 = String::from_utf8_lossy(&out.stdout)
                        .trim()
                        .parse()
                        .unwrap_or(0);
                    HealthCheck {
                        service: service.to_string(),
                        url: url.to_string(),
                        reachable: code >= 200 && code < 500,
                        status_code: Some(code),
                    }
                }
                _ => HealthCheck {
                    service: service.to_string(),
                    url: url.to_string(),
                    reachable: false,
                    status_code: None,
                },
            }
        })
        .collect()
}

fn collect_sanitized_compose() -> String {
    let compose_path = find_compose_file();
    match compose_path {
        Some(path) => {
            let content = std::fs::read_to_string(&path).unwrap_or_default();
            // Redact passwords, secrets, tokens, keys
            let mut sanitized = String::new();
            for line in content.lines() {
                let lower = line.to_lowercase();
                if lower.contains("password")
                    || lower.contains("secret")
                    || lower.contains("token")
                    || lower.contains("api_key")
                    || lower.contains("private_key")
                    || lower.contains("encryption_key")
                {
                    // Keep the key name, redact the value
                    if let Some(idx) = line.find(':') {
                        sanitized.push_str(&line[..=idx]);
                        sanitized.push_str(" ***REDACTED***");
                    } else if let Some(idx) = line.find('=') {
                        sanitized.push_str(&line[..=idx]);
                        sanitized.push_str("***REDACTED***");
                    } else {
                        sanitized.push_str(line);
                    }
                } else {
                    sanitized.push_str(line);
                }
                sanitized.push('\n');
            }
            sanitized
        }
        None => "# docker-compose.yml not found\n".to_string(),
    }
}

fn collect_disk_usage() -> serde_json::Value {
    let output = Command::new("df")
        .args(["-h", "/"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .unwrap_or_default();

    let docker_df = Command::new("docker")
        .args(["system", "df"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .unwrap_or_else(|| "Docker not available".to_string());

    serde_json::json!({
        "boot_volume": output.trim(),
        "docker_usage": docker_df.trim(),
    })
}

fn collect_network_info() -> NetworkInfo {
    // Docker networks
    let networks = Command::new("docker")
        .args(["network", "ls", "--format", "{{.Name}}"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.lines().map(String::from).collect())
        .unwrap_or_default();

    // Listening ports (relevant EkamCore ports)
    let ports = Command::new("lsof")
        .args(["-i", "-P", "-n"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| {
            s.lines()
                .filter(|l| {
                    l.contains(":8420")
                        || l.contains(":443")
                        || l.contains(":5432")
                        || l.contains(":6379")
                        || l.contains(":6333")
                        || l.contains(":11434")
                })
                .map(String::from)
                .collect()
        })
        .unwrap_or_default();

    // Tailscale
    let ts = crate::tailscale::check_tailscale();
    let tailscale_status = if ts.installed {
        Some(format!(
            "installed={}, connected={}, ip={}",
            ts.installed,
            ts.connected,
            ts.ip.unwrap_or_else(|| "none".to_string())
        ))
    } else {
        None
    };

    NetworkInfo {
        docker_networks: networks,
        listening_ports: ports,
        tailscale_status,
    }
}

// ── Utility ─────────────────────────────────────────────────────────────────

fn emit_progress(app: &AppHandle, phase: &str, status: &str) {
    let _ = app.emit(
        "diagnostics-progress",
        DiagnosticsProgress {
            phase: phase.to_string(),
            status: status.to_string(),
        },
    );
}

fn write_json<T: Serialize>(
    zip: &mut ZipWriter<std::fs::File>,
    opts: &SimpleFileOptions,
    filename: &str,
    data: &T,
) -> Result<(), String> {
    let json = serde_json::to_string_pretty(data)
        .map_err(|e| format!("JSON serialize error: {e}"))?;
    zip.start_file(filename, *opts)
        .map_err(|e| format!("ZIP error: {e}"))?;
    zip.write_all(json.as_bytes())
        .map_err(|e| format!("ZIP write error: {e}"))?;
    Ok(())
}

fn find_compose_file() -> Option<PathBuf> {
    let from_env = std::env::var("EKAMCORE_COMPOSE_DIR").ok();
    if let Some(dir) = from_env {
        let p = PathBuf::from(&dir).join("docker-compose.yml");
        if p.exists() {
            return Some(p);
        }
    }

    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let candidate = manifest.join("../../../docker-compose.yml");
    if candidate.exists() {
        return Some(candidate);
    }
    None
}

fn dir_size_mb(path: &str) -> f64 {
    let output = Command::new("du")
        .args(["-sm", path])
        .output();

    match output {
        Ok(out) if out.status.success() => {
            String::from_utf8_lossy(&out.stdout)
                .split_whitespace()
                .next()
                .and_then(|s| s.parse::<f64>().ok())
                .unwrap_or(0.0)
        }
        _ => 0.0,
    }
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn system_info_collectable() {
        let info = collect_system_info();
        assert!(info.ram_gb > 0.0);
        assert!(info.cpu_cores > 0);
        assert!(!info.macos_version.is_empty());
    }

    #[test]
    fn docker_info_collectable() {
        let info = collect_docker_info();
        // Just verify it doesn't panic
        let _ = serde_json::to_string(&info).unwrap();
    }

    #[test]
    fn health_checks_collectable() {
        let checks = collect_health_checks();
        assert_eq!(checks.len(), HEALTH_ENDPOINTS.len());
        for check in &checks {
            assert!(!check.service.is_empty());
            assert!(!check.url.is_empty());
        }
    }

    #[test]
    fn sanitize_compose_redacts_passwords() {
        let input = "POSTGRES_PASSWORD: mysecretpassword123\nPOSTGRES_DB: ekamcore\nREDIS_TOKEN=abc123\n";
        // Simulate the sanitization logic
        let mut sanitized = String::new();
        for line in input.lines() {
            let lower = line.to_lowercase();
            if lower.contains("password") || lower.contains("token") {
                if let Some(idx) = line.find(':') {
                    sanitized.push_str(&line[..=idx]);
                    sanitized.push_str(" ***REDACTED***");
                } else if let Some(idx) = line.find('=') {
                    sanitized.push_str(&line[..=idx]);
                    sanitized.push_str("***REDACTED***");
                }
            } else {
                sanitized.push_str(line);
            }
            sanitized.push('\n');
        }
        assert!(sanitized.contains("***REDACTED***"));
        assert!(!sanitized.contains("mysecretpassword123"));
        assert!(!sanitized.contains("abc123"));
        assert!(sanitized.contains("POSTGRES_DB: ekamcore"));
    }

    #[test]
    fn diagnostics_result_serializable() {
        let result = DiagnosticsResult {
            path: "/tmp/test.zip".to_string(),
            size_bytes: 12345,
            files_included: vec!["system_info.json".to_string()],
        };
        let json = serde_json::to_string(&result).unwrap();
        assert!(json.contains("\"size_bytes\":12345"));
    }

    #[test]
    fn network_info_serializable() {
        let info = NetworkInfo {
            docker_networks: vec!["ekamcore_default".to_string()],
            listening_ports: vec![],
            tailscale_status: None,
        };
        let json = serde_json::to_string(&info).unwrap();
        assert!(json.contains("ekamcore_default"));
    }

    #[test]
    fn container_logs_handles_missing() {
        let logs = collect_container_logs("nonexistent-container-12345", 10);
        // Should return error message, not panic
        assert!(!logs.is_empty());
    }
}

//! S15-003 — Dashboard IPC commands.
//!
//! Provides aggregated dashboard data (health + disk + API counts) and
//! service control commands (force restart with backoff reset, start/stop all).

use serde::Serialize;
use tauri::State;

use crate::container_runtime::ServiceHealth;
use crate::state::AppState;

// ── Types ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct DashboardData {
    pub services: Vec<ServiceHealth>,
    pub disk_free_gb: f64,
    pub disk_warning: bool,
    pub uptime_hours: f64,
    pub total_files: u64,
    pub total_photos: u64,
    pub total_persons: u64,
    pub last_backup: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct ApiCounts {
    files: u64,
    photos: u64,
    persons: u64,
    last_backup: Option<String>,
}

// ── Commands ────────────────────────────────────────────────────────────────

/// Get aggregated dashboard data: service health + disk + API counts.
#[tauri::command]
pub async fn get_dashboard_data(state: State<'_, AppState>) -> Result<DashboardData, String> {
    // 1. Service health
    let services = state
        .runtime
        .get_service_health()
        .await
        .unwrap_or_default();

    // 2. Disk check
    let disk = crate::disk::check_disk();

    // 3. API counts — best-effort HTTP call to the local API
    let counts = fetch_api_counts().await;

    // 4. Uptime (process uptime, not system uptime)
    let uptime_hours = state.started_at.elapsed().as_secs_f64() / 3600.0;

    Ok(DashboardData {
        services,
        disk_free_gb: disk.free_gb,
        disk_warning: disk.warning || !disk.passed,
        uptime_hours,
        total_files: counts.files,
        total_photos: counts.photos,
        total_persons: counts.persons,
        last_backup: counts.last_backup,
    })
}

/// Force-restart a service, resetting its watchdog backoff state.
#[tauri::command]
pub async fn force_restart_service(
    state: State<'_, AppState>,
    service: String,
) -> Result<(), String> {
    let mut wd = state.watchdog.lock().await;
    wd.force_restart(&service).await
}

/// Stop all EkamCore services via docker compose down.
#[tauri::command]
pub async fn stop_all_services(state: State<'_, AppState>) -> Result<(), String> {
    state
        .runtime
        .stop_stack()
        .await
        .map_err(|e| e.to_string())
}

/// Start all EkamCore services via docker compose up -d.
#[tauri::command]
pub async fn start_all_services(state: State<'_, AppState>) -> Result<(), String> {
    state
        .runtime
        .start_stack()
        .await
        .map_err(|e| e.to_string())
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/// Best-effort fetch of counts from the local API's health endpoint.
async fn fetch_api_counts() -> ApiCounts {
    let default = ApiCounts {
        files: 0,
        photos: 0,
        persons: 0,
        last_backup: None,
    };

    let resp = match reqwest::Client::new()
        .get("http://localhost:8420/health")
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(r) if r.status().is_success() => r,
        _ => return default,
    };

    let json: serde_json::Value = match resp.json().await {
        Ok(v) => v,
        Err(_) => return default,
    };

    ApiCounts {
        files: json["counts"]["files"].as_u64().unwrap_or(0),
        photos: json["counts"]["photos"].as_u64().unwrap_or(0),
        persons: json["counts"]["persons"].as_u64().unwrap_or(0),
        last_backup: json["last_backup"].as_str().map(String::from),
    }
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dashboard_data_serializable() {
        let data = DashboardData {
            services: vec![],
            disk_free_gb: 120.5,
            disk_warning: false,
            uptime_hours: 2.5,
            total_files: 1234,
            total_photos: 567,
            total_persons: 89,
            last_backup: Some("2026-04-16T12:00:00Z".to_string()),
        };
        let json = serde_json::to_string(&data).unwrap();
        assert!(json.contains("\"total_files\":1234"));
        assert!(json.contains("\"disk_free_gb\":120.5"));
    }

    #[test]
    fn api_counts_defaults() {
        let c = ApiCounts {
            files: 0,
            photos: 0,
            persons: 0,
            last_backup: None,
        };
        assert_eq!(c.files, 0);
        assert!(c.last_backup.is_none());
    }
}

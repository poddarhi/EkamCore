//! IPC commands for ContainerRuntime and Keychain (S15-001).
//!
//! Each function is a `#[tauri::command]` that the React frontend
//! invokes via `invoke<T>("command_name", { args })`. Errors are
//! returned as strings (Tauri IPC constraint).

use tauri::State;

use crate::container_runtime::{ContainerStats, RuntimeError, ServiceHealth};
use crate::keychain::{KeychainError, KeychainManager};
use crate::state::AppState;

// ── Container runtime commands ───────────────────────────────────────────

#[tauri::command]
pub async fn get_service_health(
    state: State<'_, AppState>,
) -> Result<Vec<ServiceHealth>, String> {
    state
        .runtime
        .get_service_health()
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn restart_service(
    state: State<'_, AppState>,
    service: String,
) -> Result<(), String> {
    state
        .runtime
        .restart_service(&service)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_service_logs(
    state: State<'_, AppState>,
    service: String,
    lines: usize,
) -> Result<String, String> {
    state
        .runtime
        .get_service_logs(&service, lines)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_container_stats(
    state: State<'_, AppState>,
) -> Result<Vec<ContainerStats>, String> {
    state
        .runtime
        .get_container_stats()
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn start_stack(state: State<'_, AppState>) -> Result<(), String> {
    state
        .runtime
        .start_stack()
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn stop_stack(state: State<'_, AppState>) -> Result<(), String> {
    state
        .runtime
        .stop_stack()
        .await
        .map_err(|e| e.to_string())
}

// ── Keychain commands ────────────────────────────────────────────────────

#[tauri::command]
pub fn keychain_has_secret(service: String) -> bool {
    KeychainManager::has_secret(&service)
}

#[tauri::command]
pub fn keychain_get_secret(service: String) -> Result<String, String> {
    KeychainManager::get_secret(&service).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn keychain_set_secret(
    service: String,
    value: String,
) -> Result<(), String> {
    KeychainManager::set_secret(&service, &value).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn keychain_generate_secret(length: usize) -> String {
    KeychainManager::generate_random_secret(length)
}

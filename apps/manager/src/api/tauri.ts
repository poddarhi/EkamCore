/**
 * Typed Tauri invoke wrapper (S15-001).
 *
 * Centralises all IPC calls so the frontend never calls ``invoke``
 * directly with a raw string. Errors from the Rust side arrive as
 * strings (Tauri IPC constraint); this module re-throws them as
 * real Errors so callers can try/catch.
 */

import { invoke } from "@tauri-apps/api/core";

export type HealthState =
  | "healthy"
  | "unhealthy"
  | "starting"
  | "not_running";

export interface ServiceHealth {
  name: string;
  state: HealthState;
  uptime_seconds: number | null;
  memory_mb: number | null;
  cpu_percent: number | null;
}

export interface ContainerStats {
  name: string;
  memory_usage_mb: number;
  memory_limit_mb: number;
  cpu_percent: number;
  network_rx_mb: number;
  network_tx_mb: number;
}

// ── Container runtime ────────────────────────────────────────────────────

export async function getServiceHealth(): Promise<ServiceHealth[]> {
  return invoke<ServiceHealth[]>("get_service_health");
}

export async function restartService(service: string): Promise<void> {
  return invoke<void>("restart_service", { service });
}

export async function getServiceLogs(
  service: string,
  lines: number = 200,
): Promise<string> {
  return invoke<string>("get_service_logs", { service, lines });
}

export async function getContainerStats(): Promise<ContainerStats[]> {
  return invoke<ContainerStats[]>("get_container_stats");
}

export async function startStack(): Promise<void> {
  return invoke<void>("start_stack");
}

export async function stopStack(): Promise<void> {
  return invoke<void>("stop_stack");
}

// ── Keychain ─────────────────────────────────────────────────────────────

export async function keychainHasSecret(service: string): Promise<boolean> {
  return invoke<boolean>("keychain_has_secret", { service });
}

export async function keychainGetSecret(service: string): Promise<string> {
  return invoke<string>("keychain_get_secret", { service });
}

export async function keychainSetSecret(
  service: string,
  value: string,
): Promise<void> {
  return invoke<void>("keychain_set_secret", { service, value });
}

export async function keychainGenerateSecret(
  length: number = 32,
): Promise<string> {
  return invoke<string>("keychain_generate_secret", { length });
}

// ── Setup wizard (S15-002) ──────────────────────────────────────────────────

export interface AdminCreateResult {
  success: boolean;
  secrets_generated: boolean;
  message: string;
}

export interface PermissionsResult {
  calendar: boolean;
  reminders: boolean;
  contacts: boolean;
}

export async function pullImages(): Promise<void> {
  return invoke<void>("pull_images");
}

export async function initializeDatabase(): Promise<void> {
  return invoke<void>("initialize_database");
}

export async function createAdmin(
  email: string,
  password: string,
): Promise<AdminCreateResult> {
  return invoke<AdminCreateResult>("create_admin", { email, password });
}

export async function requestPermissions(): Promise<PermissionsResult> {
  return invoke<PermissionsResult>("request_permissions");
}

export async function selectSourceFolders(): Promise<string[]> {
  return invoke<string[]>("select_source_folders");
}

export async function configurePaperless(consumeDir: string): Promise<void> {
  return invoke<void>("configure_paperless", { consumeDir });
}

// ── Dashboard (S15-003) ─────────────────────────────────────────────────────

export interface DashboardData {
  services: ServiceHealth[];
  disk_free_gb: number;
  disk_warning: boolean;
  uptime_hours: number;
  total_files: number;
  total_photos: number;
  total_persons: number;
  last_backup: string | null;
}

export async function getDashboardData(): Promise<DashboardData> {
  return invoke<DashboardData>("get_dashboard_data");
}

export async function forceRestartService(service: string): Promise<void> {
  return invoke<void>("force_restart_service", { service });
}

export async function stopAllServices(): Promise<void> {
  return invoke<void>("stop_all_services");
}

export async function startAllServices(): Promise<void> {
  return invoke<void>("start_all_services");
}

// ── Diagnostics + Storage (S15-004) ─────────────────────────────────────────

export interface DiagnosticsResult {
  path: string;
  size_bytes: number;
  files_included: string[];
}

export async function generateDiagnostics(): Promise<DiagnosticsResult> {
  return invoke<DiagnosticsResult>("generate_diagnostics");
}

export async function getSystemInfoText(): Promise<string> {
  return invoke<string>("get_system_info_text");
}

export async function cleanDockerCache(): Promise<string> {
  return invoke<string>("clean_docker_cache");
}

export async function getStorageBreakdown(): Promise<Record<string, unknown>> {
  return invoke<Record<string, unknown>>("get_storage_breakdown");
}

// ── macOS Integration (S15-005) ─────────────────────────────────────────────

export interface LaunchdStatus {
  login_item_registered: boolean;
  backup_scheduled: boolean;
  backup_hour: number;
  backup_minute: number;
}

export interface SecretStatus {
  all_present: boolean;
  missing: string[];
  keychain_accessible: boolean;
}

export interface InjectionResult {
  success: boolean;
  message: string;
  containers_healthy: boolean;
}

export async function registerLoginItem(): Promise<void> {
  return invoke<void>("register_login_item");
}

export async function unregisterLoginItem(): Promise<void> {
  return invoke<void>("unregister_login_item");
}

export async function isLoginItemRegistered(): Promise<boolean> {
  return invoke<boolean>("is_login_item_registered");
}

export async function installBackupSchedule(hour: number, minute: number): Promise<void> {
  return invoke<void>("install_backup_schedule", { hour, minute });
}

export async function uninstallBackupSchedule(): Promise<void> {
  return invoke<void>("uninstall_backup_schedule");
}

export async function getLaunchdStatus(): Promise<LaunchdStatus> {
  return invoke<LaunchdStatus>("get_launchd_status");
}

export async function runBackupNow(): Promise<string> {
  return invoke<string>("run_backup_now");
}

export async function checkSecretStatus(): Promise<SecretStatus> {
  return invoke<SecretStatus>("check_secret_status");
}

export async function injectSecretsAndStart(): Promise<InjectionResult> {
  return invoke<InjectionResult>("inject_secrets_and_start");
}

export async function regenerateAllSecrets(): Promise<string> {
  return invoke<string>("regenerate_all_secrets");
}

export async function resetSetup(): Promise<void> {
  return invoke<void>("reset_setup");
}

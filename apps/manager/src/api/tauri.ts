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

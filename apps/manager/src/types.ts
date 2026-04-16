export type StepStatus = "pending" | "in_progress" | "passed" | "failed" | "skipped";

export interface WizardStep {
  id: number;
  label: string;
  status: StepStatus;
}

export interface HardwareCheckResult {
  is_apple_silicon: boolean;
  ram_gb: number;
  macos_version: string;
  ram_ok: boolean;
  macos_ok: boolean;
  all_passed: boolean;
}

export interface DiskCheckResult {
  free_gb: number;
  required_gb: number;
  passed: boolean;
  warning: boolean;
}

export interface DockerCheckResult {
  installed: boolean;
  /** "orbstack" | "docker_desktop" | "none" */
  runtime: string;
  version: string | null;
}

export interface TailscaleCheckResult {
  installed: boolean;
  connected: boolean;
  hostname: string | null;
  ip: string | null;
}

export interface WizardState {
  current_step: number;
  steps: Record<string, StepStatus>;
  completed: boolean;
}

// S15-002: Setup wizard step types

export interface PullProgressEvent {
  service: string;
  status: string;
  percent: number | null;
}

export interface DbInitProgressEvent {
  phase: string;
  status: string;
}

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

// S15-003: Dashboard + Watchdog types

export type HealthState = "healthy" | "unhealthy" | "starting" | "not_running";

export interface ServiceHealthInfo {
  name: string;
  state: HealthState;
  uptime_seconds: number | null;
  memory_mb: number | null;
  cpu_percent: number | null;
}

export interface DashboardData {
  services: ServiceHealthInfo[];
  disk_free_gb: number;
  disk_warning: boolean;
  uptime_hours: number;
  total_files: number;
  total_photos: number;
  total_persons: number;
  last_backup: string | null;
}

export interface HealthUpdateEvent {
  services: ServiceHealthInfo[];
  timestamp: string;
}

export interface ServiceCriticalEvent {
  service: string;
  consecutive_failures: number;
  message: string;
}

export interface ServiceUnstableEvent {
  service: string;
  restarts_in_hour: number;
  message: string;
}

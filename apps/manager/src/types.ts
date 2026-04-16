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

// S15-004: Jobs, Storage, Diagnostics types

export type JobStatus = "active" | "queued" | "completed" | "failed";

export interface Job {
  id: string;
  filename: string;
  source: string;
  status: JobStatus;
  stage: string;
  progress: number;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface JobsData {
  active: Job[];
  queued: Job[];
  completed: Job[];
  failed: Job[];
}

export interface StorageBreakdown {
  docker_images: string;
  docker_containers: string;
  docker_volumes: string;
  ollama_models_mb: number;
  disk_free_gb: number;
  disk_warning: boolean;
}

export interface DiagnosticsResult {
  path: string;
  size_bytes: number;
  files_included: string[];
}

export interface DiagnosticsProgressEvent {
  phase: string;
  status: string;
}

// S15-005: macOS integration types

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

// S15-006: Update + Rollback types

export interface UpdateInfo {
  available: boolean;
  current_version: string;
  latest_version: string;
  release_notes: string;
  download_size_mb: number;
}

export interface UpdateProgress {
  step: string;
  step_number: number;
  total_steps: number;
  percent: number;
  message: string;
}

export interface UpdateResult {
  success: boolean;
  message: string;
  rolled_back: boolean;
  new_version: string | null;
}

export interface BackupEntry {
  path: string;
  timestamp: string;
  size_mb: number;
}

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

/**
 * S15-002 — 8-Step Setup Wizard
 *
 * Full-screen wizard for first-run experience. Guides user through:
 *   1. Hardware check    5. Database init
 *   2. Disk space        6. Admin account
 *   3. Docker/OrbStack   7. Data sources
 *   4. Pull images       8. Tailscale (optional)
 *
 * State persisted to setup-state.json via Tauri commands.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  StepStatus,
  HardwareCheckResult,
  DiskCheckResult,
  DockerCheckResult,
  TailscaleCheckResult,
  PullProgressEvent,
  DbInitProgressEvent,
  AdminCreateResult,
  PermissionsResult,
} from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STEPS = [
  { id: 1, label: "Hardware Check" },
  { id: 2, label: "Disk Space" },
  { id: 3, label: "Docker / OrbStack" },
  { id: 4, label: "Pull Images" },
  { id: 5, label: "Database Init" },
  { id: 6, label: "Admin Account" },
  { id: 7, label: "Data Sources" },
  { id: 8, label: "Tailscale" },
];

const STEP_DESCRIPTIONS: Record<number, string> = {
  1: "Verifying your Mac meets the minimum requirements for EkamCore.",
  2: "Checking that there is enough free disk space for Docker images, models, and data.",
  3: "Detecting Docker Desktop or OrbStack — required to run EkamCore services.",
  4: "Pulling all required Docker images. This may take a few minutes on first run.",
  5: "Starting PostgreSQL and running database migrations.",
  6: "Creating the admin account and generating encryption keys.",
  7: "Configure access to Calendar, Reminders, Contacts, and document folders.",
  8: "Tailscale enables secure remote access. This step is optional.",
};

const IMAGE_SERVICES = [
  "postgres", "redis", "qdrant", "caddy", "ollama",
  "paperless", "api", "workers", "web", "migrate",
];

// ---------------------------------------------------------------------------
// Step state
// ---------------------------------------------------------------------------

interface StepState {
  status: StepStatus;
  error?: string;
  data?: Record<string, unknown>;
}

const initialStepStates = (): Record<number, StepState> =>
  Object.fromEntries(STEPS.map((s) => [s.id, { status: "pending" as StepStatus }]));

const STATUS_ICON: Record<StepStatus, string> = {
  pending: "\u25CB",
  in_progress: "\u25CC",
  passed: "\u2713",
  failed: "\u2717",
  skipped: "\u2013",
};

const STATUS_COLOR: Record<StepStatus, string> = {
  pending: "#555",
  in_progress: "#60a5fa",
  passed: "#34d399",
  failed: "#f87171",
  skipped: "#888",
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  onComplete: () => void;
}

export default function SetupWizard({ onComplete }: Props) {
  const [activeStep, setActiveStep] = useState(1);
  const [stepStates, setStepStates] = useState<Record<number, StepState>>(initialStepStates());

  // Step 4: image pull progress
  const [pullProgress, setPullProgress] = useState<Record<string, PullProgressEvent>>({});

  // Step 5: DB init phases
  const [dbPhases, setDbPhases] = useState<Record<string, string>>({});

  // Step 6: admin form
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [adminConfirm, setAdminConfirm] = useState("");

  // Step 7: permissions + folders
  const [permissions, setPermissions] = useState<PermissionsResult>({ calendar: false, reminders: false, contacts: false });
  const [docFolders, setDocFolders] = useState<string[]>([]);
  const [photoFolders, setPhotoFolders] = useState<string[]>([]);
  const [paperlessDir, setPaperlessDir] = useState("");

  // Event listeners
  const unlistenPull = useRef<UnlistenFn | null>(null);
  const unlistenDb = useRef<UnlistenFn | null>(null);

  useEffect(() => {
    listen<PullProgressEvent>("pull-progress", (e) => {
      setPullProgress((prev) => ({ ...prev, [e.payload.service]: e.payload }));
    }).then((fn) => { unlistenPull.current = fn; });

    listen<DbInitProgressEvent>("db-init-progress", (e) => {
      setDbPhases((prev) => ({ ...prev, [e.payload.phase]: e.payload.status }));
    }).then((fn) => { unlistenDb.current = fn; });

    return () => {
      unlistenPull.current?.();
      unlistenDb.current?.();
    };
  }, []);

  const setStep = useCallback((id: number, patch: Partial<StepState>) => {
    setStepStates((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }, []);

  // ── Step runners ────────────────────────────────────────────────────────

  const runStep = useCallback(async (stepId: number) => {
    setStep(stepId, { status: "in_progress", error: undefined });
    try {
      switch (stepId) {
        case 1: {
          const result = await invoke<HardwareCheckResult>("check_hardware");
          if (result.all_passed) {
            setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
          } else {
            const msgs: string[] = [];
            if (!result.is_apple_silicon) msgs.push("Requires Apple Silicon (M1 or later).");
            if (!result.ram_ok) msgs.push(`Requires 16 GB RAM \u2014 detected ${result.ram_gb.toFixed(0)} GB.`);
            if (!result.macos_ok) msgs.push(`Requires macOS 13.0+ \u2014 detected ${result.macos_version}.`);
            setStep(stepId, { status: "failed", error: msgs.join(" "), data: result as unknown as Record<string, unknown> });
          }
          break;
        }
        case 2: {
          const result = await invoke<DiskCheckResult>("check_disk");
          if (result.passed) {
            setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
          } else {
            setStep(stepId, { status: "failed", error: `Need ${result.required_gb} GB free \u2014 found ${result.free_gb.toFixed(1)} GB.` });
          }
          break;
        }
        case 3: {
          const result = await invoke<DockerCheckResult>("check_docker");
          if (result.installed) {
            setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
          } else {
            setStep(stepId, { status: "failed", error: "Docker / OrbStack not found. Install OrbStack (recommended) or Docker Desktop, then try again." });
          }
          break;
        }
        case 4: {
          setPullProgress({});
          await invoke("pull_images");
          setStep(stepId, { status: "passed" });
          break;
        }
        case 5: {
          setDbPhases({});
          await invoke("initialize_database");
          setStep(stepId, { status: "passed" });
          break;
        }
        case 6: {
          // Validated before calling
          const result = await invoke<AdminCreateResult>("create_admin", {
            email: adminEmail,
            password: adminPassword,
          });
          if (result.success) {
            setStep(stepId, { status: "passed", data: { message: result.message, secrets_generated: result.secrets_generated } });
          } else {
            setStep(stepId, { status: "failed", error: result.message });
          }
          break;
        }
        case 7: {
          // Permissions are requested individually via toggles — just mark passed
          setStep(stepId, { status: "passed" });
          break;
        }
        case 8: {
          const result = await invoke<TailscaleCheckResult>("check_tailscale");
          setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
          break;
        }
      }
    } catch (err) {
      setStep(stepId, { status: "failed", error: String(err) });
    }
  }, [setStep, adminEmail, adminPassword]);

  // ── Navigation ──────────────────────────────────────────────────────────

  const advance = useCallback(async () => {
    const st = stepStates[activeStep];

    // Step 6 requires form validation before running
    if (activeStep === 6 && st.status !== "passed") {
      if (!adminEmail || !adminPassword) return;
      if (adminPassword !== adminConfirm) return;
      if (adminPassword.length < 12) return;
      await runStep(6);
      return;
    }

    // Step 7: mark as done when user clicks Continue
    if (activeStep === 7 && st.status !== "passed") {
      setStep(7, { status: "passed" });
      if (activeStep < STEPS.length) {
        setActiveStep(activeStep + 1);
        await runStep(activeStep + 1);
      }
      return;
    }

    if (st.status !== "passed" && st.status !== "skipped") {
      await runStep(activeStep);
      return;
    }

    if (activeStep < STEPS.length) {
      const next = activeStep + 1;
      setActiveStep(next);
      // Auto-run for automated steps (1-5, 8)
      if (next !== 6 && next !== 7) {
        await runStep(next);
      }
    } else {
      // Save state and finish
      await invoke("mark_setup_complete");
      onComplete();
    }
  }, [activeStep, stepStates, runStep, onComplete, adminEmail, adminPassword, adminConfirm, setStep]);

  const goBack = useCallback(() => {
    if (activeStep > 1) setActiveStep(activeStep - 1);
  }, [activeStep]);

  const retry = useCallback(async () => {
    await runStep(activeStep);
  }, [activeStep, runStep]);

  const currentState = stepStates[activeStep];

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0f0f11" }}>
      {/* Left rail */}
      <div style={railStyle}>
        <div style={{ padding: "0 20px 24px", color: "#e8e8ea", fontSize: 15, fontWeight: 600 }}>
          EkamCore Setup
        </div>
        {STEPS.map((step) => {
          const state = stepStates[step.id];
          const isActive = step.id === activeStep;
          return (
            <div
              key={step.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 20px",
                background: isActive ? "#27272a" : "transparent",
                borderLeft: `3px solid ${isActive ? "#60a5fa" : "transparent"}`,
                cursor: "default",
              }}
            >
              <span style={{ color: STATUS_COLOR[state.status], fontSize: 14, width: 16 }}>
                {STATUS_ICON[state.status]}
              </span>
              <span style={{
                fontSize: 13,
                color: isActive ? "#e8e8ea" : state.status === "passed" ? "#a1a1aa" : "#71717a",
              }}>
                {step.label}
              </span>
            </div>
          );
        })}

        {/* Progress indicator */}
        <div style={{ marginTop: "auto", padding: "20px" }}>
          <div style={{ fontSize: 11, color: "#555", marginBottom: 8 }}>
            {Object.values(stepStates).filter((s) => s.status === "passed" || s.status === "skipped").length} of {STEPS.length} complete
          </div>
          <div style={{ height: 3, background: "#27272a", borderRadius: 2, overflow: "hidden" }}>
            <div style={{
              height: "100%",
              width: `${(Object.values(stepStates).filter((s) => s.status === "passed" || s.status === "skipped").length / STEPS.length) * 100}%`,
              background: "#3b82f6",
              borderRadius: 2,
              transition: "width 0.4s ease",
            }} />
          </div>
        </div>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "48px 56px", overflow: "auto" }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8, color: "#e8e8ea" }}>
          Step {activeStep}: {STEPS[activeStep - 1].label}
        </h1>
        <p style={{ color: "#71717a", fontSize: 14, marginBottom: 32 }}>
          {STEP_DESCRIPTIONS[activeStep]}
        </p>

        {/* Status banners */}
        {currentState.status === "in_progress" && activeStep !== 4 && activeStep !== 5 && (
          <InfoBox bg="#1e3a5f" border="#60a5fa">Running checks...</InfoBox>
        )}
        {currentState.status === "passed" && activeStep < 6 && (
          <InfoBox bg="#14532d" border="#34d399">All checks passed.</InfoBox>
        )}
        {currentState.status === "failed" && currentState.error && (
          <InfoBox bg="#450a0a" border="#f87171">{currentState.error}</InfoBox>
        )}

        {/* Step-specific content */}
        {activeStep === 1 && currentState.data && (
          <HardwareDetail data={currentState.data as unknown as HardwareCheckResult} />
        )}
        {activeStep === 2 && currentState.data && (
          <DiskDetail data={currentState.data as unknown as DiskCheckResult} />
        )}
        {activeStep === 3 && currentState.data && (
          <DockerDetail data={currentState.data as unknown as DockerCheckResult} />
        )}
        {activeStep === 4 && (
          <PullImagesDetail progress={pullProgress} isRunning={currentState.status === "in_progress"} />
        )}
        {activeStep === 5 && (
          <DbInitDetail phases={dbPhases} isRunning={currentState.status === "in_progress"} />
        )}
        {activeStep === 6 && (
          <AdminAccountStep
            email={adminEmail}
            password={adminPassword}
            confirm={adminConfirm}
            onEmailChange={setAdminEmail}
            onPasswordChange={setAdminPassword}
            onConfirmChange={setAdminConfirm}
            state={currentState}
          />
        )}
        {activeStep === 7 && (
          <DataSourcesStep
            permissions={permissions}
            onPermissionsRefresh={async () => {
              const p = await invoke<PermissionsResult>("request_permissions");
              setPermissions(p);
            }}
            docFolders={docFolders}
            photoFolders={photoFolders}
            paperlessDir={paperlessDir}
            onAddDocFolders={async () => {
              const paths = await invoke<string[]>("select_source_folders");
              if (paths.length > 0) setDocFolders((prev) => [...prev, ...paths]);
            }}
            onAddPhotoFolders={async () => {
              const paths = await invoke<string[]>("select_source_folders");
              if (paths.length > 0) setPhotoFolders((prev) => [...prev, ...paths]);
            }}
            onPaperlessDir={async () => {
              const paths = await invoke<string[]>("select_source_folders");
              if (paths.length > 0) {
                setPaperlessDir(paths[0]);
                await invoke("configure_paperless", { consumeDir: paths[0] });
              }
            }}
          />
        )}
        {activeStep === 8 && currentState.data && (
          <TailscaleDetail data={currentState.data as unknown as TailscaleCheckResult} />
        )}

        {/* Action bar */}
        <div style={{ marginTop: "auto", display: "flex", gap: 12, paddingTop: 32 }}>
          {activeStep > 1 && (
            <button onClick={goBack} style={secondaryBtnStyle}>Back</button>
          )}
          {currentState.status === "failed" ? (
            <button onClick={retry} style={primaryBtnStyle}>Try Again</button>
          ) : (
            <button
              onClick={advance}
              disabled={currentState.status === "in_progress" || (activeStep === 6 && !isAdminFormValid(adminEmail, adminPassword, adminConfirm))}
              style={{
                ...primaryBtnStyle,
                opacity: currentState.status === "in_progress" ? 0.5 : 1,
              }}
            >
              {buttonLabel(activeStep, currentState)}
            </button>
          )}
          {activeStep === 8 && currentState.status !== "passed" && (
            <button
              onClick={async () => {
                setStep(8, { status: "skipped" });
                await invoke("mark_setup_complete");
                onComplete();
              }}
              style={secondaryBtnStyle}
            >
              Skip & Finish
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Button label logic
// ---------------------------------------------------------------------------

function buttonLabel(step: number, state: StepState): string {
  if (state.status === "in_progress") return "Working...";
  if (state.status === "pending") {
    if (step === 6) return "Create Account";
    if (step === 7) return "Continue";
    return "Run Check";
  }
  if (state.status === "passed" || state.status === "skipped") {
    if (step === 8) return "Finish Setup";
    return "Continue";
  }
  return "Continue";
}

// ---------------------------------------------------------------------------
// Admin form validation
// ---------------------------------------------------------------------------

function isAdminFormValid(email: string, password: string, confirm: string): boolean {
  if (!email || !email.includes("@")) return false;
  if (password.length < 12) return false;
  if (password !== confirm) return false;
  if (!/[A-Z]/.test(password)) return false;
  if (!/[0-9]/.test(password)) return false;
  if (!/[^A-Za-z0-9]/.test(password)) return false;
  return true;
}

function passwordStrength(password: string): { label: string; color: string; pct: number } {
  let score = 0;
  if (password.length >= 12) score++;
  if (password.length >= 16) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  if (score <= 2) return { label: "Weak", color: "#f87171", pct: 33 };
  if (score <= 3) return { label: "Fair", color: "#fbbf24", pct: 60 };
  return { label: "Strong", color: "#34d399", pct: 100 };
}

// ---------------------------------------------------------------------------
// Step content components
// ---------------------------------------------------------------------------

function HardwareDetail({ data }: { data: HardwareCheckResult }) {
  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <CheckRow label="Apple Silicon" pass={data.is_apple_silicon} detail="Required" />
      <CheckRow label="RAM" pass={data.ram_ok} detail={`${data.ram_gb.toFixed(0)} GB (need \u2265 16 GB)`} />
      <CheckRow label="macOS" pass={data.macos_ok} detail={`${data.macos_version} (need \u2265 13.0)`} />
    </div>
  );
}

function DiskDetail({ data }: { data: DiskCheckResult }) {
  const pct = Math.min((data.free_gb / (data.free_gb + 20)) * 100, 100);
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 13, color: "#a1a1aa", marginBottom: 8 }}>
        {data.free_gb.toFixed(1)} GB free on boot volume
      </div>
      <div style={{ height: 8, background: "#27272a", borderRadius: 4, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${pct}%`,
          background: data.passed ? (data.warning ? "#fbbf24" : "#34d399") : "#f87171",
          borderRadius: 4,
        }} />
      </div>
    </div>
  );
}

function DockerDetail({ data }: { data: DockerCheckResult }) {
  const label = data.runtime === "orbstack" ? "OrbStack" : data.runtime === "docker_desktop" ? "Docker Desktop" : "Unknown";
  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <CheckRow label="Runtime" pass={data.installed} detail={label} />
      {data.version && <CheckRow label="Version" pass detail={data.version} />}
    </div>
  );
}

function PullImagesDetail({ progress, isRunning }: { progress: Record<string, PullProgressEvent>; isRunning: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
      {IMAGE_SERVICES.map((svc) => {
        const p = progress[svc];
        const pct = p?.percent ?? 0;
        const isDone = p?.status === "done" || p?.status === "cached" || p?.status === "local_build";
        const isFailed = p?.status === "failed";
        const statusLabel = p?.status === "cached" ? "Cached" : p?.status === "local_build" ? "Local" : p?.status === "done" ? "Done" : p?.status === "pulling" ? "Pulling..." : p?.status === "failed" ? "Failed" : isRunning ? "Waiting..." : "";
        return (
          <div key={svc}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 13, color: isDone ? "#a1a1aa" : isFailed ? "#f87171" : "#e8e8ea" }}>{svc}</span>
              <span style={{ fontSize: 11, color: isDone ? "#34d399" : isFailed ? "#f87171" : "#71717a" }}>{statusLabel}</span>
            </div>
            <div style={{ height: 4, background: "#27272a", borderRadius: 2, overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${pct}%`,
                background: isDone ? "#34d399" : isFailed ? "#f87171" : "#3b82f6",
                borderRadius: 2,
                transition: "width 0.3s ease",
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DbInitDetail({ phases, isRunning }: { phases: Record<string, string>; isRunning: boolean }) {
  const PHASE_LABELS: Record<string, string> = {
    starting_postgres: "Starting PostgreSQL",
    waiting_postgres: "Waiting for PostgreSQL",
    running_migrations: "Running migrations",
    starting_redis: "Starting Redis",
    complete: "Complete",
  };
  const phaseOrder = ["starting_postgres", "running_migrations", "starting_redis", "complete"];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 8 }}>
      {phaseOrder.map((phase) => {
        const status = phases[phase];
        const isDone = status === "done";
        const isFailed = status === "failed";
        const isActive = status === "running";
        return (
          <div key={phase} style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{
              color: isDone ? "#34d399" : isFailed ? "#f87171" : isActive ? "#60a5fa" : "#555",
              fontSize: 14, width: 16,
            }}>
              {isDone ? "\u2713" : isFailed ? "\u2717" : isActive ? "\u25CC" : "\u25CB"}
            </span>
            <span style={{
              fontSize: 13,
              color: isDone ? "#a1a1aa" : isActive ? "#e8e8ea" : isFailed ? "#f87171" : "#555",
            }}>
              {PHASE_LABELS[phase] ?? phase}
            </span>
          </div>
        );
      })}
      {isRunning && !phases.complete && (
        <div style={{ fontSize: 12, color: "#71717a", marginTop: 8 }}>
          This may take a minute...
        </div>
      )}
    </div>
  );
}

function AdminAccountStep({
  email, password, confirm,
  onEmailChange, onPasswordChange, onConfirmChange,
  state,
}: {
  email: string; password: string; confirm: string;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onConfirmChange: (v: string) => void;
  state: StepState;
}) {
  const strength = passwordStrength(password);
  const mismatch = confirm.length > 0 && password !== confirm;

  if (state.status === "passed") {
    return (
      <div>
        <InfoBox bg="#14532d" border="#34d399">
          {(state.data as Record<string, unknown>)?.message as string || "Admin account created. Encryption keys stored in macOS Keychain."}
        </InfoBox>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 400 }}>
      <div>
        <label style={labelStyle}>Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => onEmailChange(e.target.value)}
          placeholder="admin@example.com"
          style={inputStyle}
          disabled={state.status === "in_progress"}
        />
      </div>
      <div>
        <label style={labelStyle}>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          placeholder="Min 12 chars, 1 uppercase, 1 number, 1 special"
          style={inputStyle}
          disabled={state.status === "in_progress"}
        />
        {password.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: "#71717a" }}>Strength</span>
              <span style={{ fontSize: 11, color: strength.color }}>{strength.label}</span>
            </div>
            <div style={{ height: 3, background: "#27272a", borderRadius: 2, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${strength.pct}%`, background: strength.color, borderRadius: 2, transition: "width 0.3s" }} />
            </div>
          </div>
        )}
      </div>
      <div>
        <label style={labelStyle}>Confirm Password</label>
        <input
          type="password"
          value={confirm}
          onChange={(e) => onConfirmChange(e.target.value)}
          placeholder="Re-enter password"
          style={{ ...inputStyle, borderColor: mismatch ? "#f87171" : "#3f3f46" }}
          disabled={state.status === "in_progress"}
        />
        {mismatch && (
          <span style={{ fontSize: 12, color: "#f87171", marginTop: 4, display: "block" }}>Passwords do not match.</span>
        )}
      </div>
      <div style={{ fontSize: 12, color: "#555" }}>
        Requirements: 12+ characters, 1 uppercase, 1 number, 1 special character.
      </div>
    </div>
  );
}

function DataSourcesStep({
  permissions, onPermissionsRefresh,
  docFolders, photoFolders, paperlessDir,
  onAddDocFolders, onAddPhotoFolders, onPaperlessDir,
}: {
  permissions: PermissionsResult;
  onPermissionsRefresh: () => Promise<void>;
  docFolders: string[];
  photoFolders: string[];
  paperlessDir: string;
  onAddDocFolders: () => Promise<void>;
  onAddPhotoFolders: () => Promise<void>;
  onPaperlessDir: () => Promise<void>;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* System data permissions */}
      <div>
        <h3 style={sectionHeadingStyle}>System Data</h3>
        <p style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>
          Grant access to system data sources. A macOS permission dialog will appear for each.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <PermToggle label="Calendar" granted={permissions.calendar} onRequest={onPermissionsRefresh} />
          <PermToggle label="Reminders" granted={permissions.reminders} onRequest={onPermissionsRefresh} />
          <PermToggle label="Contacts" granted={permissions.contacts} onRequest={onPermissionsRefresh} />
        </div>
      </div>

      {/* Document folders */}
      <div>
        <h3 style={sectionHeadingStyle}>Document Folders</h3>
        <p style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>
          Select folders containing documents to index.
        </p>
        <FolderList folders={docFolders} onAdd={onAddDocFolders} />
      </div>

      {/* Photo folders */}
      <div>
        <h3 style={sectionHeadingStyle}>Photo Folders</h3>
        <p style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>
          Select folders containing photos to index.
        </p>
        <FolderList folders={photoFolders} onAdd={onAddPhotoFolders} />
      </div>

      {/* PaperlessNGX */}
      <div>
        <h3 style={sectionHeadingStyle}>PaperlessNGX Consume Folder</h3>
        <p style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>
          Drop documents here for automatic OCR and ingestion.
        </p>
        {paperlessDir ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13, color: "#34d399" }}>{"\u2713"}</span>
            <span style={{ fontSize: 13, color: "#a1a1aa", fontFamily: "monospace" }}>{paperlessDir}</span>
          </div>
        ) : (
          <button onClick={onPaperlessDir} style={secondaryBtnStyle}>
            Select Folder
          </button>
        )}
      </div>

      <div style={{ fontSize: 12, color: "#555", marginTop: 8 }}>
        You can always add more sources later in Settings.
      </div>
    </div>
  );
}

function PermToggle({ label, granted, onRequest }: { label: string; granted: boolean; onRequest: () => Promise<void> }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0" }}>
      <span style={{ fontSize: 13, color: "#e8e8ea", width: 100 }}>{label}</span>
      {granted ? (
        <span style={{ fontSize: 12, color: "#34d399" }}>{"\u2713"} Granted</span>
      ) : (
        <button onClick={onRequest} style={{ ...secondaryBtnStyle, padding: "6px 16px", fontSize: 12 }}>
          Request Access
        </button>
      )}
    </div>
  );
}

function FolderList({ folders, onAdd }: { folders: string[]; onAdd: () => Promise<void> }) {
  return (
    <div>
      {folders.map((f, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 13, color: "#34d399" }}>{"\u2713"}</span>
          <span style={{ fontSize: 13, color: "#a1a1aa", fontFamily: "monospace" }}>{f}</span>
        </div>
      ))}
      <button onClick={onAdd} style={{ ...secondaryBtnStyle, marginTop: folders.length > 0 ? 8 : 0, padding: "6px 16px", fontSize: 12 }}>
        {folders.length > 0 ? "Add More" : "Select Folders"}
      </button>
    </div>
  );
}

function TailscaleDetail({ data }: { data: TailscaleCheckResult }) {
  if (!data.installed) {
    return (
      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 13, color: "#71717a", marginBottom: 16 }}>
          Tailscale is not installed. Install it to access EkamCore securely from your phone or other devices.
        </div>
        <a
          href="https://tailscale.com/download/mac"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#60a5fa", fontSize: 13, textDecoration: "underline" }}
        >
          Download Tailscale for macOS
        </a>
      </div>
    );
  }
  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <CheckRow label="Installed" pass detail="Yes" />
      <CheckRow label="Connected" pass={data.connected} detail={data.connected ? (data.hostname ?? "Yes") : "Not connected"} />
      {data.ip && <CheckRow label="Tailscale IP" pass detail={data.ip} />}
      {data.connected && data.ip && (
        <InfoBox bg="#14532d" border="#34d399">
          You can access EkamCore from anywhere via {data.ip}:443
        </InfoBox>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared UI components
// ---------------------------------------------------------------------------

function CheckRow({ label, pass, detail }: { label: string; pass: boolean; detail: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 14 }}>
      <span style={{ color: pass ? "#34d399" : "#f87171", width: 16 }}>{pass ? "\u2713" : "\u2717"}</span>
      <span style={{ color: "#e8e8ea", width: 120 }}>{label}</span>
      <span style={{ color: "#71717a" }}>{detail}</span>
    </div>
  );
}

function InfoBox({ bg, border, children }: { bg: string; border: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 8,
      padding: "12px 16px",
      fontSize: 14,
      color: "#e8e8ea",
      marginBottom: 16,
    }}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const railStyle: React.CSSProperties = {
  width: 220,
  background: "#18181b",
  borderRight: "1px solid #27272a",
  padding: "32px 0",
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "10px 24px",
  background: "#3b82f6",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 500,
  cursor: "pointer",
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: "10px 24px",
  background: "#27272a",
  color: "#e8e8ea",
  border: "1px solid #3f3f46",
  borderRadius: 8,
  fontSize: 14,
  cursor: "pointer",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 13,
  color: "#a1a1aa",
  marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  background: "#18181b",
  border: "1px solid #3f3f46",
  borderRadius: 8,
  color: "#e8e8ea",
  fontSize: 14,
  outline: "none",
  boxSizing: "border-box",
};

const sectionHeadingStyle: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  color: "#e8e8ea",
  marginBottom: 4,
};

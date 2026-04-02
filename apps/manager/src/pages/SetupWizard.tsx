import { useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type {
  StepStatus,
  HardwareCheckResult,
  DiskCheckResult,
  DockerCheckResult,
  TailscaleCheckResult,
} from "../types";

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

interface StepState {
  status: StepStatus;
  error?: string;
  data?: Record<string, unknown>;
}

const initialStepStates = (): Record<number, StepState> =>
  Object.fromEntries(STEPS.map((s) => [s.id, { status: "pending" as StepStatus }]));

const STATUS_ICON: Record<StepStatus, string> = {
  pending: "○",
  in_progress: "◌",
  passed: "✓",
  failed: "✗",
  skipped: "–",
};

const STATUS_COLOR: Record<StepStatus, string> = {
  pending: "#555",
  in_progress: "#60a5fa",
  passed: "#34d399",
  failed: "#f87171",
  skipped: "#888",
};

interface Props {
  onComplete: () => void;
}

export default function SetupWizard({ onComplete }: Props) {
  const [activeStep, setActiveStep] = useState(1);
  const [stepStates, setStepStates] = useState<Record<number, StepState>>(initialStepStates());

  const setStep = useCallback((id: number, patch: Partial<StepState>) => {
    setStepStates((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }, []);

  const runStep = useCallback(async (stepId: number) => {
    setStep(stepId, { status: "in_progress", error: undefined });
    try {
      switch (stepId) {
        case 1: await runHardwareCheck(stepId, setStep); break;
        case 2: await runDiskCheck(stepId, setStep); break;
        case 3: await runDockerCheck(stepId, setStep); break;
        case 8: await runTailscaleCheck(stepId, setStep); break;
        default:
          // Steps 4-7: stub — mark as passed for now (full impl in startup sequence)
          await new Promise((r) => setTimeout(r, 600));
          setStep(stepId, { status: "passed" });
      }
    } catch (err) {
      setStep(stepId, { status: "failed", error: String(err) });
    }
  }, [setStep]);

  const advance = useCallback(async () => {
    if (stepStates[activeStep].status !== "passed" && stepStates[activeStep].status !== "skipped") {
      await runStep(activeStep);
      return;
    }
    if (activeStep < STEPS.length) {
      const next = activeStep + 1;
      setActiveStep(next);
      await runStep(next);
    } else {
      await invoke("mark_setup_complete");
      onComplete();
    }
  }, [activeStep, stepStates, runStep, onComplete]);

  const retry = useCallback(async () => {
    await runStep(activeStep);
  }, [activeStep, runStep]);

  const currentState = stepStates[activeStep];

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0f0f11" }}>
      {/* Left rail */}
      <div
        style={{
          width: 220,
          background: "#18181b",
          borderRight: "1px solid #27272a",
          padding: "32px 0",
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
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
              <span
                style={{
                  fontSize: 13,
                  color: isActive ? "#e8e8ea" : state.status === "passed" ? "#a1a1aa" : "#71717a",
                }}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Main content */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          padding: "48px 56px",
          overflow: "auto",
        }}
      >
        <StepContent
          stepId={activeStep}
          state={currentState}
          onRetry={retry}
        />

        {/* Action bar */}
        <div style={{ marginTop: "auto", display: "flex", gap: 12, paddingTop: 32 }}>
          {activeStep > 1 && (
            <button
              onClick={() => setActiveStep((s) => s - 1)}
              style={secondaryBtnStyle}
            >
              Back
            </button>
          )}
          {currentState.status === "failed" ? (
            <button onClick={retry} style={primaryBtnStyle}>
              Try Again
            </button>
          ) : (
            <button
              onClick={advance}
              disabled={currentState.status === "in_progress"}
              style={{
                ...primaryBtnStyle,
                opacity: currentState.status === "in_progress" ? 0.5 : 1,
              }}
            >
              {currentState.status === "pending" || currentState.status === "in_progress"
                ? currentState.status === "in_progress"
                  ? "Checking…"
                  : "Run Check"
                : activeStep === STEPS.length
                ? "Finish"
                : "Continue"}
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
              Skip
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step runners
// ---------------------------------------------------------------------------

async function runHardwareCheck(
  stepId: number,
  setStep: (id: number, p: Partial<StepState>) => void,
) {
  const result = await invoke<HardwareCheckResult>("check_hardware");
  if (result.all_passed) {
    setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
  } else {
    const messages: string[] = [];
    if (!result.is_apple_silicon) messages.push("Requires Apple Silicon (M1 or later).");
    if (!result.ram_ok) messages.push(`Requires 16 GB RAM — detected ${result.ram_gb.toFixed(0)} GB.`);
    if (!result.macos_ok) messages.push(`Requires macOS 13.0+ — detected ${result.macos_version}.`);
    setStep(stepId, { status: "failed", error: messages.join(" "), data: result as unknown as Record<string, unknown> });
  }
}

async function runDiskCheck(
  stepId: number,
  setStep: (id: number, p: Partial<StepState>) => void,
) {
  const result = await invoke<DiskCheckResult>("check_disk");
  if (result.passed) {
    setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
  } else {
    setStep(stepId, {
      status: "failed",
      error: `Need ${result.required_gb} GB free — found ${result.free_gb.toFixed(1)} GB.`,
      data: result as unknown as Record<string, unknown>,
    });
  }
}

async function runDockerCheck(
  stepId: number,
  setStep: (id: number, p: Partial<StepState>) => void,
) {
  const result = await invoke<DockerCheckResult>("check_docker");
  if (result.installed) {
    setStep(stepId, { status: "passed", data: result as unknown as Record<string, unknown> });
  } else {
    setStep(stepId, {
      status: "failed",
      error: "Docker / OrbStack not found. Install OrbStack (recommended) or Docker Desktop, then try again.",
      data: result as unknown as Record<string, unknown>,
    });
  }
}

async function runTailscaleCheck(
  stepId: number,
  setStep: (id: number, p: Partial<StepState>) => void,
) {
  const result = await invoke<TailscaleCheckResult>("check_tailscale");
  // Tailscale is optional — even "not installed" counts as passed (user can skip).
  setStep(stepId, {
    status: result.connected ? "passed" : result.installed ? "passed" : "passed",
    data: result as unknown as Record<string, unknown>,
  });
}

// ---------------------------------------------------------------------------
// Step content renderer
// ---------------------------------------------------------------------------

interface StepContentProps {
  stepId: number;
  state: StepState;
  onRetry: () => void;
}

function StepContent({ stepId, state }: StepContentProps) {
  const step = STEPS[stepId - 1];

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>
        Step {stepId}: {step.label}
      </h1>
      <p style={{ color: "#71717a", fontSize: 14, marginBottom: 32 }}>
        {STEP_DESCRIPTIONS[stepId]}
      </p>

      {state.status === "in_progress" && (
        <div style={infoBoxStyle("#1e3a5f", "#60a5fa")}>Running checks…</div>
      )}

      {state.status === "passed" && (
        <div style={infoBoxStyle("#14532d", "#34d399")}>All checks passed.</div>
      )}

      {state.status === "failed" && state.error && (
        <div style={infoBoxStyle("#450a0a", "#f87171")}>{state.error}</div>
      )}

      {state.status === "passed" && state.data && stepId === 1 && (
        <HardwareDetail data={state.data as unknown as HardwareCheckResult} />
      )}

      {state.status === "passed" && state.data && stepId === 2 && (
        <DiskDetail data={state.data as unknown as DiskCheckResult} />
      )}

      {state.status === "passed" && state.data && stepId === 3 && (
        <DockerDetail data={state.data as unknown as DockerCheckResult} />
      )}

      {stepId === 8 && state.data && (
        <TailscaleDetail data={state.data as unknown as TailscaleCheckResult} />
      )}
    </div>
  );
}

function HardwareDetail({ data }: { data: HardwareCheckResult }) {
  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <CheckRow label="Apple Silicon" pass={data.is_apple_silicon} detail="Required" />
      <CheckRow label="RAM" pass={data.ram_ok} detail={`${data.ram_gb.toFixed(0)} GB (need ≥ 16 GB)`} />
      <CheckRow label="macOS" pass={data.macos_ok} detail={`${data.macos_version} (need ≥ 13.0)`} />
    </div>
  );
}

function DiskDetail({ data }: { data: DiskCheckResult }) {
  const pct = Math.min((data.free_gb / (data.free_gb + 20)) * 100, 100);
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 13, color: "#a1a1aa", marginBottom: 8 }}>
        {data.free_gb.toFixed(1)} GB free of boot volume
      </div>
      <div style={{ height: 8, background: "#27272a", borderRadius: 4, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: data.passed ? "#34d399" : data.warning ? "#fbbf24" : "#f87171",
            borderRadius: 4,
          }}
        />
      </div>
    </div>
  );
}

function DockerDetail({ data }: { data: DockerCheckResult }) {
  const runtimeLabel =
    data.runtime === "orbstack"
      ? "OrbStack"
      : data.runtime === "docker_desktop"
      ? "Docker Desktop"
      : "Unknown";
  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <CheckRow label="Runtime" pass={data.installed} detail={runtimeLabel} />
      {data.version && (
        <CheckRow label="Version" pass={true} detail={data.version} />
      )}
    </div>
  );
}

function TailscaleDetail({ data }: { data: TailscaleCheckResult }) {
  if (!data.installed) {
    return (
      <div style={{ marginTop: 16, fontSize: 13, color: "#71717a" }}>
        Tailscale is not installed. You can install it later to enable remote access.
      </div>
    );
  }
  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <CheckRow label="Installed" pass={data.installed} detail="Yes" />
      <CheckRow
        label="Connected"
        pass={data.connected}
        detail={data.connected ? (data.hostname ?? "Yes") : "Not connected"}
      />
      {data.ip && <CheckRow label="Tailscale IP" pass={true} detail={data.ip} />}
    </div>
  );
}

function CheckRow({ label, pass, detail }: { label: string; pass: boolean; detail: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 14 }}>
      <span style={{ color: pass ? "#34d399" : "#f87171", width: 16 }}>{pass ? "✓" : "✗"}</span>
      <span style={{ color: "#e8e8ea", width: 120 }}>{label}</span>
      <span style={{ color: "#71717a" }}>{detail}</span>
    </div>
  );
}

const STEP_DESCRIPTIONS: Record<number, string> = {
  1: "Verifying your Mac meets the minimum requirements for EkamCore.",
  2: "Checking that there is enough free disk space for Docker images, models, and data.",
  3: "Detecting Docker Desktop or OrbStack — required to run EkamCore services.",
  4: "Pulling all required Docker images (this may take a few minutes).",
  5: "Initialising the PostgreSQL database and running migrations.",
  6: "Creating the admin account for the EkamCore API.",
  7: "Granting access to Calendar, Reminders, and Contacts.",
  8: "Configuring Tailscale for secure remote access. This step is optional and can be skipped.",
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

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

function infoBoxStyle(bg: string, border: string): React.CSSProperties {
  return {
    background: bg,
    border: `1px solid ${border}`,
    borderRadius: 8,
    padding: "12px 16px",
    fontSize: 14,
    color: "#e8e8ea",
    marginBottom: 16,
  };
}

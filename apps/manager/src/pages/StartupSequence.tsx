/**
 * S03-006 — Startup Sequence
 *
 * Displays real-time progress of the 15-step service startup.
 * Listens for "startup://progress" events emitted by startup.rs.
 * Calls onReady() when step 15 reports "ok".
 * Calls onError() when any step reports "failed".
 */

import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StepStatus = "pending" | "running" | "ok" | "failed" | "skipped";

interface StepState {
  status: StepStatus;
  message?: string;
}

interface StartupProgressEvent {
  step: number;
  label: string;
  status: "running" | "ok" | "failed" | "skipped";
  message: string | null;
}

const ALL_STEPS: { id: number; label: string }[] = [
  { id: 1,  label: "Hardware check" },
  { id: 2,  label: "Disk check" },
  { id: 3,  label: "Docker check" },
  { id: 4,  label: "Verify images" },
  { id: 5,  label: "Create network" },
  { id: 6,  label: "Start PostgreSQL" },
  { id: 7,  label: "Run migrations" },
  { id: 8,  label: "Start Redis" },
  { id: 9,  label: "Start Qdrant" },
  { id: 10, label: "Start Ollama" },
  { id: 11, label: "Check models" },
  { id: 12, label: "Start API" },
  { id: 13, label: "Start Workers" },
  { id: 14, label: "Start Proxy" },
  { id: 15, label: "System ready" },
];

const STATUS_ICON: Record<StepStatus, string> = {
  pending:    "○",
  running:    "◌",
  ok:         "✓",
  failed:     "✗",
  skipped:    "–",
};

const STATUS_COLOR: Record<StepStatus, string> = {
  pending:    "#555",
  running:    "#60a5fa",
  ok:         "#34d399",
  failed:     "#f87171",
  skipped:    "#888",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  onReady: () => void;
}

export default function StartupSequence({ onReady }: Props) {
  const [steps, setSteps] = useState<Record<number, StepState>>(
    () => Object.fromEntries(ALL_STEPS.map((s) => [s.id, { status: "pending" as StepStatus }])),
  );
  const [failedStep, setFailedStep] = useState<number | null>(null);
  const [failedMsg, setFailedMsg] = useState<string>("");
  const unlistenRef = useRef<UnlistenFn | null>(null);

  const runStartup = () => {
    setFailedStep(null);
    setFailedMsg("");
    // Reset all steps to pending
    setSteps(Object.fromEntries(ALL_STEPS.map((s) => [s.id, { status: "pending" as StepStatus }])));

    invoke("run_startup").catch((err: unknown) => {
      // The error surface is handled via events; this catch handles unexpected Tauri errors.
      console.error("run_startup error:", err);
    });
  };

  useEffect(() => {
    let mounted = true;

    listen<StartupProgressEvent>("startup://progress", (event) => {
      if (!mounted) return;
      const { step, status, message } = event.payload;

      setSteps((prev) => ({
        ...prev,
        [step]: { status, message: message ?? undefined },
      }));

      if (status === "failed") {
        setFailedStep(step);
        setFailedMsg(message ?? "Unknown error");
      }

      if (step === 15 && status === "ok") {
        // Brief pause so the user sees step 15 go green before transitioning.
        setTimeout(onReady, 800);
      }
    }).then((fn) => {
      if (mounted) unlistenRef.current = fn;
    });

    // Auto-start on mount
    runStartup();

    return () => {
      mounted = false;
      unlistenRef.current?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeStep = ALL_STEPS.find((s) => steps[s.id].status === "running")?.id ?? null;
  const completedCount = ALL_STEPS.filter((s) => steps[s.id].status === "ok").length;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        background: "#0f0f11",
        padding: "48px 32px",
        boxSizing: "border-box",
      }}
    >
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "#e8e8ea", margin: 0 }}>
          Starting EkamCore
        </h1>
        <p style={{ color: "#71717a", fontSize: 13, marginTop: 8 }}>
          {failedStep
            ? "A service failed to start."
            : completedCount === ALL_STEPS.length
            ? "All services ready."
            : `Step ${completedCount + (activeStep ? 1 : 0)} of ${ALL_STEPS.length}`}
        </p>
      </div>

      {/* Step list */}
      <div
        style={{
          width: "100%",
          maxWidth: 480,
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        {ALL_STEPS.map((s) => {
          const state = steps[s.id];
          return (
            <div
              key={s.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "8px 14px",
                borderRadius: 6,
                background: state.status === "running" ? "#1c2a3a" : "transparent",
                transition: "background 0.2s",
              }}
            >
              <span
                style={{
                  color: STATUS_COLOR[state.status],
                  fontSize: 13,
                  width: 16,
                  textAlign: "center",
                  flexShrink: 0,
                  animation: state.status === "running" ? "spin 1.2s linear infinite" : undefined,
                }}
              >
                {STATUS_ICON[state.status]}
              </span>
              <span
                style={{
                  fontSize: 13,
                  color:
                    state.status === "ok"
                      ? "#a1a1aa"
                      : state.status === "running"
                      ? "#e8e8ea"
                      : state.status === "failed"
                      ? "#f87171"
                      : "#555",
                  flex: 1,
                }}
              >
                {s.label}
              </span>
              {state.message && state.status === "ok" && (
                <span style={{ fontSize: 11, color: "#555" }}>{state.message}</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div
        style={{
          width: "100%",
          maxWidth: 480,
          height: 3,
          background: "#27272a",
          borderRadius: 2,
          marginTop: 24,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${(completedCount / ALL_STEPS.length) * 100}%`,
            background: failedStep ? "#f87171" : "#3b82f6",
            borderRadius: 2,
            transition: "width 0.4s ease",
          }}
        />
      </div>

      {/* Error detail + retry */}
      {failedStep && (
        <div
          style={{
            marginTop: 24,
            width: "100%",
            maxWidth: 480,
            background: "#450a0a",
            border: "1px solid #f87171",
            borderRadius: 8,
            padding: "12px 16px",
          }}
        >
          <div style={{ color: "#f87171", fontSize: 13, fontWeight: 500, marginBottom: 4 }}>
            Step {failedStep} failed
          </div>
          <div style={{ color: "#e8e8ea", fontSize: 13, marginBottom: 16 }}>{failedMsg}</div>
          <button
            onClick={runStartup}
            style={{
              padding: "8px 20px",
              background: "#3b82f6",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

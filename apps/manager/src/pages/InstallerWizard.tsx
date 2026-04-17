/**
 * InstallerWizard — one-click setup that handles everything (S16-014).
 *
 * Runs the bundled install.sh script through phases:
 * 1. Check system dependencies
 * 2. Install Docker (OrbStack)
 * 3. Install Ollama
 * 4. Download EkamCore
 * 5. Pull/build Docker images
 * 6. Start services
 * 7. Download AI models
 * 8. Verify everything works
 */

import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

interface InstallerProgress {
  phase: string;
  status: string;
  message: string;
}

const PHASES = [
  { id: "install-docker", label: "Docker Runtime", description: "Installing OrbStack for container management" },
  { id: "install-ollama", label: "AI Engine", description: "Installing Ollama for local AI inference" },
  { id: "clone-repo", label: "Download EkamCore", description: "Downloading EkamCore from GitHub" },
  { id: "pull-images", label: "Container Images", description: "Building and pulling Docker images" },
  { id: "start-stack", label: "Start Services", description: "Starting all 10 services" },
  { id: "pull-models", label: "AI Models", description: "Downloading AI models (nomic-embed-text, phi3)" },
  { id: "verify", label: "Verify", description: "Checking everything works" },
];

interface Props {
  onComplete: () => void;
}

export default function InstallerWizard({ onComplete }: Props) {
  const [isRunning, setIsRunning] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [phaseStatuses, setPhaseStatuses] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deps, setDeps] = useState<Record<string, boolean> | null>(null);
  const unlistenRef = useRef<UnlistenFn | null>(null);

  // Check deps on mount
  useEffect(() => {
    invoke<Record<string, boolean>>("check_system_deps")
      .then(setDeps)
      .catch(() => {});
  }, []);

  // Listen for progress events
  useEffect(() => {
    listen<InstallerProgress>("installer-progress", (e) => {
      const { phase, status, message } = e.payload;
      setCurrentPhase(phase);
      setPhaseStatuses((prev) => ({ ...prev, [phase]: status }));
      if (message) {
        setMessages((prev) => [...prev.slice(-20), message]);
      }
    }).then((fn) => { unlistenRef.current = fn; });

    return () => { unlistenRef.current?.(); };
  }, []);

  const handleInstall = async () => {
    setIsRunning(true);
    setError(null);
    setMessages([]);
    setPhaseStatuses({});

    try {
      await invoke<string>("run_installer", { phase: "full" });
      // Mark setup as complete
      await invoke("mark_setup_complete");
      onComplete();
    } catch (err) {
      setError(String(err));
      setIsRunning(false);
    }
  };

  const allDepsPresent = deps?.docker_running && deps?.ollama_running && deps?.api_healthy;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#0f0f11", color: "#e8e8ea" }}>
      {/* Header */}
      <div style={{ padding: "48px 56px 24px", textAlign: "center" }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Welcome to EkamCore</h1>
        <p style={{ color: "#71717a", fontSize: 15, marginTop: 8 }}>
          Your private, local-first life assistant. Everything runs on your Mac.
        </p>
      </div>

      {/* Dependency status (pre-install) */}
      {!isRunning && deps && !allDepsPresent && (
        <div style={{ padding: "0 56px 24px" }}>
          <div style={{
            background: "#18181b",
            border: "1px solid #27272a",
            borderRadius: 12,
            padding: 20,
          }}>
            <h3 style={{ fontSize: 15, fontWeight: 600, margin: "0 0 12px 0" }}>System Check</h3>
            <DepRow label="Docker" ok={deps.docker_running} detail={deps.docker_running ? "Running" : "Will be installed"} />
            <DepRow label="Ollama" ok={deps.ollama_running} detail={deps.ollama_running ? "Running" : "Will be installed"} />
            <DepRow label="EkamCore" ok={deps.repo_exists} detail={deps.repo_exists ? "Downloaded" : "Will be downloaded"} />
            <DepRow label="API" ok={deps.api_healthy} detail={deps.api_healthy ? "Healthy" : "Will be started"} />
          </div>
        </div>
      )}

      {/* Already running — skip install */}
      {!isRunning && allDepsPresent && (
        <div style={{ padding: "0 56px 24px", textAlign: "center" }}>
          <div style={{
            background: "#14532d",
            border: "1px solid #34d399",
            borderRadius: 12,
            padding: 20,
            fontSize: 15,
          }}>
            EkamCore is already running! Click Continue to open the dashboard.
          </div>
        </div>
      )}

      {/* Progress phases */}
      {isRunning && (
        <div style={{ flex: 1, padding: "0 56px", overflow: "auto" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {PHASES.map((phase) => {
              const status = phaseStatuses[phase.id];
              const isCurrent = currentPhase === phase.id;
              const isDone = status === "done";
              const isFailed = status === "failed";

              return (
                <div key={phase.id} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 16px",
                  background: isCurrent ? "#1c2a3a" : "#18181b",
                  border: `1px solid ${isFailed ? "#7f1d1d" : isCurrent ? "#3b82f6" : "#27272a"}`,
                  borderRadius: 10,
                }}>
                  <span style={{
                    fontSize: 16,
                    width: 24,
                    textAlign: "center",
                    color: isDone ? "#34d399" : isFailed ? "#f87171" : isCurrent ? "#60a5fa" : "#555",
                  }}>
                    {isDone ? "✓" : isFailed ? "✗" : isCurrent ? "◌" : "○"}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontSize: 14,
                      fontWeight: 500,
                      color: isDone ? "#a1a1aa" : isCurrent ? "#e8e8ea" : "#555",
                    }}>
                      {phase.label}
                    </div>
                    <div style={{ fontSize: 12, color: "#555", marginTop: 2 }}>
                      {phase.description}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Live log */}
          {messages.length > 0 && (
            <div style={{
              marginTop: 16,
              background: "#0a0a0b",
              borderRadius: 8,
              padding: 12,
              maxHeight: 120,
              overflow: "auto",
              fontFamily: "monospace",
              fontSize: 11,
              color: "#71717a",
              lineHeight: 1.6,
            }}>
              {messages.map((m, i) => <div key={i}>{m}</div>)}
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ padding: "0 56px 16px" }}>
          <div style={{
            background: "#450a0a",
            border: "1px solid #f87171",
            borderRadius: 8,
            padding: "12px 16px",
            fontSize: 13,
            color: "#e8e8ea",
          }}>
            {error}
          </div>
        </div>
      )}

      {/* Action bar */}
      <div style={{ padding: "16px 56px 48px", textAlign: "center" }}>
        {!isRunning && !allDepsPresent && (
          <>
            <button
              onClick={handleInstall}
              style={{
                padding: "14px 48px",
                background: "#3b82f6",
                color: "#fff",
                border: "none",
                borderRadius: 10,
                fontSize: 16,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Install EkamCore
            </button>
            <p style={{ color: "#555", fontSize: 12, marginTop: 12 }}>
              This will install Docker, Ollama, and download ~4 GB of data.
              <br />
              Requires an internet connection. Takes 5–15 minutes.
            </p>
          </>
        )}
        {!isRunning && allDepsPresent && (
          <button
            onClick={async () => {
              await invoke("mark_setup_complete");
              onComplete();
            }}
            style={{
              padding: "14px 48px",
              background: "#22c55e",
              color: "#fff",
              border: "none",
              borderRadius: 10,
              fontSize: 16,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Continue to Dashboard
          </button>
        )}
        {!isRunning && error && (
          <button
            onClick={handleInstall}
            style={{
              padding: "14px 48px",
              background: "#f59e0b",
              color: "#000",
              border: "none",
              borderRadius: 10,
              fontSize: 16,
              fontWeight: 600,
              cursor: "pointer",
              marginTop: 12,
            }}
          >
            Retry
          </button>
        )}
        {isRunning && (
          <p style={{ color: "#71717a", fontSize: 13 }}>
            Installing... This may take several minutes. Please don't close the app.
          </p>
        )}
      </div>
    </div>
  );
}

function DepRow({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <span style={{ color: ok ? "#34d399" : "#fbbf24", fontSize: 14 }}>
        {ok ? "✓" : "○"}
      </span>
      <span style={{ fontSize: 14, color: "#e8e8ea", width: 100 }}>{label}</span>
      <span style={{ fontSize: 13, color: ok ? "#71717a" : "#fbbf24" }}>{detail}</span>
    </div>
  );
}

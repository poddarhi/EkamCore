/**
 * S15-004 — Diagnostics Page
 *
 * Export diagnostics bundle (works offline), view service logs,
 * copy system info to clipboard. Per FS-123: no personal data included.
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { DiagnosticsResult, DiagnosticsProgressEvent } from "../types";

const SERVICES = [
  "ekamcore-postgres",
  "ekamcore-redis",
  "ekamcore-qdrant",
  "ekamcore-api",
  "ekamcore-workers",
  "ekamcore-web",
  "ekamcore-proxy",
  "ekamcore-paperless",
];

const BUNDLE_CONTENTS = [
  "system_info.json — macOS version, hardware, RAM, disk, CPU",
  "docker_info.json — Docker version, running containers, resource usage",
  "container_logs/ — Last 500 lines of each container's logs",
  "health_check.json — Service reachability results",
  "setup_state.json — Setup wizard state",
  "config_sanitized.yml — docker-compose.yml with passwords redacted",
  "disk_usage.json — Disk and Docker volume usage",
  "network_info.json — Docker networks, ports, Tailscale status",
];

export default function Diagnostics() {
  // Export state
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<DiagnosticsResult | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportPhases, setExportPhases] = useState<Record<string, string>>({});

  // Log viewer state
  const [selectedService, setSelectedService] = useState(SERVICES[0]);
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [logSearch, setLogSearch] = useState("");

  // System info
  const [copied, setCopied] = useState(false);

  const unlistenProgress = useRef<UnlistenFn | null>(null);

  useEffect(() => {
    listen<DiagnosticsProgressEvent>("diagnostics-progress", (e) => {
      setExportPhases((prev) => ({ ...prev, [e.payload.phase]: e.payload.status }));
    }).then((fn) => { unlistenProgress.current = fn; });

    return () => { unlistenProgress.current?.(); };
  }, []);

  // ── Export ────────────────────────────────────────────────────────────────

  const handleExport = async () => {
    setExporting(true);
    setExportResult(null);
    setExportError(null);
    setExportPhases({});
    try {
      const result = await invoke<DiagnosticsResult>("generate_diagnostics");
      setExportResult(result);
    } catch (e) {
      setExportError(String(e));
    } finally {
      setExporting(false);
    }
  };

  // ── Copy system info ──────────────────────────────────────────────────────

  const handleCopySystemInfo = async () => {
    try {
      const text = await invoke<string>("get_system_info_text");
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error("copy failed:", e);
    }
  };

  // ── Log viewer ────────────────────────────────────────────────────────────

  const fetchLogs = useCallback(async (service: string) => {
    setLogsLoading(true);
    try {
      const result = await invoke<string>("get_service_logs", { service, lines: 200 });
      setLogs(result);
    } catch (e) {
      setLogs(`Error: ${e}`);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs(selectedService);
  }, [selectedService, fetchLogs]);

  const filteredLogs = logSearch
    ? logs.split("\n").filter((line) => line.toLowerCase().includes(logSearch.toLowerCase())).join("\n")
    : logs;

  return (
    <div style={{ minHeight: "100vh", background: "#0f0f11", color: "#e8e8ea", padding: "32px 40px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4 }}>Diagnostics</h1>
      <p style={{ color: "#71717a", fontSize: 13, marginBottom: 32 }}>
        Export a diagnostics bundle for troubleshooting or view service logs.
      </p>

      {/* Export section */}
      <div style={{ ...cardStyle, marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={sectionHeading}>Export Diagnostics Bundle</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleCopySystemInfo}
              style={secondaryBtnStyle}
            >
              {copied ? "Copied!" : "Copy System Info"}
            </button>
            <button
              onClick={handleExport}
              disabled={exporting}
              style={{ ...primaryBtnStyle, opacity: exporting ? 0.5 : 1 }}
            >
              {exporting ? "Collecting..." : "Export Diagnostics"}
            </button>
          </div>
        </div>

        <div style={{
          background: "#14532d",
          border: "1px solid #22c55e",
          borderRadius: 8,
          padding: "10px 14px",
          fontSize: 12,
          color: "#bbf7d0",
          marginBottom: 16,
        }}>
          No personal data is included — no query logs, file names, person names, embeddings, or database content.
        </div>

        {/* Progress phases */}
        {exporting && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
            {PHASE_LABELS.map(([key, label]) => {
              const status = exportPhases[key];
              const isDone = status === "done" || (exportPhases.complete === "done");
              const isActive = status === "collecting" && !exportPhases.complete;
              return (
                <div key={key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ color: isDone ? "#34d399" : isActive ? "#60a5fa" : "#555", fontSize: 13, width: 16 }}>
                    {isDone ? "\u2713" : isActive ? "\u25CC" : "\u25CB"}
                  </span>
                  <span style={{ fontSize: 12, color: isDone ? "#a1a1aa" : isActive ? "#e8e8ea" : "#555" }}>
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Result */}
        {exportResult && (
          <div style={{ background: "#18181b", borderRadius: 8, padding: 14, border: "1px solid #27272a" }}>
            <div style={{ fontSize: 13, color: "#34d399", marginBottom: 8 }}>
              Bundle exported successfully ({(exportResult.size_bytes / 1024).toFixed(0)} KB)
            </div>
            <div style={{ fontSize: 12, color: "#a1a1aa", fontFamily: "monospace", wordBreak: "break-all" }}>
              {exportResult.path}
            </div>
            <div style={{ fontSize: 11, color: "#555", marginTop: 8 }}>
              {exportResult.files_included.length} files included
            </div>
          </div>
        )}

        {exportError && (
          <div style={{ background: "#450a0a", border: "1px solid #f87171", borderRadius: 8, padding: 12, fontSize: 13, color: "#e8e8ea" }}>
            {exportError}
          </div>
        )}

        {/* What's included */}
        <details style={{ marginTop: 16 }}>
          <summary style={{ fontSize: 12, color: "#71717a", cursor: "pointer" }}>
            What's included in the bundle
          </summary>
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            {BUNDLE_CONTENTS.map((item) => (
              <li key={item} style={{ fontSize: 12, color: "#555", marginBottom: 4 }}>{item}</li>
            ))}
          </ul>
        </details>
      </div>

      {/* Log viewer */}
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={sectionHeading}>Service Logs</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
              style={selectStyle}
            >
              {SERVICES.map((s) => (
                <option key={s} value={s}>{s.replace("ekamcore-", "")}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Search logs..."
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
              style={searchInputStyle}
            />
            <button onClick={() => fetchLogs(selectedService)} style={secondaryBtnStyle}>
              Refresh
            </button>
          </div>
        </div>

        <div style={{
          background: "#0f0f11",
          borderRadius: 8,
          padding: 14,
          height: 350,
          overflow: "auto",
          fontFamily: "monospace",
          fontSize: 11,
          color: "#a1a1aa",
          whiteSpace: "pre-wrap",
          lineHeight: 1.6,
          border: "1px solid #1c1c1f",
        }}>
          {logsLoading ? "Loading logs..." : (filteredLogs || "No logs available.")}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PHASE_LABELS: [string, string][] = [
  ["system_info", "System information"],
  ["docker_info", "Docker state"],
  ["container_logs", "Container logs (8 services)"],
  ["health_checks", "Health checks"],
  ["setup_state", "Setup state"],
  ["config_sanitized", "Sanitized configuration"],
  ["disk_usage", "Disk usage"],
  ["network_info", "Network information"],
];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const cardStyle: React.CSSProperties = {
  background: "#18181b",
  border: "1px solid #27272a",
  borderRadius: 10,
  padding: 20,
};

const sectionHeading: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  color: "#e8e8ea",
  margin: 0,
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "8px 18px",
  background: "#3b82f6",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 500,
  cursor: "pointer",
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: "8px 14px",
  background: "#27272a",
  color: "#e8e8ea",
  border: "1px solid #3f3f46",
  borderRadius: 8,
  fontSize: 12,
  cursor: "pointer",
};

const selectStyle: React.CSSProperties = {
  padding: "6px 12px",
  background: "#27272a",
  color: "#e8e8ea",
  border: "1px solid #3f3f46",
  borderRadius: 6,
  fontSize: 12,
  outline: "none",
};

const searchInputStyle: React.CSSProperties = {
  padding: "6px 12px",
  background: "#0f0f11",
  color: "#e8e8ea",
  border: "1px solid #3f3f46",
  borderRadius: 6,
  fontSize: 12,
  outline: "none",
  width: 150,
};

/**
 * S15-004 — Storage Page
 *
 * Mirrors web admin StoragePage (S09-004) with manager-specific features.
 * Shows storage breakdown by category, disk usage, and cleanup actions.
 */

import { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

interface StorageData {
  docker_images: string;
  docker_containers: string;
  docker_volumes: string;
  ollama_models_mb: number;
  disk_free_gb: number;
  disk_warning: boolean;
}

export default function Storage() {
  const [data, setData] = useState<StorageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await invoke<StorageData>("get_storage_breakdown");
      setData(result);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCleanCache = async () => {
    if (!confirm("This will remove all unused Docker images, containers, and build cache. Continue?")) return;
    setCleaning(true);
    setCleanResult(null);
    try {
      const result = await invoke<string>("clean_docker_cache");
      setCleanResult(result);
      await fetchData();
    } catch (e) {
      setCleanResult(`Error: ${e}`);
    } finally {
      setCleaning(false);
    }
  };

  if (loading) {
    return <PageShell><span style={{ color: "#555", fontSize: 13 }}>Loading storage data...</span></PageShell>;
  }

  return (
    <PageShell>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, color: "#e8e8ea" }}>Storage</h1>
          <p style={{ color: "#71717a", fontSize: 13, marginTop: 4 }}>
            Disk usage breakdown and cleanup tools
          </p>
        </div>
        <button onClick={fetchData} style={btnStyle("#71717a")}>Refresh</button>
      </div>

      {error && <AlertBanner type="warning" message={error} />}
      {data?.disk_warning && (
        <AlertBanner type="critical" message={`Disk space is low: ${data.disk_free_gb.toFixed(1)} GB free. EkamCore requires at least 30 GB.`} />
      )}

      {data && (
        <>
          {/* Disk overview card */}
          <div style={{ ...cardStyle, marginBottom: 24 }}>
            <h2 style={sectionHeadingStyle}>Boot Volume</h2>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 32, fontWeight: 700, color: data.disk_warning ? "#fbbf24" : "#34d399" }}>
                {data.disk_free_gb.toFixed(0)}
              </span>
              <span style={{ fontSize: 14, color: "#71717a" }}>GB free</span>
            </div>
            <div style={{ height: 8, background: "#27272a", borderRadius: 4, overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${Math.min((data.disk_free_gb / 500) * 100, 100)}%`,
                background: data.disk_warning ? "#fbbf24" : "#34d399",
                borderRadius: 4,
              }} />
            </div>
          </div>

          {/* Breakdown grid */}
          <h2 style={{ ...sectionHeadingStyle, marginBottom: 16 }}>Docker Usage</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 24 }}>
            <BreakdownCard label="Images" value={data.docker_images} icon="I" color="#3b82f6" />
            <BreakdownCard label="Containers" value={data.docker_containers} icon="C" color="#8b5cf6" />
            <BreakdownCard label="Volumes" value={data.docker_volumes} icon="V" color="#06b6d4" />
          </div>

          {/* Models */}
          <h2 style={{ ...sectionHeadingStyle, marginBottom: 16 }}>AI Models</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12, marginBottom: 32 }}>
            <BreakdownCard
              label="Ollama Models"
              value={data.ollama_models_mb > 1024 ? `${(data.ollama_models_mb / 1024).toFixed(1)} GB` : `${data.ollama_models_mb.toFixed(0)} MB`}
              icon="O"
              color="#f59e0b"
            />
            <BreakdownCard label="InsightFace Models" value="~120 MB" icon="F" color="#ec4899" />
          </div>

          {/* Cleanup actions */}
          <h2 style={{ ...sectionHeadingStyle, marginBottom: 16 }}>Cleanup</h2>
          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={handleCleanCache}
              disabled={cleaning}
              style={{ ...btnStyle("#ef4444"), opacity: cleaning ? 0.5 : 1 }}
            >
              {cleaning ? "Cleaning..." : "Clean Docker Cache"}
            </button>
          </div>
          {cleanResult && (
            <div style={{
              marginTop: 12,
              background: "#18181b",
              border: "1px solid #27272a",
              borderRadius: 8,
              padding: 12,
              fontFamily: "monospace",
              fontSize: 11,
              color: "#a1a1aa",
              whiteSpace: "pre-wrap",
              maxHeight: 200,
              overflow: "auto",
            }}>
              {cleanResult}
            </div>
          )}
        </>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BreakdownCard({ label, value, icon, color }: { label: string; value: string; icon: string; color: string }) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 28,
          height: 28,
          borderRadius: 6,
          background: `${color}20`,
          color,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 13,
          fontWeight: 700,
        }}>
          {icon}
        </div>
        <span style={{ fontSize: 13, color: "#a1a1aa" }}>{label}</span>
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: "#e8e8ea" }}>{value}</div>
    </div>
  );
}

function AlertBanner({ type, message }: { type: "critical" | "warning"; message: string }) {
  const bg = type === "critical" ? "#450a0a" : "#451a03";
  const border = type === "critical" ? "#f87171" : "#fbbf24";
  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 8,
      padding: "10px 16px",
      marginBottom: 16,
      fontSize: 13,
      color: "#e8e8ea",
    }}>
      {message}
    </div>
  );
}

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", background: "#0f0f11", color: "#e8e8ea", padding: "32px 40px" }}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const cardStyle: React.CSSProperties = {
  background: "#18181b",
  border: "1px solid #27272a",
  borderRadius: 10,
  padding: 16,
};

const sectionHeadingStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  color: "#a1a1aa",
  margin: 0,
};

function btnStyle(bg: string): React.CSSProperties {
  return {
    padding: "8px 18px",
    background: bg,
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  };
}

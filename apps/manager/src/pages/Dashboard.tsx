/**
 * S15-003 — Manager Dashboard
 *
 * Real-time service health tiles, KPI cards, disk usage, alert banners,
 * and service controls. Subscribes to watchdog events for live updates.
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  HealthState,
  ServiceHealthInfo,
  DashboardData,
  HealthUpdateEvent,
  ServiceCriticalEvent,
  ServiceUnstableEvent,
} from "../types";

// ---------------------------------------------------------------------------
// Service display config
// ---------------------------------------------------------------------------

const SERVICE_LABELS: Record<string, string> = {
  "ekamcore-postgres": "PostgreSQL",
  "ekamcore-redis": "Redis",
  "ekamcore-qdrant": "Qdrant",
  "ekamcore-ollama": "Ollama",
  "ekamcore-paperless": "PaperlessNGX",
  "ekamcore-api": "API",
  "ekamcore-workers": "Workers",
  "ekamcore-web": "Web",
  "ekamcore-proxy": "Proxy",
  "ekamcore-migrate": "Migrate",
};

function displayName(name: string): string {
  return SERVICE_LABELS[name] ?? name.replace("ekamcore-", "");
}

// ---------------------------------------------------------------------------
// Health state colors
// ---------------------------------------------------------------------------

const STATE_DOT: Record<HealthState, string> = {
  healthy: "#34d399",
  unhealthy: "#f87171",
  starting: "#fbbf24",
  not_running: "#71717a",
};

const STATE_LABEL: Record<HealthState, string> = {
  healthy: "Healthy",
  unhealthy: "Unhealthy",
  starting: "Starting",
  not_running: "Stopped",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [services, setServices] = useState<ServiceHealthInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Alerts
  const [criticalAlerts, setCriticalAlerts] = useState<ServiceCriticalEvent[]>([]);
  const [unstableAlerts, setUnstableAlerts] = useState<ServiceUnstableEvent[]>([]);

  // Expanded tile
  const [expandedService, setExpandedService] = useState<string | null>(null);
  const [serviceLogs, setServiceLogs] = useState<string>("");
  const [logsLoading, setLogsLoading] = useState(false);

  // Action state
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const unlistenHealth = useRef<UnlistenFn | null>(null);
  const unlistenCritical = useRef<UnlistenFn | null>(null);
  const unlistenUnstable = useRef<UnlistenFn | null>(null);

  // ── Fetch dashboard data ────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    try {
      const d = await invoke<DashboardData>("get_dashboard_data");
      setData(d);
      setServices(d.services);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Subscribe to watchdog events ────────────────────────────────────────

  useEffect(() => {
    fetchData();

    listen<HealthUpdateEvent>("health-update", (e) => {
      setServices(e.payload.services);
    }).then((fn) => { unlistenHealth.current = fn; });

    listen<ServiceCriticalEvent>("service-critical", (e) => {
      setCriticalAlerts((prev) => {
        // Deduplicate by service name
        const existing = prev.filter((a) => a.service !== e.payload.service);
        return [...existing, e.payload];
      });
    }).then((fn) => { unlistenCritical.current = fn; });

    listen<ServiceUnstableEvent>("service-unstable", (e) => {
      setUnstableAlerts((prev) => {
        const existing = prev.filter((a) => a.service !== e.payload.service);
        return [...existing, e.payload];
      });
    }).then((fn) => { unlistenUnstable.current = fn; });

    // Periodic refresh for KPI data (watchdog handles service health)
    const interval = setInterval(fetchData, 60_000);

    return () => {
      unlistenHealth.current?.();
      unlistenCritical.current?.();
      unlistenUnstable.current?.();
      clearInterval(interval);
    };
  }, [fetchData]);

  // ── Service actions ─────────────────────────────────────────────────────

  const handleRestart = async (service: string) => {
    setActionInProgress(service);
    try {
      await invoke("force_restart_service", { service });
      // Clear critical alert for this service
      setCriticalAlerts((prev) => prev.filter((a) => a.service !== service));
    } catch (e) {
      console.error("restart failed:", e);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleViewLogs = async (service: string) => {
    setLogsLoading(true);
    try {
      const logs = await invoke<string>("get_service_logs", { service, lines: 100 });
      setServiceLogs(logs);
    } catch (e) {
      setServiceLogs(`Error fetching logs: ${e}`);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleStartAll = async () => {
    setActionInProgress("start_all");
    try {
      await invoke("start_all_services");
      await fetchData();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleStopAll = async () => {
    setActionInProgress("stop_all");
    try {
      await invoke("stop_all_services");
      await fetchData();
    } finally {
      setActionInProgress(null);
    }
  };

  const toggleExpand = (service: string) => {
    if (expandedService === service) {
      setExpandedService(null);
      setServiceLogs("");
    } else {
      setExpandedService(service);
      handleViewLogs(service);
    }
  };

  // ── Overall status ──────────────────────────────────────────────────────

  const overallStatus = (): { label: string; color: string } => {
    if (criticalAlerts.length > 0) return { label: "Critical", color: "#f87171" };
    const unhealthy = services.filter((s) => s.state === "unhealthy" || s.state === "not_running");
    if (unhealthy.length > 0) return { label: "Degraded", color: "#fbbf24" };
    if (services.length === 0) return { label: "Loading", color: "#71717a" };
    return { label: "All Systems Operational", color: "#34d399" };
  };

  const status = overallStatus();

  // ── Render ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={centerStyle}>
        <span style={{ color: "#555", fontSize: 13 }}>Loading dashboard...</span>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0f0f11", color: "#e8e8ea", padding: "32px 40px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 32 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>EkamCore Manager</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: status.color, display: "inline-block" }} />
            <span style={{ fontSize: 13, color: status.color }}>{status.label}</span>
            {data && (
              <span style={{ fontSize: 12, color: "#555", marginLeft: 12 }}>
                Uptime: {formatUptime(data.uptime_hours)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Alert banners */}
      {criticalAlerts.map((alert) => (
        <AlertBanner key={alert.service} type="critical" message={alert.message} />
      ))}
      {unstableAlerts.map((alert) => (
        <AlertBanner key={alert.service} type="warning" message={alert.message} />
      ))}
      {data?.disk_warning && (
        <AlertBanner type="warning" message={`Disk space low: ${data.disk_free_gb.toFixed(1)} GB free. EkamCore requires at least 30 GB.`} />
      )}
      {error && (
        <AlertBanner type="critical" message={`Dashboard error: ${error}`} />
      )}

      {/* KPI cards */}
      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16, marginBottom: 32 }}>
          <KpiCard label="Files Indexed" value={formatNumber(data.total_files)} />
          <KpiCard label="Photos Indexed" value={formatNumber(data.total_photos)} />
          <KpiCard label="Persons" value={formatNumber(data.total_persons)} />
          <KpiCard label="Last Backup" value={data.last_backup ? relativeTime(data.last_backup) : "Never"} />
          <DiskCard freeGb={data.disk_free_gb} warning={data.disk_warning} />
        </div>
      )}

      {/* Service health grid */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16, color: "#a1a1aa" }}>Services</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {services
            .filter((s) => s.name !== "ekamcore-migrate") // migrate is a one-shot container
            .map((svc) => (
            <ServiceTile
              key={svc.name}
              service={svc}
              expanded={expandedService === svc.name}
              logs={expandedService === svc.name ? serviceLogs : ""}
              logsLoading={logsLoading && expandedService === svc.name}
              restarting={actionInProgress === svc.name}
              onToggle={() => toggleExpand(svc.name)}
              onRestart={() => handleRestart(svc.name)}
              isCritical={criticalAlerts.some((a) => a.service === svc.name)}
            />
          ))}
        </div>
      </div>

      {/* Bottom controls */}
      <div style={{ display: "flex", gap: 12, paddingTop: 16, borderTop: "1px solid #27272a" }}>
        <button
          onClick={handleStartAll}
          disabled={actionInProgress !== null}
          style={{ ...btnStyle("#22c55e", "#166534"), opacity: actionInProgress ? 0.5 : 1 }}
        >
          {actionInProgress === "start_all" ? "Starting..." : "Start All"}
        </button>
        <button
          onClick={handleStopAll}
          disabled={actionInProgress !== null}
          style={{ ...btnStyle("#ef4444", "#991b1b"), opacity: actionInProgress ? 0.5 : 1 }}
        >
          {actionInProgress === "stop_all" ? "Stopping..." : "Stop All"}
        </button>
        <a
          href="https://localhost:443"
          target="_blank"
          rel="noopener noreferrer"
          style={{ ...btnStyle("#3b82f6", "#1e40af"), textDecoration: "none", display: "inline-flex", alignItems: "center" }}
        >
          Open Web UI
        </a>
        <button onClick={fetchData} style={btnStyle("#71717a", "#3f3f46")}>
          Refresh
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ServiceTile({
  service, expanded, logs, logsLoading, restarting, onToggle, onRestart, isCritical,
}: {
  service: ServiceHealthInfo;
  expanded: boolean;
  logs: string;
  logsLoading: boolean;
  restarting: boolean;
  onToggle: () => void;
  onRestart: () => void;
  isCritical: boolean;
}) {
  const borderColor = isCritical ? "#f87171" : expanded ? "#3b82f6" : "#27272a";

  return (
    <div style={{
      background: "#18181b",
      border: `1px solid ${borderColor}`,
      borderRadius: 10,
      padding: 16,
      cursor: "pointer",
      transition: "border-color 0.2s",
      gridColumn: expanded ? "1 / -1" : undefined,
    }}>
      {/* Header row */}
      <div onClick={onToggle} style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: STATE_DOT[service.state],
          flexShrink: 0,
          boxShadow: service.state === "unhealthy" ? "0 0 6px #f87171" : undefined,
        }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{displayName(service.name)}</div>
          <div style={{ fontSize: 12, color: STATE_DOT[service.state], marginTop: 2 }}>
            {STATE_LABEL[service.state]}
          </div>
        </div>
        <div style={{ textAlign: "right", fontSize: 11, color: "#71717a" }}>
          {service.memory_mb != null && (
            <div>{service.memory_mb.toFixed(0)} MB</div>
          )}
          {service.cpu_percent != null && (
            <div>{service.cpu_percent.toFixed(1)}% CPU</div>
          )}
          {service.uptime_seconds != null && (
            <div>{formatUptimeSeconds(service.uptime_seconds)}</div>
          )}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ marginTop: 16, borderTop: "1px solid #27272a", paddingTop: 16 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button
              onClick={(e) => { e.stopPropagation(); onRestart(); }}
              disabled={restarting}
              style={{ ...smallBtnStyle, background: "#3b82f6", opacity: restarting ? 0.5 : 1 }}
            >
              {restarting ? "Restarting..." : "Restart"}
            </button>
          </div>
          <div style={{
            background: "#0f0f11",
            borderRadius: 6,
            padding: 12,
            maxHeight: 200,
            overflow: "auto",
            fontFamily: "monospace",
            fontSize: 11,
            color: "#a1a1aa",
            whiteSpace: "pre-wrap",
            lineHeight: 1.5,
          }}>
            {logsLoading ? "Loading logs..." : (logs || "No logs available.")}
          </div>
        </div>
      )}
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={kpiCardStyle}>
      <div style={{ fontSize: 11, color: "#71717a", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600, color: "#e8e8ea" }}>{value}</div>
    </div>
  );
}

function DiskCard({ freeGb, warning }: { freeGb: number; warning: boolean }) {
  const color = warning ? "#fbbf24" : "#34d399";
  return (
    <div style={kpiCardStyle}>
      <div style={{ fontSize: 11, color: "#71717a", marginBottom: 6 }}>Disk Free</div>
      <div style={{ fontSize: 20, fontWeight: 600, color }}>{freeGb.toFixed(0)} GB</div>
      <div style={{ height: 3, background: "#27272a", borderRadius: 2, marginTop: 8, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${Math.min((freeGb / 500) * 100, 100)}%`,
          background: color,
          borderRadius: 2,
        }} />
      </div>
    </div>
  );
}

function AlertBanner({ type, message }: { type: "critical" | "warning"; message: string }) {
  const bg = type === "critical" ? "#450a0a" : "#451a03";
  const border = type === "critical" ? "#f87171" : "#fbbf24";
  const icon = type === "critical" ? "\u2717" : "\u26A0";
  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 8,
      padding: "10px 16px",
      marginBottom: 12,
      display: "flex",
      alignItems: "center",
      gap: 10,
      fontSize: 13,
    }}>
      <span style={{ color: border }}>{icon}</span>
      <span style={{ color: "#e8e8ea" }}>{message}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function formatUptime(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = Math.floor(hours / 24);
  const h = Math.round(hours % 24);
  return `${days}d ${h}h`;
}

function formatUptimeSeconds(secs: number): string {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
  return `${Math.floor(secs / 86400)}d`;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const centerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  height: "100vh",
  background: "#0f0f11",
};

const kpiCardStyle: React.CSSProperties = {
  background: "#18181b",
  border: "1px solid #27272a",
  borderRadius: 10,
  padding: 16,
};

function btnStyle(bg: string, _hoverBg?: string): React.CSSProperties {
  return {
    padding: "8px 20px",
    background: bg,
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  };
}

const smallBtnStyle: React.CSSProperties = {
  padding: "6px 14px",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
};

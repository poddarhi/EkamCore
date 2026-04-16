/**
 * S15-004 — Jobs Page
 *
 * Mirrors web admin JobsPage (S09-003) with manager-specific features.
 * 4 sections: Active, Queued, Recently Completed, Failed.
 * Auto-refreshes every 5 seconds via polling the local API.
 */

import { useEffect, useState, useCallback } from "react";
import type { Job, JobsData } from "../types";

const API_BASE = "http://localhost:8420";

export default function Jobs() {
  const [data, setData] = useState<JobsData>({ active: [], queued: [], completed: [], failed: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/admin/jobs`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();

      // Partition jobs by status
      const all: Job[] = json.jobs ?? json ?? [];
      const grouped: JobsData = {
        active: all.filter((j) => j.status === "active"),
        queued: all.filter((j) => j.status === "queued"),
        completed: all.filter((j) => j.status === "completed").slice(0, 50),
        failed: all.filter((j) => j.status === "failed"),
      };
      setData(grouped);
      setError(null);
    } catch (e) {
      setError(`Cannot fetch jobs: ${e}. Is the API running?`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const retryJob = async (jobId: string) => {
    setRetrying(jobId);
    try {
      await fetch(`${API_BASE}/api/v1/admin/jobs/${jobId}/retry`, { method: "POST" });
      await fetchJobs();
    } catch (e) {
      console.error("retry failed:", e);
    } finally {
      setRetrying(null);
    }
  };

  const retryAllFailed = async () => {
    setRetrying("all");
    try {
      await fetch(`${API_BASE}/api/v1/admin/jobs/retry-all-failed`, { method: "POST" });
      await fetchJobs();
    } catch (e) {
      console.error("retry all failed:", e);
    } finally {
      setRetrying(null);
    }
  };

  if (loading) {
    return <PageShell><span style={{ color: "#555", fontSize: 13 }}>Loading jobs...</span></PageShell>;
  }

  const totalActive = data.active.length + data.queued.length;

  return (
    <PageShell>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, color: "#e8e8ea" }}>Jobs</h1>
          <p style={{ color: "#71717a", fontSize: 13, marginTop: 4 }}>
            {totalActive > 0 ? `${totalActive} active` : "No active jobs"}
            {data.failed.length > 0 && ` \u2022 ${data.failed.length} failed`}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {data.failed.length > 0 && (
            <button
              onClick={retryAllFailed}
              disabled={retrying === "all"}
              style={{ ...btnStyle("#f59e0b"), opacity: retrying === "all" ? 0.5 : 1 }}
            >
              {retrying === "all" ? "Retrying..." : `Retry All Failed (${data.failed.length})`}
            </button>
          )}
          <a
            href="https://localhost/paperless/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ ...btnStyle("#3b82f6"), textDecoration: "none" }}
          >
            Open Paperless
          </a>
        </div>
      </div>

      {error && <AlertBanner message={error} />}

      {/* Active jobs */}
      <JobSection title="Active" jobs={data.active} retrying={retrying} onRetry={retryJob} showProgress />

      {/* Queued */}
      <JobSection title="Queued" jobs={data.queued} retrying={retrying} onRetry={retryJob} />

      {/* Failed */}
      {data.failed.length > 0 && (
        <JobSection title="Failed" jobs={data.failed} retrying={retrying} onRetry={retryJob} showError isFailed />
      )}

      {/* Recently completed */}
      <JobSection title="Recently Completed" jobs={data.completed} retrying={retrying} onRetry={retryJob} />

      {/* Empty state */}
      {totalActive === 0 && data.failed.length === 0 && data.completed.length === 0 && !error && (
        <div style={{ textAlign: "center", padding: "60px 0", color: "#555", fontSize: 14 }}>
          No jobs found. Ingestion jobs appear here when files are added to source folders.
        </div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function JobSection({
  title, jobs, retrying, onRetry, showProgress, showError, isFailed,
}: {
  title: string;
  jobs: Job[];
  retrying: string | null;
  onRetry: (id: string) => void;
  showProgress?: boolean;
  showError?: boolean;
  isFailed?: boolean;
}) {
  if (jobs.length === 0) return null;

  return (
    <div style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, color: isFailed ? "#f87171" : "#a1a1aa", marginBottom: 10 }}>
        {title} ({jobs.length})
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {jobs.map((job) => (
          <div
            key={job.id}
            style={{
              background: "#18181b",
              border: `1px solid ${isFailed ? "#7f1d1d" : "#27272a"}`,
              borderRadius: 8,
              padding: "12px 16px",
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: "#e8e8ea", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {job.filename}
              </div>
              <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>
                {job.source} {job.stage && `\u2022 ${job.stage}`}
              </div>
            </div>

            {showProgress && job.progress > 0 && (
              <div style={{ width: 100 }}>
                <div style={{ height: 3, background: "#27272a", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    height: "100%",
                    width: `${job.progress}%`,
                    background: "#3b82f6",
                    borderRadius: 2,
                    transition: "width 0.3s",
                  }} />
                </div>
                <div style={{ fontSize: 10, color: "#555", textAlign: "right", marginTop: 2 }}>
                  {job.progress}%
                </div>
              </div>
            )}

            {showError && job.error && (
              <div style={{ fontSize: 11, color: "#f87171", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {job.error}
              </div>
            )}

            {job.completed_at && (
              <div style={{ fontSize: 11, color: "#555", whiteSpace: "nowrap" }}>
                {relativeTime(job.completed_at)}
              </div>
            )}

            {isFailed && (
              <button
                onClick={() => onRetry(job.id)}
                disabled={retrying === job.id}
                style={{ ...smallBtnStyle, opacity: retrying === job.id ? 0.5 : 1 }}
              >
                {retrying === job.id ? "..." : "Retry"}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function AlertBanner({ message }: { message: string }) {
  return (
    <div style={{
      background: "#451a03",
      border: "1px solid #fbbf24",
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
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

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
    display: "inline-flex",
    alignItems: "center",
  };
}

const smallBtnStyle: React.CSSProperties = {
  padding: "5px 12px",
  background: "#f59e0b",
  color: "#000",
  border: "none",
  borderRadius: 6,
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

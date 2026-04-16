/**
 * S15-006 — Updates & Rollback Page
 *
 * Check for updates, apply with 8-step progress, rollback to backup.
 */

import { useEffect, useState, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { UpdateInfo, UpdateProgress, UpdateResult, BackupEntry } from "../types";

const UPDATE_STEPS = [
  { key: "snapshot", label: "Pre-update backup" },
  { key: "pulling", label: "Pull new images" },
  { key: "stopping", label: "Stop services" },
  { key: "updating_tags", label: "Update image tags" },
  { key: "starting", label: "Start new version" },
  { key: "migrating", label: "Run migrations" },
  { key: "verifying", label: "Verify health" },
  { key: "complete", label: "Complete" },
];

export default function Updates() {
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [result, setResult] = useState<UpdateResult | null>(null);

  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [rollingBack, setRollingBack] = useState<string | null>(null);
  const [rollbackResult, setRollbackResult] = useState<string | null>(null);

  const unlistenProgress = useRef<UnlistenFn | null>(null);

  useEffect(() => {
    listen<UpdateProgress>("update-progress", (e) => {
      setProgress(e.payload);
    }).then((fn) => { unlistenProgress.current = fn; });

    fetchBackups();
    return () => { unlistenProgress.current?.(); };
  }, []);

  const fetchBackups = async () => {
    try {
      const list = await invoke<BackupEntry[]>("list_backups");
      setBackups(list);
    } catch (e) {
      console.error("list backups failed:", e);
    }
  };

  const handleCheckUpdates = async () => {
    setChecking(true);
    setResult(null);
    try {
      const info = await invoke<UpdateInfo>("check_for_updates");
      setUpdateInfo(info);
    } catch (e) {
      console.error("check updates failed:", e);
    } finally {
      setChecking(false);
    }
  };

  const handleApplyUpdate = async () => {
    if (!updateInfo?.latest_version) return;
    setApplying(true);
    setResult(null);
    setProgress(null);
    try {
      const res = await invoke<UpdateResult>("apply_update", {
        targetVersion: updateInfo.latest_version,
      });
      setResult(res);
      if (res.success) {
        setUpdateInfo(null); // Clear update info after success
      }
      await fetchBackups();
    } catch (e) {
      setResult({
        success: false,
        message: String(e),
        rolled_back: false,
        new_version: null,
      });
    } finally {
      setApplying(false);
    }
  };

  const handleRollback = async (backupPath: string) => {
    if (!confirm("This will stop all services, restore the backup, and restart. Continue?")) return;
    setRollingBack(backupPath);
    setRollbackResult(null);
    try {
      const msg = await invoke<string>("rollback_to_backup", { backupPath });
      setRollbackResult(msg);
    } catch (e) {
      setRollbackResult(`Error: ${e}`);
    } finally {
      setRollingBack(null);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0f0f11", color: "#e8e8ea", padding: "32px 40px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4 }}>Updates</h1>
      <p style={{ color: "#71717a", fontSize: 13, marginBottom: 32 }}>
        Check for new versions and manage rollbacks.
      </p>

      {/* Current version + check */}
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <h2 style={sectionHeading}>Current Version</h2>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#e8e8ea", marginTop: 8 }}>
              v{updateInfo?.current_version ?? "0.1.0"}
            </div>
          </div>
          <button
            onClick={handleCheckUpdates}
            disabled={checking || applying}
            style={{ ...btnStyle("#3b82f6"), opacity: checking ? 0.5 : 1 }}
          >
            {checking ? "Checking..." : "Check for Updates"}
          </button>
        </div>

        {/* Update available */}
        {updateInfo?.available && !applying && !result?.success && (
          <div style={{
            background: "#1e3a5f",
            border: "1px solid #3b82f6",
            borderRadius: 8,
            padding: 16,
            marginTop: 16,
          }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
              Update Available: v{updateInfo.latest_version}
            </div>
            {updateInfo.release_notes && (
              <p style={{ fontSize: 13, color: "#a1a1aa", marginBottom: 12 }}>
                {updateInfo.release_notes}
              </p>
            )}
            {updateInfo.download_size_mb > 0 && (
              <p style={{ fontSize: 12, color: "#71717a", marginBottom: 12 }}>
                Download size: {updateInfo.download_size_mb.toFixed(0)} MB
              </p>
            )}
            <button
              onClick={handleApplyUpdate}
              style={btnStyle("#22c55e")}
            >
              Apply Update
            </button>
          </div>
        )}

        {updateInfo && !updateInfo.available && !applying && (
          <div style={{ marginTop: 16, fontSize: 13, color: "#34d399" }}>
            You're on the latest version.
          </div>
        )}
      </div>

      {/* Update progress */}
      {(applying || result) && (
        <div style={{ ...cardStyle, marginTop: 20 }}>
          <h2 style={sectionHeading}>
            {result ? (result.success ? "Update Complete" : "Update Failed") : "Applying Update"}
          </h2>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
            {UPDATE_STEPS.map((step, i) => {
              const stepNum = i + 1;
              const currentStep = progress?.step_number ?? 0;
              const isDone = result ? (result.success || step.key !== progress?.step) && stepNum <= currentStep : stepNum < currentStep;
              const isActive = !result && stepNum === currentStep;
              const isRollingBack = progress?.step === "rolling_back" && stepNum === currentStep;

              return (
                <div key={step.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{
                    color: isRollingBack ? "#f87171" : isDone ? "#34d399" : isActive ? "#60a5fa" : "#555",
                    fontSize: 13,
                    width: 16,
                  }}>
                    {isRollingBack ? "\u2717" : isDone ? "\u2713" : isActive ? "\u25CC" : "\u25CB"}
                  </span>
                  <span style={{
                    fontSize: 13,
                    color: isDone ? "#a1a1aa" : isActive ? "#e8e8ea" : "#555",
                  }}>
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>

          {progress && applying && (
            <div style={{ marginTop: 16 }}>
              <div style={{ height: 4, background: "#27272a", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${progress.percent}%`,
                  background: progress.step === "rolling_back" ? "#f87171" : "#3b82f6",
                  borderRadius: 2,
                  transition: "width 0.4s ease",
                }} />
              </div>
              <div style={{ fontSize: 12, color: "#71717a", marginTop: 6 }}>{progress.message}</div>
            </div>
          )}

          {result && (
            <div style={{
              marginTop: 16,
              padding: 12,
              borderRadius: 8,
              background: result.success ? "#14532d" : "#450a0a",
              border: `1px solid ${result.success ? "#34d399" : "#f87171"}`,
              fontSize: 13,
              color: "#e8e8ea",
            }}>
              {result.message}
              {result.rolled_back && (
                <div style={{ marginTop: 6, fontSize: 12, color: "#fbbf24" }}>
                  The previous version has been restored automatically.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Rollback section */}
      <div style={{ ...cardStyle, marginTop: 20 }}>
        <h2 style={sectionHeading}>Rollback</h2>
        <p style={{ fontSize: 12, color: "#555", marginTop: 4, marginBottom: 16 }}>
          Restore from a previous backup. This will stop all services, restore data, and restart.
        </p>

        {backups.length === 0 ? (
          <div style={{ fontSize: 13, color: "#555" }}>No backups available.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {backups.slice(0, 10).map((backup) => (
              <div
                key={backup.path}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 14px",
                  background: "#0f0f11",
                  borderRadius: 8,
                  border: "1px solid #27272a",
                }}
              >
                <div>
                  <div style={{ fontSize: 13, color: "#e8e8ea" }}>{backup.timestamp}</div>
                  <div style={{ fontSize: 11, color: "#555" }}>{backup.size_mb} MB</div>
                </div>
                <button
                  onClick={() => handleRollback(backup.path)}
                  disabled={rollingBack !== null || applying}
                  style={{
                    ...btnStyle("#ef4444"),
                    padding: "5px 14px",
                    fontSize: 12,
                    opacity: rollingBack === backup.path ? 0.5 : 1,
                  }}
                >
                  {rollingBack === backup.path ? "Restoring..." : "Rollback"}
                </button>
              </div>
            ))}
          </div>
        )}

        {rollbackResult && (
          <div style={{
            marginTop: 12,
            padding: 12,
            borderRadius: 8,
            background: "#18181b",
            border: "1px solid #27272a",
            fontSize: 13,
            color: "#a1a1aa",
          }}>
            {rollbackResult}
          </div>
        )}
      </div>
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
  padding: 20,
};

const sectionHeading: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  color: "#e8e8ea",
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

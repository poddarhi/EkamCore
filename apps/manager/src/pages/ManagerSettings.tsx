/**
 * S15-005 — Manager Settings
 *
 * Auto-start toggle, backup scheduling, secret management, reset,
 * and about section.
 */

import { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { LaunchdStatus, SecretStatus } from "../types";

export default function ManagerSettings() {
  const [launchd, setLaunchd] = useState<LaunchdStatus | null>(null);
  const [secrets, setSecrets] = useState<SecretStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Action states
  const [backupRunning, setBackupRunning] = useState(false);
  const [backupResult, setBackupResult] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateResult, setRegenerateResult] = useState<string | null>(null);
  const [backupHour, setBackupHour] = useState(2);
  const [backupMinute, setBackupMinute] = useState(0);

  const fetchStatus = useCallback(async () => {
    try {
      const [ld, ss] = await Promise.all([
        invoke<LaunchdStatus>("get_launchd_status"),
        invoke<SecretStatus>("check_secret_status"),
      ]);
      setLaunchd(ld);
      setSecrets(ss);
      setBackupHour(ld.backup_hour);
      setBackupMinute(ld.backup_minute);
    } catch (e) {
      console.error("settings fetch failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // ── Handlers ────────────────────────────────────────────────────────────

  const toggleAutoStart = async () => {
    if (!launchd) return;
    try {
      if (launchd.login_item_registered) {
        await invoke("unregister_login_item");
      } else {
        await invoke("register_login_item");
      }
      await fetchStatus();
    } catch (e) {
      console.error("toggle auto-start failed:", e);
    }
  };

  const toggleBackup = async () => {
    if (!launchd) return;
    try {
      if (launchd.backup_scheduled) {
        await invoke("uninstall_backup_schedule");
      } else {
        await invoke("install_backup_schedule", { hour: backupHour, minute: backupMinute });
      }
      await fetchStatus();
    } catch (e) {
      console.error("toggle backup failed:", e);
    }
  };

  const updateBackupTime = async () => {
    try {
      await invoke("install_backup_schedule", { hour: backupHour, minute: backupMinute });
      await fetchStatus();
    } catch (e) {
      console.error("update backup time failed:", e);
    }
  };

  const handleRunBackup = async () => {
    setBackupRunning(true);
    setBackupResult(null);
    try {
      const result = await invoke<string>("run_backup_now");
      setBackupResult(result);
    } catch (e) {
      setBackupResult(`Error: ${e}`);
    } finally {
      setBackupRunning(false);
    }
  };

  const handleRegenerate = async () => {
    if (!confirm("This will regenerate ALL encryption keys and secrets. All services must be restarted and the database will need to be re-initialized. Are you sure?")) return;
    if (!confirm("FINAL WARNING: This action cannot be undone. Existing encrypted data may become inaccessible. Continue?")) return;

    setRegenerating(true);
    setRegenerateResult(null);
    try {
      const result = await invoke<string>("regenerate_all_secrets");
      setRegenerateResult(result);
      await fetchStatus();
    } catch (e) {
      setRegenerateResult(`Error: ${e}`);
    } finally {
      setRegenerating(false);
    }
  };

  const handleResetSetup = async () => {
    if (!confirm("This will reset the setup wizard. You will need to complete the full setup process again. Continue?")) return;

    try {
      await invoke("reset_setup");
      // Reload the app to trigger setup wizard
      window.location.reload();
    } catch (e) {
      console.error("reset failed:", e);
    }
  };

  if (loading) {
    return <PageShell><span style={{ color: "#555", fontSize: 13 }}>Loading settings...</span></PageShell>;
  }

  return (
    <PageShell>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 32, color: "#e8e8ea" }}>Settings</h1>

      {/* Auto-start */}
      <Section title="Startup">
        <ToggleRow
          label="Start EkamCore when you log in"
          description="Registers as a macOS Login Item via launchd."
          enabled={launchd?.login_item_registered ?? false}
          onToggle={toggleAutoStart}
        />
      </Section>

      {/* Backup schedule */}
      <Section title="Backups">
        <ToggleRow
          label="Automatic daily backups"
          description="Runs the backup script on a schedule via launchd."
          enabled={launchd?.backup_scheduled ?? false}
          onToggle={toggleBackup}
        />

        {launchd?.backup_scheduled && (
          <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 12 }}>
            <label style={{ fontSize: 13, color: "#a1a1aa" }}>Backup time:</label>
            <select
              value={backupHour}
              onChange={(e) => setBackupHour(Number(e.target.value))}
              style={selectStyle}
            >
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{String(i).padStart(2, "0")}</option>
              ))}
            </select>
            <span style={{ color: "#555" }}>:</span>
            <select
              value={backupMinute}
              onChange={(e) => setBackupMinute(Number(e.target.value))}
              style={selectStyle}
            >
              {[0, 15, 30, 45].map((m) => (
                <option key={m} value={m}>{String(m).padStart(2, "0")}</option>
              ))}
            </select>
            <button onClick={updateBackupTime} style={smallBtnStyle}>
              Update
            </button>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <button
            onClick={handleRunBackup}
            disabled={backupRunning}
            style={{ ...actionBtnStyle("#3b82f6"), opacity: backupRunning ? 0.5 : 1 }}
          >
            {backupRunning ? "Running..." : "Run Backup Now"}
          </button>
        </div>

        {backupResult && (
          <div style={resultBoxStyle}>
            {backupResult}
          </div>
        )}
      </Section>

      {/* Secret management */}
      <Section title="Secrets & Keychain">
        {secrets && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: secrets.all_present ? "#34d399" : secrets.keychain_accessible ? "#fbbf24" : "#f87171",
              }} />
              <span style={{ fontSize: 13, color: "#e8e8ea" }}>
                {secrets.all_present
                  ? "All 8 secrets present in Keychain"
                  : !secrets.keychain_accessible
                  ? "Keychain is locked — unlock your Mac"
                  : `${secrets.missing.length} secret(s) missing`}
              </span>
            </div>
            {secrets.missing.length > 0 && (
              <div style={{ fontSize: 12, color: "#f87171", marginLeft: 16 }}>
                Missing: {secrets.missing.join(", ")}
              </div>
            )}
          </div>
        )}
      </Section>

      {/* Danger zone */}
      <Section title="Danger Zone" danger>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <DangerAction
            label="Regenerate All Secrets"
            description="Generates new encryption keys. Existing encrypted data may become inaccessible. Requires full service restart."
            buttonText={regenerating ? "Regenerating..." : "Regenerate Secrets"}
            onAction={handleRegenerate}
            disabled={regenerating}
          />
          {regenerateResult && <div style={resultBoxStyle}>{regenerateResult}</div>}

          <DangerAction
            label="Reset Setup"
            description="Removes setup state and returns to the setup wizard. Does not delete data or secrets."
            buttonText="Reset to Setup Wizard"
            onAction={handleResetSetup}
          />
        </div>
      </Section>

      {/* About */}
      <Section title="About">
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <AboutRow label="EkamCore Manager" value="0.1.0" />
          <AboutRow label="Tauri" value="2.x" />
          <AboutRow label="Platform" value="macOS (Apple Silicon)" />
        </div>
      </Section>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Section({ title, children, danger }: { title: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <div style={{
      marginBottom: 32,
      padding: 20,
      background: danger ? "#1a0505" : "#18181b",
      border: `1px solid ${danger ? "#7f1d1d" : "#27272a"}`,
      borderRadius: 10,
    }}>
      <h2 style={{
        fontSize: 15,
        fontWeight: 600,
        color: danger ? "#f87171" : "#e8e8ea",
        margin: "0 0 16px 0",
      }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

function ToggleRow({ label, description, enabled, onToggle }: {
  label: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <div style={{ fontSize: 14, color: "#e8e8ea" }}>{label}</div>
        <div style={{ fontSize: 12, color: "#555", marginTop: 2 }}>{description}</div>
      </div>
      <button
        onClick={onToggle}
        style={{
          width: 44,
          height: 24,
          borderRadius: 12,
          border: "none",
          background: enabled ? "#3b82f6" : "#3f3f46",
          cursor: "pointer",
          position: "relative",
          transition: "background 0.2s",
          flexShrink: 0,
        }}
      >
        <div style={{
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "#fff",
          position: "absolute",
          top: 3,
          left: enabled ? 23 : 3,
          transition: "left 0.2s",
        }} />
      </button>
    </div>
  );
}

function DangerAction({ label, description, buttonText, onAction, disabled }: {
  label: string;
  description: string;
  buttonText: string;
  onAction: () => void;
  disabled?: boolean;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 0", borderBottom: "1px solid #27272a" }}>
      <div>
        <div style={{ fontSize: 14, color: "#e8e8ea" }}>{label}</div>
        <div style={{ fontSize: 12, color: "#71717a", marginTop: 2 }}>{description}</div>
      </div>
      <button
        onClick={onAction}
        disabled={disabled}
        style={{ ...actionBtnStyle("#ef4444"), opacity: disabled ? 0.5 : 1, flexShrink: 0 }}
      >
        {buttonText}
      </button>
    </div>
  );
}

function AboutRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
      <span style={{ color: "#71717a" }}>{label}</span>
      <span style={{ color: "#a1a1aa" }}>{value}</span>
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

const selectStyle: React.CSSProperties = {
  padding: "4px 8px",
  background: "#27272a",
  color: "#e8e8ea",
  border: "1px solid #3f3f46",
  borderRadius: 6,
  fontSize: 13,
  outline: "none",
};

const smallBtnStyle: React.CSSProperties = {
  padding: "4px 12px",
  background: "#27272a",
  color: "#e8e8ea",
  border: "1px solid #3f3f46",
  borderRadius: 6,
  fontSize: 12,
  cursor: "pointer",
};

function actionBtnStyle(bg: string): React.CSSProperties {
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

const resultBoxStyle: React.CSSProperties = {
  marginTop: 12,
  background: "#0f0f11",
  border: "1px solid #27272a",
  borderRadius: 8,
  padding: 12,
  fontFamily: "monospace",
  fontSize: 11,
  color: "#a1a1aa",
  whiteSpace: "pre-wrap",
  maxHeight: 150,
  overflow: "auto",
};

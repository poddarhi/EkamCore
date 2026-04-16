/**
 * EkamCore Manager — Root App Component
 *
 * Routes between: Loading → Setup Wizard → Startup Sequence → Main App (tabbed).
 * After setup, shows a sidebar with Dashboard / Jobs / Storage / Diagnostics tabs.
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import SetupWizard from "./pages/SetupWizard";
import StartupSequence from "./pages/StartupSequence";
import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import Storage from "./pages/Storage";
import Diagnostics from "./pages/Diagnostics";

type AppView = "loading" | "setup" | "starting" | "main";
type Tab = "dashboard" | "jobs" | "storage" | "diagnostics";

const TABS: { id: Tab; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "jobs", label: "Jobs" },
  { id: "storage", label: "Storage" },
  { id: "diagnostics", label: "Diagnostics" },
];

export default function App() {
  const [view, setView] = useState<AppView>("loading");
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");

  useEffect(() => {
    invoke<boolean>("is_setup_complete")
      .then((complete) => setView(complete ? "starting" : "setup"))
      .catch(() => setView("setup"));
  }, []);

  if (view === "loading") {
    return (
      <div style={centerStyle}>
        <span style={{ color: "#555", fontSize: 13 }}>Loading...</span>
      </div>
    );
  }

  if (view === "setup") {
    return <SetupWizard onComplete={() => setView("starting")} />;
  }

  if (view === "starting") {
    return <StartupSequence onReady={() => setView("main")} />;
  }

  // Main tabbed view
  return (
    <div style={{ display: "flex", height: "100vh", background: "#0f0f11" }}>
      {/* Sidebar */}
      <nav style={sidebarStyle}>
        <div style={{ padding: "20px 16px 24px", color: "#e8e8ea", fontSize: 14, fontWeight: 600 }}>
          EkamCore
        </div>
        {TABS.map((tab) => {
          const isActive = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: "block",
                width: "100%",
                padding: "10px 16px",
                background: isActive ? "#27272a" : "transparent",
                borderLeft: `3px solid ${isActive ? "#3b82f6" : "transparent"}`,
                border: "none",
                borderLeftStyle: "solid",
                borderLeftWidth: 3,
                borderLeftColor: isActive ? "#3b82f6" : "transparent",
                color: isActive ? "#e8e8ea" : "#71717a",
                fontSize: 13,
                textAlign: "left",
                cursor: "pointer",
                transition: "background 0.15s",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Content area */}
      <main style={{ flex: 1, overflow: "auto" }}>
        {activeTab === "dashboard" && <Dashboard />}
        {activeTab === "jobs" && <Jobs />}
        {activeTab === "storage" && <Storage />}
        {activeTab === "diagnostics" && <Diagnostics />}
      </main>
    </div>
  );
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

const sidebarStyle: React.CSSProperties = {
  width: 180,
  background: "#18181b",
  borderRight: "1px solid #27272a",
  display: "flex",
  flexDirection: "column",
  flexShrink: 0,
};

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import SetupWizard from "./pages/SetupWizard";
import StartupSequence from "./pages/StartupSequence";
import Dashboard from "./pages/Dashboard";

type AppView = "loading" | "setup" | "starting" | "dashboard";

export default function App() {
  const [view, setView] = useState<AppView>("loading");

  useEffect(() => {
    invoke<boolean>("is_setup_complete")
      .then((complete) => setView(complete ? "starting" : "setup"))
      .catch(() => setView("setup"));
  }, []);

  if (view === "loading") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "#0f0f11",
        }}
      >
        <span style={{ color: "#555", fontSize: 13 }}>Loading…</span>
      </div>
    );
  }

  if (view === "setup") {
    return (
      <SetupWizard
        onComplete={() => setView("starting")}
      />
    );
  }

  if (view === "starting") {
    return (
      <StartupSequence
        onReady={() => setView("dashboard")}
      />
    );
  }

  return <Dashboard />;
}

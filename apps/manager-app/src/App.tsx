import type { TodayCard } from "@ekamcore/shared-types";
import { startTransition, useEffect, useMemo, useState } from "react";
import {
  createServiceSupervisor,
  type BackendSlice,
  type LogEntry,
  type ServiceRecord,
  type SetupCheck,
  type StatusTone,
  type SupervisionSnapshot,
} from "./lib/supervision";

type ScreenId =
  | "setup"
  | "service-status"
  | "logs"
  | "settings"
  | "diagnostics";

type Screen = {
  id: ScreenId;
  label: string;
  eyebrow: string;
  title: string;
  description: string;
};

const screens: Screen[] = [
  {
    id: "setup",
    label: "Setup",
    eyebrow: "First Run",
    title: "Guide the hub from blank Mac to ready local stack.",
    description:
      "The manager app now exposes concrete prerequisite checks for Docker Desktop, generated contract types, and the live backend stub path.",
  },
  {
    id: "service-status",
    label: "Service Status",
    eyebrow: "Control Plane",
    title: "One place to see whether the hub is healthy.",
    description:
      "The service-status screen now blends local runtime supervision with live FastAPI stub polling for the first real end-to-end demo path.",
  },
  {
    id: "logs",
    label: "Logs",
    eyebrow: "Troubleshooting",
    title: "Recent errors and useful context without terminal spelunking.",
    description:
      "The current log surface stays intentionally small, but it now reports both supervision facts and backend connectivity.",
  },
  {
    id: "settings",
    label: "Settings",
    eyebrow: "Configuration",
    title: "Surface the controls that shape how the hub runs.",
    description:
      "Sprint 0 settings focus on the decisions already locked in: runtime substrate, contract source of truth, backend base URL, and API boundary rules.",
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    eyebrow: "Support",
    title: "Prepare the product for supportability from the beginning.",
    description:
      "Diagnostics now reads from the same supervision snapshot as the rest of the app, including live backend details when the stub service is running.",
  },
];

const supervisor = createServiceSupervisor();

function formatCollectedAt(collectedAtMs: number) {
  return new Date(collectedAtMs).toLocaleString();
}

function statusLabel(status: StatusTone) {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "warning":
      return "Warning";
    case "attention":
      return "Needs attention";
    case "planned":
      return "Planned";
    case "blocked":
      return "Blocked";
    default:
      return status;
  }
}

function renderStatusBadge(status: StatusTone) {
  return <span className={`badge badge-${status}`}>{statusLabel(status)}</span>;
}

function describeTodayCard(card: TodayCard) {
  switch (card.type) {
    case "agenda":
      return `${card.title} · ${card.items.length} scheduled item${
        card.items.length === 1 ? "" : "s"
      }`;
    case "focus":
      return `${card.title} · ${card.actionLabel}`;
    case "system":
      return `${card.title} · ${card.status}`;
    default:
      return "Unknown card";
  }
}

function renderSetupChecks(checks: SetupCheck[]) {
  return (
    <div className="stack-list">
      {checks.map((check) => (
        <article key={check.id} className="stack-card">
          <div className="stack-card-header">
            <div>
              <h3>{check.label}</h3>
              <p>{check.detail}</p>
            </div>
            {renderStatusBadge(check.status)}
          </div>
          {check.nextStep ? <p className="stack-note">{check.nextStep}</p> : null}
        </article>
      ))}
    </div>
  );
}

function renderServices(services: ServiceRecord[]) {
  return (
    <div className="stack-list">
      {services.map((service) => (
        <article key={service.id} className="stack-card">
          <div className="stack-card-header">
            <div>
              <p className="stack-kicker">{service.category}</p>
              <h3>{service.label}</h3>
              <p>{service.detail}</p>
            </div>
            {renderStatusBadge(service.status)}
          </div>
          {service.actionHint ? (
            <p className="stack-note">Next action: {service.actionHint}</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function renderLogs(logs: LogEntry[]) {
  return (
    <div className="stack-list">
      {logs.map((entry) => (
        <article key={entry.id} className="stack-card">
          <div className="stack-card-header">
            <div>
              <p className="stack-kicker">{entry.source}</p>
              <h3>{entry.level.toUpperCase()}</h3>
              <p>{entry.message}</p>
            </div>
            <span
              className={`badge badge-${
                entry.level === "error"
                  ? "blocked"
                  : entry.level === "warning"
                    ? "warning"
                    : "healthy"
              }`}
            >
              {entry.level}
            </span>
          </div>
        </article>
      ))}
    </div>
  );
}

function renderLiveSlicePanel(backend: BackendSlice) {
  const hasLiveToday = Boolean(backend.today);

  return (
    <article className="panel">
      <div className="panel-header">
        <p className="eyebrow">Thin End-to-End Demo</p>
        <h3>{backend.connectionLabel}</h3>
      </div>

      <div className="panel-inline-row">
        {renderStatusBadge(backend.status)}
        <span className="inline-detail">Base URL: {backend.baseUrl}</span>
        <span className="inline-detail">Workspace: {backend.workspaceId}</span>
      </div>

      <p className="panel-copy">
        {backend.health?.data.summary ??
          backend.error ??
          "Start the FastAPI stub backend to turn the live demo path on."}
      </p>

      <div className="metric-grid">
        <article className="metric-card">
          <p>API Version</p>
          <strong>
            {backend.version?.data.apiVersion ?? "Unavailable"}
          </strong>
        </article>
        <article className="metric-card">
          <p>Contract Version</p>
          <strong>
            {backend.version?.data.contractVersion ?? "Unavailable"}
          </strong>
        </article>
        <article className="metric-card">
          <p>Application Version</p>
          <strong>
            {backend.version?.data.applicationVersion ?? "Unavailable"}
          </strong>
        </article>
        <article className="metric-card">
          <p>Today Cards</p>
          <strong>{backend.today?.data.cards.length ?? 0}</strong>
        </article>
      </div>

      {hasLiveToday ? (
        <>
          <div className="section-divider" />
          <div className="panel-header">
            <p className="eyebrow">Today Preview</p>
            <h3>{backend.today?.data.summary}</h3>
          </div>
          <ul className="preview-list">
            {backend.today?.data.cards.map((card) => (
              <li key={card.id}>{describeTodayCard(card)}</li>
            ))}
          </ul>
        </>
      ) : (
        <p className="stack-note">
          Keep `pnpm dev:backend` running on `127.0.0.1:8808` to load the live
          Today preview into this panel.
        </p>
      )}
    </article>
  );
}

function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("setup");
  const [snapshot, setSnapshot] = useState<SupervisionSnapshot | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      setIsRefreshing(true);

      try {
        const next = await supervisor.getSnapshot();
        if (cancelled) {
          return;
        }

        startTransition(() => {
          setSnapshot(next);
          setError(null);
        });
      } catch (refreshError) {
        if (cancelled) {
          return;
        }

        setError(
          refreshError instanceof Error
            ? refreshError.message
            : "Unknown refresh failure.",
        );
      } finally {
        if (!cancelled) {
          setIsRefreshing(false);
        }
      }
    };

    void refresh();
    const intervalId = window.setInterval(() => {
      void refresh();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const selectedScreen = useMemo(
    () => screens.find((screen) => screen.id === activeScreen) ?? screens[0],
    [activeScreen],
  );

  const readinessCards = useMemo(() => {
    if (!snapshot) {
      return [
        { title: "Reference Host", value: "Apple silicon / 24 GB", tone: "steady" },
        { title: "Runtime", value: "Loading...", tone: "attention" },
        { title: "Backend", value: "Loading...", tone: "attention" },
        { title: "Contract", value: "Loading...", tone: "attention" },
      ] as const;
    }

    return [
      {
        title: "Reference Host",
        value: "Apple silicon / 24 GB",
        tone: "steady",
      },
      {
        title: "Runtime",
        value: snapshot.runtime.engineReachable
          ? `Ready (${snapshot.runtime.contextName})`
          : "Needs follow-up",
        tone: snapshot.runtime.engineReachable ? "steady" : "attention",
      },
      {
        title: "Backend",
        value: snapshot.backend.connectionLabel,
        tone:
          snapshot.backend.status === "healthy"
            ? "active"
            : snapshot.backend.status === "warning"
              ? "attention"
              : "attention",
      },
      {
        title: "Contract",
        value:
          snapshot.diagnostics.find((fact) => fact.label === "Contract version")
            ?.value ?? "Pending",
        tone: "active",
      },
    ] as const;
  }, [snapshot]);

  const screenBody = useMemo(() => {
    if (!snapshot) {
      return (
        <article className="panel">
          <div className="panel-header">
            <p className="eyebrow">Loading</p>
            <h3>Building the first supervision snapshot</h3>
          </div>
          <p className="panel-copy">
            The manager app is collecting runtime, contract, and backend baseline
            information.
          </p>
        </article>
      );
    }

    switch (activeScreen) {
      case "setup":
        return (
          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Readiness Checks</p>
              <h3>Clean-machine onboarding baseline</h3>
            </div>
            {renderSetupChecks(snapshot.setupChecks)}
          </article>
        );
      case "service-status":
        return (
          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Live Services</p>
              <h3>Runtime and application surfaces</h3>
            </div>
            {renderServices(snapshot.services)}
          </article>
        );
      case "logs":
        return (
          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Recent Log Summary</p>
              <h3>Readable operational context</h3>
            </div>
            {renderLogs(snapshot.logs)}
          </article>
        );
      case "settings":
        return (
          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Locked Decisions</p>
              <h3>Configuration baseline</h3>
            </div>
            <div className="stack-list">
              {snapshot.settings.map((setting) => (
                <article key={setting.label} className="stack-card">
                  <div className="stack-card-header">
                    <div>
                      <h3>{setting.label}</h3>
                      <p>{setting.detail}</p>
                    </div>
                    <strong>{setting.value}</strong>
                  </div>
                </article>
              ))}
            </div>
          </article>
        );
      case "diagnostics":
        return (
          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Runtime Facts</p>
              <h3>Diagnostics snapshot</h3>
            </div>
            <div className="diagnostic-grid">
              {snapshot.diagnostics.map((fact) => (
                <article
                  key={fact.label}
                  className={`status-card ${
                    fact.tone === "healthy"
                      ? "steady"
                      : fact.tone === "planned"
                        ? "attention"
                        : "active"
                  }`}
                >
                  <p>{fact.label}</p>
                  <strong>{fact.value}</strong>
                </article>
              ))}
            </div>
          </article>
        );
      default:
        return null;
    }
  }, [activeScreen, snapshot]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="brand-kicker">EkamCore</p>
          <h1>Manager App</h1>
          <p className="brand-copy">
            Sprint 0 shell for hub setup, control, and supportability.
          </p>
        </div>

        <nav className="nav-list" aria-label="Manager sections">
          {screens.map((screen) => {
            const isActive = screen.id === activeScreen;
            return (
              <button
                key={screen.id}
                className={`nav-item${isActive ? " is-active" : ""}`}
                onClick={() => setActiveScreen(screen.id)}
                type="button"
              >
                <span className="nav-item-label">{screen.label}</span>
                <span className="nav-item-kicker">{screen.eyebrow}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-note">
          <span className="pill">Mac-first v1</span>
          <span className="pill">Local-only</span>
          <span className="pill">Tauri + React</span>
        </div>
      </aside>

      <main className="content">
        <header className="hero">
          <div>
            <p className="eyebrow">{selectedScreen.eyebrow}</p>
            <h2>{selectedScreen.title}</h2>
            <p className="hero-copy">{selectedScreen.description}</p>
          </div>

          <div className="hero-panel">
            <p className="hero-panel-label">Supervision status</p>
            <strong>{snapshot?.summary ?? "Collecting the first runtime snapshot..."}</strong>
            <span>
              Source: {snapshot?.source ?? "loading"} | Last updated:{" "}
              {snapshot ? formatCollectedAt(snapshot.collectedAtMs) : "waiting"}
            </span>
            <span>Next integration: {snapshot?.nextIntegration ?? "Waiting on the first snapshot."}</span>
            <span>
              {isRefreshing ? "Refresh in progress." : "Auto-refreshing every 15 seconds."}
            </span>
          </div>
        </header>

        {error ? <div className="alert-banner">Refresh warning: {error}</div> : null}

        <section className="card-grid" aria-label="Readiness overview">
          {readinessCards.map((card) => (
            <article key={card.title} className={`status-card ${card.tone}`}>
              <p>{card.title}</p>
              <strong>{card.value}</strong>
            </article>
          ))}
        </section>

        <section className="detail-grid">
          {screenBody}
          {snapshot ? (
            renderLiveSlicePanel(snapshot.backend)
          ) : (
            <article className="panel">
              <div className="panel-header">
                <p className="eyebrow">Thin End-to-End Demo</p>
                <h3>Waiting for backend status</h3>
              </div>
              <p className="panel-copy">
                The manager app will load health, version, and Today stubs from the
                backend once the first snapshot completes.
              </p>
            </article>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Current App Activity</p>
            <h3>What this slice already proves</h3>
          </div>
          <ul className="detail-list">
            {(snapshot?.activity ?? [
              "Manager app shell is booting its first supervision snapshot.",
              "Generated shared types are already available to the frontend.",
              "Backend stub routes are the next live integration target.",
            ]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}

export default App;

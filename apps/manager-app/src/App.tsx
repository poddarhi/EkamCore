import { useMemo, useState } from "react";

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
  bullets: string[];
};

const screens: Screen[] = [
  {
    id: "setup",
    label: "Setup",
    eyebrow: "First Run",
    title: "Guide the hub from blank Mac to ready local stack.",
    description:
      "This Sprint 0 shell reserves the setup surface for prerequisite checks, Docker Desktop detection, admin bootstrap, and the first source-connection flow.",
    bullets: [
      "Detect Docker Desktop and report clean-machine onboarding state.",
      "Reserve space for account bootstrap and permission guidance.",
      "Keep the flow honest about privileged install or first-run prompts.",
    ],
  },
  {
    id: "service-status",
    label: "Service Status",
    eyebrow: "Control Plane",
    title: "One place to see whether the hub is healthy.",
    description:
      "The eventual manager app will supervise the local runtime, show health, and expose restart and repair actions. This shell turns that structure into a concrete navigation target now.",
    bullets: [
      "Display runtime readiness, service heartbeat, and issue severity.",
      "Separate stack health from product data readiness.",
      "Support later restart, repair, and job-status actions.",
    ],
  },
  {
    id: "logs",
    label: "Logs",
    eyebrow: "Troubleshooting",
    title: "Recent errors and useful context without terminal spelunking.",
    description:
      "This area is reserved for readable runtime and backend diagnostics so the manager app becomes the first stop for support instead of a collection of shell commands.",
    bullets: [
      "Summarize recent failures in plain language.",
      "Keep a short tail of runtime and backend messages.",
      "Link later to export and support bundle actions.",
    ],
  },
  {
    id: "settings",
    label: "Settings",
    eyebrow: "Configuration",
    title: "Surface the controls that shape how the hub runs.",
    description:
      "Settings will eventually cover storage, runtime preferences, update policy, and private access guidance. For now, the shell establishes the location and structure.",
    bullets: [
      "Reserve controls for runtime and storage configuration.",
      "Make future update and rollback messaging easy to place.",
      "Keep high-risk actions explicit and reviewable.",
    ],
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    eyebrow: "Support",
    title: "Prepare the product for supportability from the beginning.",
    description:
      "Diagnostics is where Sprint 0 and later work will gather versions, environment facts, health state, and exportable support context for debugging.",
    bullets: [
      "Capture runtime, app, and backend version details.",
      "Prepare a stable place for support bundle export.",
      "Support future repair recommendations with concrete evidence.",
    ],
  },
];

const readinessCards = [
  {
    title: "Reference Host",
    value: "Apple silicon / 24 GB",
    tone: "steady",
  },
  {
    title: "Runtime Direction",
    value: "Docker Desktop accepted",
    tone: "steady",
  },
  {
    title: "Current Stage",
    value: "Manager app skeleton",
    tone: "active",
  },
  {
    title: "Next Integration",
    value: "Service supervision adapter",
    tone: "attention",
  },
] as const;

const activityItems = [
  "Placeholder navigation is wired for Setup, Service Status, Logs, Settings, and Diagnostics.",
  "Tauri shell is ready for later runtime supervision and health polling.",
  "Frontend structure is TypeScript-first and ready for generated contract types later in Sprint 0.",
];

function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("setup");

  const selectedScreen = useMemo(
    () => screens.find((screen) => screen.id === activeScreen) ?? screens[0],
    [activeScreen],
  );

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
            <p className="hero-panel-label">Shell status</p>
            <strong>Ready for Sprint 0 integration work</strong>
            <span>
              This build is intentionally skeletal, but it already behaves like a
              real desktop shell and is ready for runtime wiring.
            </span>
          </div>
        </header>

        <section className="card-grid" aria-label="Readiness overview">
          {readinessCards.map((card) => (
            <article key={card.title} className={`status-card ${card.tone}`}>
              <p>{card.title}</p>
              <strong>{card.value}</strong>
            </article>
          ))}
        </section>

        <section className="detail-grid">
          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Section Scope</p>
              <h3>{selectedScreen.label}</h3>
            </div>
            <ul className="detail-list">
              {selectedScreen.bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          </article>

          <article className="panel">
            <div className="panel-header">
              <p className="eyebrow">Current App Activity</p>
              <h3>What this skeleton already proves</h3>
            </div>
            <ul className="detail-list">
              {activityItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        </section>
      </main>
    </div>
  );
}

export default App;

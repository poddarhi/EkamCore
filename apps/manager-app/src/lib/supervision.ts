import { invoke } from "@tauri-apps/api/core";
import { backendHealthBaseline, backendVersionBaseline } from "./backendBaseline";

export type StatusTone =
  | "healthy"
  | "warning"
  | "attention"
  | "planned"
  | "blocked";

export type SetupCheck = {
  id: string;
  label: string;
  status: StatusTone;
  detail: string;
  nextStep?: string;
};

export type ServiceRecord = {
  id: string;
  label: string;
  category: string;
  status: StatusTone;
  detail: string;
  actionHint?: string;
};

export type DiagnosticFact = {
  label: string;
  value: string;
  tone: StatusTone;
};

export type SettingFact = {
  label: string;
  value: string;
  detail: string;
};

export type LogEntry = {
  id: string;
  level: "info" | "warning" | "error";
  source: string;
  message: string;
};

export type RuntimeSnapshot = {
  contextName: string;
  dockerAppInstalled: boolean;
  contextAvailable: boolean;
  engineReachable: boolean;
  composeFilePresent: boolean;
  composeServicesDefined: boolean;
  status: StatusTone;
  detail: string;
};

export type SupervisionSnapshot = {
  source: string;
  collectedAtMs: number;
  summary: string;
  nextIntegration: string;
  runtime: RuntimeSnapshot;
  setupChecks: SetupCheck[];
  services: ServiceRecord[];
  diagnostics: DiagnosticFact[];
  settings: SettingFact[];
  logs: LogEntry[];
  activity: string[];
};

export interface ServiceSupervisor {
  getSnapshot(): Promise<SupervisionSnapshot>;
}

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function buildFallbackSnapshot(message?: string): SupervisionSnapshot {
  const now = Date.now();
  const logs: LogEntry[] = [
    {
      id: "log-web-fallback",
      level: message ? "warning" : "info",
      source: "manager-app",
      message:
        message ??
        "Running in web-shell mode, so supervision data is using the local fallback snapshot.",
    },
    {
      id: "log-contract-baseline",
      level: "info",
      source: "shared-types",
      message: backendHealthBaseline.data.summary,
    },
  ];

  return {
    source: "web-fallback",
    collectedAtMs: now,
    summary:
      "Manager shell is active with fallback supervision data while the desktop runtime path stays ready for live checks.",
    nextIntegration: "Wire the backend stub service into the manager app health loop.",
    runtime: {
      contextName: "desktop-linux",
      dockerAppInstalled: true,
      contextAvailable: true,
      engineReachable: true,
      composeFilePresent: false,
      composeServicesDefined: false,
      status: "healthy",
      detail:
        "Fallback mode assumes Docker Desktop is the accepted v1 substrate and no EkamCore compose services are defined yet.",
    },
    setupChecks: [
      {
        id: "docker-desktop",
        label: "Docker Desktop installed",
        status: "healthy",
        detail: "The accepted v1 runtime substrate is present on the reference machine.",
      },
      {
        id: "docker-context",
        label: "Local Docker context ready",
        status: "healthy",
        detail: "The runtime scripts target desktop-linux by default.",
      },
      {
        id: "contract-generated",
        label: "Shared contract types generated",
        status: "healthy",
        detail: "The manager app is reading generated OpenAPI-derived types from the monorepo package.",
      },
      {
        id: "backend-stub",
        label: "Backend stub service scaffolded",
        status: "planned",
        detail: "FastAPI stub routes exist; the next step is wiring live polling from the manager app.",
      },
    ],
    services: [
      {
        id: "service-runtime",
        label: "Docker Desktop runtime",
        category: "Runtime",
        status: "healthy",
        detail: "Accepted local runtime substrate for v1.",
        actionHint: "Use runtime:start and runtime:stop for repo-managed lifecycle steps.",
      },
      {
        id: "service-manager",
        label: "Manager app shell",
        category: "Desktop",
        status: "healthy",
        detail: "Tauri shell is running and can render supervision data.",
      },
      {
        id: "service-contract",
        label: "API contract + shared types",
        category: "Contract",
        status: "healthy",
        detail: `Contract version ${backendVersionBaseline.data.contractVersion} is generated into the shared-types package.`,
      },
      {
        id: "service-backend",
        label: "FastAPI stub backend",
        category: "Backend",
        status: "attention",
        detail: "Backend routes are scaffolded, but the manager app is not polling them live yet.",
        actionHint: "Next slice: thin end-to-end health polling and stub Today/Recap preview.",
      },
    ],
    diagnostics: [
      {
        label: "Snapshot source",
        value: "web-fallback",
        tone: "warning",
      },
      {
        label: "Runtime context",
        value: "desktop-linux",
        tone: "healthy",
      },
      {
        label: "Backend API version",
        value: backendVersionBaseline.data.apiVersion,
        tone: "healthy",
      },
      {
        label: "Contract version",
        value: backendVersionBaseline.data.contractVersion,
        tone: "healthy",
      },
      {
        label: "Compose services defined",
        value: "No",
        tone: "planned",
      },
    ],
    settings: [
      {
        label: "Runtime substrate",
        value: "Docker Desktop",
        detail: "Accepted in ADR 0001 for v1 behind the manager app.",
      },
      {
        label: "Docker context",
        value: "desktop-linux",
        detail: "Runtime scripts validate this local context by default.",
      },
      {
        label: "API source of truth",
        value: "OpenAPI 3.1 YAML",
        detail: "docs/contracts/ekamcore-api.yaml drives shared TS generation.",
      },
      {
        label: "Workspace rule",
        value: "API boundary scoped",
        detail: "Today, Recap, and job polling use explicit workspace identifiers.",
      },
    ],
    logs,
    activity: [
      "Service supervision adapter is active with a Tauri-first, fallback-friendly shape.",
      "Generated shared contract types are imported into real manager-app code.",
      "FastAPI stub routes are ready for the next thin end-to-end demo slice.",
    ],
  };
}

class DesktopSupervisor implements ServiceSupervisor {
  async getSnapshot() {
    if (!isTauriRuntime()) {
      return buildFallbackSnapshot();
    }

    try {
      return await invoke<SupervisionSnapshot>("get_supervision_snapshot");
    } catch (error) {
      const detail =
        error instanceof Error ? error.message : "Unknown Tauri invoke failure.";
      return buildFallbackSnapshot(
        `Live Tauri supervision failed, so the manager app fell back to static data. ${detail}`,
      );
    }
  }
}

export function createServiceSupervisor(): ServiceSupervisor {
  return new DesktopSupervisor();
}

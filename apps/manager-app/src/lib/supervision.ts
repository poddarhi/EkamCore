import { invoke } from "@tauri-apps/api/core";
import type {
  HealthResponse,
  TodayResponse,
  VersionResponse,
} from "@ekamcore/shared-types";
import { backendHealthBaseline, backendVersionBaseline } from "./backendBaseline";

const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8808";
const DEMO_WORKSPACE_ID = "personal";

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

export type BackendSlice = {
  baseUrl: string;
  workspaceId: string;
  status: StatusTone;
  connectionLabel: string;
  health?: HealthResponse;
  version?: VersionResponse;
  today?: TodayResponse;
  error?: string;
};

export type BaseSupervisionSnapshot = {
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

export type SupervisionSnapshot = BaseSupervisionSnapshot & {
  backend: BackendSlice;
};

export interface ServiceSupervisor {
  getSnapshot(): Promise<SupervisionSnapshot>;
}

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function managerBackendBaseUrl() {
  const configured = import.meta.env.VITE_EKAMCORE_BACKEND_BASE_URL?.trim();
  if (!configured) {
    return DEFAULT_BACKEND_BASE_URL;
  }

  return configured.replace(/\/+$/, "");
}

function makeUrl(baseUrl: string, path: string) {
  return new URL(path.replace(/^\//, ""), `${baseUrl}/`).toString();
}

async function fetchJson<T>(url: string) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

function upsertDiagnostic(
  diagnostics: DiagnosticFact[],
  nextDiagnostic: DiagnosticFact,
) {
  return [
    ...diagnostics.filter((diagnostic) => diagnostic.label !== nextDiagnostic.label),
    nextDiagnostic,
  ];
}

function upsertSetting(settings: SettingFact[], nextSetting: SettingFact) {
  return [
    ...settings.filter((setting) => setting.label !== nextSetting.label),
    nextSetting,
  ];
}

async function fetchBackendSlice(): Promise<BackendSlice> {
  const baseUrl = managerBackendBaseUrl();

  const [healthResult, versionResult, todayResult] = await Promise.allSettled([
    fetchJson<HealthResponse>(makeUrl(baseUrl, "/v1/health")),
    fetchJson<VersionResponse>(makeUrl(baseUrl, "/v1/version")),
    fetchJson<TodayResponse>(
      makeUrl(baseUrl, `/v1/workspaces/${DEMO_WORKSPACE_ID}/today`),
    ),
  ]);

  const health =
    healthResult.status === "fulfilled" ? healthResult.value : undefined;
  const version =
    versionResult.status === "fulfilled" ? versionResult.value : undefined;
  const today = todayResult.status === "fulfilled" ? todayResult.value : undefined;

  const errors = [healthResult, versionResult, todayResult]
    .filter((result): result is PromiseRejectedResult => result.status === "rejected")
    .map((result) =>
      result.reason instanceof Error ? result.reason.message : String(result.reason),
    );

  const status: StatusTone =
    health && version && today
      ? "healthy"
      : health || version || today
        ? "warning"
        : "attention";

  return {
    baseUrl,
    workspaceId: DEMO_WORKSPACE_ID,
    status,
    connectionLabel:
      status === "healthy"
        ? "Live backend slice connected"
        : status === "warning"
          ? "Partial backend connectivity"
          : "Backend unavailable",
    health,
    version,
    today,
    error: errors.length > 0 ? errors.join(" | ") : undefined,
  };
}

function withBackendSlice(
  baseSnapshot: BaseSupervisionSnapshot,
  backend: BackendSlice,
): SupervisionSnapshot {
  const isLive = backend.status === "healthy";
  const isPartial = backend.status === "warning";

  const setupChecks = baseSnapshot.setupChecks.map((check) => {
    if (check.id !== "backend-stub") {
      return check;
    }

    if (isLive && backend.today) {
      return {
        ...check,
        status: "healthy" as const,
        detail: `FastAPI stub responded from ${backend.baseUrl} and returned the ${backend.workspaceId} workspace Today payload.`,
        nextStep: `Live demo loaded ${backend.today.data.cards.length} Today cards from the backend stub.`,
      };
    }

    if (isPartial) {
      return {
        ...check,
        status: "warning" as const,
        detail: `Manager app reached part of the backend slice at ${backend.baseUrl}, but not every expected endpoint responded.`,
        nextStep: backend.error ?? "Verify the backend is running and the Today stub route is reachable.",
      };
    }

    return {
      ...check,
      status: "attention" as const,
      detail: `Manager app could not reach the backend at ${backend.baseUrl}.`,
      nextStep: `Run pnpm dev:backend and keep the stub service listening on ${backend.baseUrl}.`,
    };
  });

  const services = baseSnapshot.services.map((service) => {
    if (service.id !== "backend" && service.id !== "service-backend") {
      return service;
    }

    if (isLive && backend.health) {
      return {
        ...service,
        status: "healthy" as const,
        detail: backend.health.data.summary,
        actionHint: `Live demo workspace '${backend.workspaceId}' returned ${backend.today?.data.cards.length ?? 0} Today cards from ${backend.baseUrl}.`,
      };
    }

    if (isPartial) {
      return {
        ...service,
        status: "warning" as const,
        detail: `Partial backend connectivity at ${backend.baseUrl}.`,
        actionHint:
          backend.error ??
          "Check the backend process and confirm every stub endpoint is reachable.",
      };
    }

    return {
      ...service,
      status: "attention" as const,
      detail: `Backend is not reachable at ${backend.baseUrl}.`,
      actionHint: `Start pnpm dev:backend so the manager app can load the live slice.`,
    };
  });

  let diagnostics = upsertDiagnostic(baseSnapshot.diagnostics, {
    label: "Backend base URL",
    value: backend.baseUrl,
    tone: isLive ? "healthy" : isPartial ? "warning" : "attention",
  });

  diagnostics = upsertDiagnostic(diagnostics, {
    label: "Backend API version",
    value: backend.version?.data.apiVersion ?? backendVersionBaseline.data.apiVersion,
    tone: backend.version ? "healthy" : "warning",
  });

  diagnostics = upsertDiagnostic(diagnostics, {
    label: "Contract version",
    value:
      backend.version?.data.contractVersion ??
      backendVersionBaseline.data.contractVersion,
    tone: backend.version ? "healthy" : "warning",
  });

  let settings = upsertSetting(baseSnapshot.settings, {
    label: "Backend base URL",
    value: backend.baseUrl,
    detail:
      "Manager-app live polling target for Sprint 0 health, version, and Today requests.",
  });

  settings = upsertSetting(settings, {
    label: "Demo workspace",
    value: backend.workspaceId,
    detail:
      "The thin vertical slice uses the personal workspace route so clients can exercise explicit workspace scoping early.",
  });

  const logs = [
    ...baseSnapshot.logs,
    {
      id: "backend-live-slice",
      level: isLive ? "info" : isPartial ? "warning" : "error",
      source: "backend",
      message: isLive
        ? `Live stub endpoints responded from ${backend.baseUrl}.`
        : `Live backend slice is not fully reachable at ${backend.baseUrl}. ${backend.error ?? "Start pnpm dev:backend."}`,
    },
  ] as LogEntry[];

  const activity = [...baseSnapshot.activity];
  const liveSliceMessage = isLive
    ? "Thin end-to-end slice is live: manager app -> FastAPI stub -> generated contract types."
    : "Thin end-to-end slice is ready, but the manager app still needs the backend process to stay running.";

  if (!activity.includes(liveSliceMessage)) {
    activity.unshift(liveSliceMessage);
  }

  return {
    ...baseSnapshot,
    source: `${baseSnapshot.source}${isLive ? " + backend-live" : isPartial ? " + backend-partial" : " + backend-unreachable"}`,
    summary: isLive
      ? `Thin end-to-end slice is live across the manager app, contract types, and FastAPI stubs at ${backend.baseUrl}.`
      : baseSnapshot.summary,
    nextIntegration: isLive
      ? "Add auth/session enforcement and workspace-aware request context on top of this live slice."
      : "Start the FastAPI stub backend so the manager app can switch from structural supervision to the live demo path.",
    setupChecks,
    services,
    diagnostics,
    settings,
    logs,
    activity,
    backend,
  };
}

function buildFallbackSnapshot(message?: string): BaseSupervisionSnapshot {
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
    let baseSnapshot: BaseSupervisionSnapshot;

    if (!isTauriRuntime()) {
      baseSnapshot = buildFallbackSnapshot();
    } else {
      try {
        baseSnapshot = await invoke<BaseSupervisionSnapshot>(
          "get_supervision_snapshot",
        );
      } catch (error) {
        const detail =
          error instanceof Error ? error.message : "Unknown Tauri invoke failure.";
        baseSnapshot = buildFallbackSnapshot(
          `Live Tauri supervision failed, so the manager app fell back to static data. ${detail}`,
        );
      }
    }

    try {
      const backend = await fetchBackendSlice();
      return withBackendSlice(baseSnapshot, backend);
    } catch (error) {
      const detail =
        error instanceof Error ? error.message : "Unknown backend fetch failure.";

      return withBackendSlice(baseSnapshot, {
        baseUrl: managerBackendBaseUrl(),
        workspaceId: DEMO_WORKSPACE_ID,
        status: "attention",
        connectionLabel: "Backend unavailable",
        error: detail,
      });
    }
  }
}

export function createServiceSupervisor(): ServiceSupervisor {
  return new DesktopSupervisor();
}

import type { HealthResponse, VersionResponse } from "@ekamcore/shared-types";

export const backendHealthBaseline: HealthResponse = {
  meta: {
    requestId: "0cb3b62f-b172-46e4-8b2f-1ed65bbf8f8a",
    generatedAt: "2026-03-15T14:30:00Z",
    stub: true,
  },
  data: {
    status: "ok",
    summary: "Backend stub routes are aligned to the Sprint 0 contract and ready for client integration.",
    checks: [
      {
        name: "health_route",
        status: "ok",
        detail: "The FastAPI skeleton exposes a contract-shaped health payload.",
      },
      {
        name: "workspace_summary_routes",
        status: "ok",
        detail: "Today and Recap stubs are explicit workspace-scoped routes.",
      },
      {
        name: "job_status_polling",
        status: "planned",
        detail: "Polling exists now; real async jobs will replace static fixtures later.",
      },
    ],
  },
};

export const backendVersionBaseline: VersionResponse = {
  meta: {
    requestId: "3e6cb3dc-7cd7-4efa-b350-4849f237a2d3",
    generatedAt: "2026-03-15T14:30:00Z",
    stub: true,
  },
  data: {
    applicationVersion: "0.1.0-sprint0",
    apiVersion: "v1",
    contractVersion: "0.1.0-sprint0",
    buildChannel: "local-dev",
  },
};

# Workspace Scoping Rules

This note operationalizes ADR 0004 for the current API and for new routes added after Sprint 0.

## Core Principle

Workspace membership is a server-side authorization boundary. Clients may suggest context, but they do not define it.

## Route Classes

### Global Routes

Global routes are intentionally few and should not expose workspace content.

Current examples:

- `GET /v1/health`
- `GET /v1/version`

Likely future global routes:

- login
- refresh
- logout
- account/session management routes that are scoped to the authenticated user rather than a workspace payload

### Workspace-Scoped Routes

Workspace routes must carry an explicit workspace identifier in the path unless a reviewed alternative is documented.

Current examples:

- `GET /v1/workspaces/{workspaceId}/today`
- `GET /v1/workspaces/{workspaceId}/recap`
- `GET /v1/workspaces/{workspaceId}/jobs/{jobId}`

## Server Rules

- Every workspace-scoped request must resolve the authenticated user first.
- The server must verify the user is a member of the requested workspace before loading content.
- Job polling must verify both workspace membership and that the job belongs to the same workspace.
- Personal workspaces and shared workspaces use the same API boundary rule even if internal storage differs.
- Cross-workspace aggregation must not be smuggled into a workspace route; it needs an explicit reviewed route and contract update.

## Client Rules

- The Sprint 0 manager-app live slice uses the `personal` workspace only as a fixed demo path.
- Later clients may remember a current workspace for UX, but they must still send explicit workspace identifiers to the API.
- Clients must not filter unauthorized data client-side as a substitute for server checks.

## Response and Logging Rules

- Workspace-scoped responses may echo `meta.workspaceId` for debugging and traceability.
- Global routes should omit `meta.workspaceId`.
- Structured logs and job records should include workspace identifiers when the route is workspace-bound.

## Contract Review Checklist for New Routes

- Is the route global or workspace-scoped?
- If workspace-scoped, is the workspace identifier explicit in the path?
- If global, is there a clear reason it must not belong to a workspace?
- Does the route leak cross-workspace counts, names, or suggestions indirectly?
- Are background jobs and exported artifacts tied back to the same workspace boundary?

## Follow-up Implementation Work

- add membership enforcement middleware once auth/session work begins
- classify every new route during OpenAPI review
- keep manager-app diagnostics honest about which demo data is fixed to the `personal` workspace

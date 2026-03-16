# ADR 0004: Workspace Scoping at the API Boundary

- Status: Accepted
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: S0-022, Sprint 1 workspace enforcement
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/adr/0003-auth-session-model.md`, `/Users/hiteshpoddar/EkamCore/docs/workspace-scoping-rules.md`

## Context

EkamCore supports both personal and shared workspaces in v1. The functional and API documents make workspace scoping a product-level requirement, not an internal implementation preference. Content access, suggestion access, and mutation behavior must respect workspace boundaries consistently.

## Decision

Workspace content endpoints are scoped at the API boundary unless they are explicitly global by design. Every request that accesses workspace content must enforce authenticated user identity, role, membership, and source-derived visibility rules.

## Decision Drivers

- Personal and shared workspaces are part of the v1 product boundary.
- Suggestion and graph surfaces must not leak content across workspace boundaries.
- API-level enforcement is easier to reason about than relying on client behavior.

## Consequences

### Positive

- Establishes a clear line between global and workspace-scoped routes before the API grows.
- Gives backend and client teams a stable rule for routing and authorization.

### Tradeoffs

- Route design needs more discipline early, including explicit workspace identifiers.
- Some endpoints need careful classification so “global” does not become a loophole.

## Alternatives Considered

### Client-Side Workspace Filtering

- Considered because it can feel faster in early UI work.
- Rejected because it is not a valid security boundary and would risk leakage across users or workspaces.

### Implicit Current Workspace Context Only

- Considered as a simplification for mobile and web clients.
- Not selected as the primary rule because explicit workspace scoping is clearer and safer for API evolution.

## Follow-up Work

- Document which endpoints are workspace-scoped and which are global.
- Apply the rule consistently in auth middleware and route design.

## Notes

This ADR defines the policy boundary. Individual endpoint details will be finalized in the API contract work.

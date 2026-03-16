# Contracts

This directory holds the canonical API contract artifacts for EkamCore.

## Source of Truth

- canonical OpenAPI file: `docs/contracts/ekamcore-api.yaml`
- contract notes and workflow: this directory
- generated TypeScript artifacts: `packages/shared-types`

This matches [ADR 0002](/Users/hiteshpoddar/EkamCore/docs/adr/0002-api-source-of-truth.md): the OpenAPI document is the reviewed source of truth, and clients consume generated shared types from it.

## Sprint 0 Scope

The initial Sprint 0 contract covers the first thin local API slice:

- global health and version endpoints
- workspace-scoped Today and Recap stub endpoints
- workspace-scoped job-status polling endpoint
- shared response envelope shapes and a problem envelope

The manager app now consumes the health, version, and Today routes directly in the Sprint 0 live demo path using `http://127.0.0.1:8808` by default and the `personal` workspace stub.

## Workflow

1. Edit `docs/contracts/ekamcore-api.yaml`.
2. Lint the contract:

```sh
pnpm lint:api
```

3. Regenerate the shared TypeScript package:

```sh
pnpm generate:shared-types
```

4. Update backend stubs in `apps/backend` in the same review cycle if the contract shape changed.

## Notes

- The contract is intentionally conservative in Sprint 0: it is stub-first, explicit about workspace-scoped routes, and ready for generated TS consumption before richer feature work begins.
- Auth/session enforcement will layer on after the Sprint 0 note in `S0-021`; the initial stub routes focus on payload shape and endpoint boundaries.
- The root-level `security: []` is a temporary Sprint 0 exception so the thin live slice can run before auth middleware is added.

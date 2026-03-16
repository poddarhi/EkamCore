# ADR 0002: API Source of Truth and Generated Shared Types

- Status: Accepted
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: S0-011, S0-012, S0-013, S0-014
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/contracts/README.md`

## Context

EkamCore needs backend, manager app, and mobile work to proceed in parallel without payload drift. The product and API contract documents explicitly require one canonical contract source plus generated shared artifacts so that request and response shapes, card unions, auth/session flows, and job status payloads stay aligned.

## Decision

The canonical API contract source for EkamCore v1 is an OpenAPI 3.1 specification file at `docs/contracts/ekamcore-api.yaml`. Generated shared TypeScript types and, where useful, client helpers will be produced from that contract into `packages/shared-types`. Server models must be generated from or explicitly aligned to the same contract.

## Decision Drivers

- Parallel backend and client development must not drift on payload shape.
- Card unions, action envelopes, and job status contracts need one typed baseline.
- Shared contract generation reduces duplicate manual client models.

## Consequences

### Positive

- Gives the team a single place to review and version API changes.
- Makes generated shared types a normal part of development instead of an afterthought.

### Tradeoffs

- Contract changes now require discipline and regeneration work in the same review cycle.
- Poorly maintained code generation would create false confidence, so tooling and validation need to be part of Sprint 0.

## Alternatives Considered

### Hand-Maintained Client Types

- Considered because it is faster to start for a single prototype.
- Rejected because it guarantees drift once backend, manager app, and mobile work move in parallel.

### Backend Code as the Only Contract

- Considered because FastAPI and Pydantic can emit schemas from implementation.
- Not selected as the sole source because the canonical contract needs to be reviewable and stable before parallel client work expands.

## Follow-up Work

- Add `docs/contracts/ekamcore-api.yaml`.
- Add validation and linting for the OpenAPI file.
- Generate and consume shared TypeScript artifacts from the contract.

## Notes

This ADR is accepted because it is already a locked direction in the approved architecture and API documents, even though the repository implementation still needs to be added.

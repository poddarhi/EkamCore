# ADR 0001: Runtime Substrate for Local Hub Services

- Status: Proposed
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: S0-004, S0-005, S0-006
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/adr/README.md`

## Context

EkamCore v1 needs a repeatable local runtime strategy for the backend, data services, and future workers on an always-on Apple silicon Mac. The runtime substrate directly affects manager-app supervision, service startup and shutdown, health checks, update flow, repair actions, diagnostics, and support burden.

The product and architecture documents currently recommend hidden Docker Desktop orchestration as the most practical v1 path, but Sprint 0 still requires an explicit comparison against Homebrew plus LaunchAgents before the repository treats that path as accepted.

## Decision

The current proposed baseline is to use Docker Desktop as the hidden local runtime substrate behind the manager app for Mac-first v1, pending completion of the Sprint 0 runtime spike and final ADR acceptance.

## Decision Drivers

- The manager app needs a stable and scriptable way to start, stop, restart, and observe multiple services.
- The small team needs a pragmatic v1 path with lower orchestration complexity than bundling every dependency manually.
- Runtime choice affects updates, rollback, diagnostics, and support effort early, not only later.

## Consequences

### Positive

- Gives the manager app a clearer supervision target for multi-service orchestration.
- Makes it easier to reason about service boundaries, health, and repeatable local bootstrap behavior.

### Tradeoffs

- Docker Desktop introduces user-visible installation and licensing considerations.
- This decision may carry more overhead than a more Mac-native substrate, and it should be validated on the reference host rather than assumed.

## Alternatives Considered

### Homebrew Plus LaunchAgents

- Considered because it is familiar to technical Mac users and avoids Docker Desktop licensing constraints.
- Not yet selected because it exposes more lifecycle, dependency, and repair complexity directly to the team and possibly the user.

### Bundled Local Binaries

- Considered because it could reduce visible runtime dependencies for the user.
- Not selected for v1 because packaging and operating services like PostgreSQL and Qdrant inside the app would add significant complexity.

## Follow-up Work

- Complete the runtime substrate spike on the reference host.
- Update this ADR with measured observations and final acceptance or rejection.
- Add the bootstrap procedure once the selected runtime is locked.

## Notes

OrbStack remains a future evaluation candidate, but not the current v1 default.

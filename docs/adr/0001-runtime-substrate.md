# ADR 0001: Runtime Substrate for Local Hub Services

- Status: Proposed
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: S0-004, S0-005, S0-006
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/adr/README.md`

## Context

EkamCore v1 needs a repeatable local runtime strategy for the backend, data services, and future workers on an always-on Apple silicon Mac. The runtime substrate directly affects manager-app supervision, service startup and shutdown, health checks, update flow, repair actions, diagnostics, and support burden.

The product and architecture documents currently recommend hidden Docker Desktop orchestration as the most practical v1 path, but Sprint 0 still requires an explicit comparison against Homebrew plus LaunchAgents before the repository treats that path as accepted.

The v1 product decision should assume a clean user Mac, not a developer machine. That means neither Homebrew nor Docker Desktop should be treated as preinstalled. Homebrew may still be useful for engineering workflows, but it should not become a user-facing requirement by accident.

## Decision

The current proposed baseline is to use Docker Desktop as the hidden local runtime substrate behind the manager app for Mac-first v1, pending completion of the Sprint 0 runtime spike and final ADR acceptance.

## Decision Drivers

- The manager app needs a stable and scriptable way to start, stop, restart, and observe multiple services.
- The small team needs a pragmatic v1 path with lower orchestration complexity than bundling every dependency manually.
- Runtime choice affects updates, rollback, diagnostics, and support effort early, not only later.
- The end-user onboarding path should assume a clean Mac with no preinstalled package manager or runtime substrate.
- The runtime choice must account for host resource overhead, including memory usage, because EkamCore also plans to run local AI and background processing on the same machine.

## Consequences

### Positive

- Gives the manager app a clearer supervision target for multi-service orchestration.
- Makes it easier to reason about service boundaries, health, and repeatable local bootstrap behavior.

### Tradeoffs

- Docker Desktop introduces user-visible installation and licensing considerations.
- Docker Desktop consumes host resources, including memory, before EkamCore workloads are layered on top.
- This decision may carry more overhead than a more Mac-native substrate, and it should be validated on the reference host rather than assumed.

## Alternatives Considered

### Homebrew Plus LaunchAgents

- Considered because it is familiar to technical Mac users and avoids Docker Desktop licensing constraints.
- Not yet selected because it exposes more lifecycle, dependency, and repair complexity directly to the team and would also make Homebrew an accidental end-user requirement unless the product added more custom installation logic.

### Bundled Local Binaries

- Considered because it could reduce visible runtime dependencies for the user.
- Not selected for v1 because packaging and operating services like PostgreSQL and Qdrant inside the app would add significant complexity.

## Follow-up Work

- Complete the runtime substrate spike on the reference host.
- Update this ADR with measured observations and final acceptance or rejection.
- Record the clean-machine onboarding assumption explicitly if Docker Desktop is accepted.
- Capture Docker Desktop memory and startup overhead in the performance truth table.
- Add the bootstrap procedure once the selected runtime is locked.

## Notes

OrbStack remains a future evaluation candidate, but not the current v1 default.

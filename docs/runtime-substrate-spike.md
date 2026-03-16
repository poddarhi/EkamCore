# Runtime Substrate Spike

Sprint task: `S0-004`  
Date: 2026-03-15

## Purpose

This note records the Sprint 0 comparison between the two runtime substrate paths called out in the product and architecture documents:

- hidden Docker Desktop orchestration behind the manager app
- Homebrew-managed services with LaunchAgents

The goal is not to finalize the ADR yet. The goal is to capture real operational observations from the reference Mac so `S0-005` can lock the decision with evidence instead of preference.

## Decision Framing Correction

One important distinction became clear during the spike: the reference Mac used for evaluation is not the same thing as the default end-user starting point.

For v1 product decisions, the team should assume a clean user Mac where:

- Homebrew is not preinstalled
- Docker Desktop is not preinstalled
- the user may need guided setup for privileged install steps

This means the runtime decision needs to optimize for two things at once:

- engineering operability for a small team shipping a multi-service local product
- honest, guided onboarding for a user who is not already running the supporting stack

Homebrew remains useful for developer workflows and for comparing substrate options, but it should not be treated as a required end-user dependency.

## Reference Host

Observed on this machine:

- Model: MacBook Air (`Mac16,12`)
- Chip: Apple M4
- CPU: 10 cores
- Memory: 24 GB
- Architecture: Apple silicon

This matches the documented reference profile closely enough for Sprint 0 runtime evaluation.

## Option A: Docker Desktop as Hidden Runtime Substrate

### What Was Observed

- Docker Desktop was installed on the reference Mac via Homebrew cask.
- The installed app footprint is about `2.4G` in `/Applications/Docker.app`.
- Docker CLI became available after Docker Desktop setup completed.
- Observed CLI version: `Docker version 29.2.1`
- Observed Compose plugin version: `Docker Compose version v5.1.0`
- Observed active context list:

```text
NAME              DESCRIPTION                               DOCKER ENDPOINT                                      ERROR
default           Current DOCKER_HOST based configuration   unix:///var/run/docker.sock
desktop-linux *   Docker Desktop                            unix:///Users/hiteshpoddar/.docker/run/docker.sock
```

- User-observed engine info after startup:

```text
29.2.1|Docker Desktop|linux|aarch64
```

- During installation, Homebrew needed an admin-password step to create `/usr/local/cli-plugins` and link the Compose plugin.
- The resulting plugin path is rooted in a system-owned directory:

```text
/usr/local/cli-plugins/docker-compose -> /Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose
```

### Operational Implications

#### Setup Complexity

- Installation is not zero-friction. It required a large app install, first-run setup, and an admin-password step.
- This is still manageable for the target v1 audience, but it must be treated as part of onboarding truth, not hidden magic.

#### Memory and Host Resource Impact

- Docker Desktop on macOS runs a Linux runtime layer rather than using the host kernel directly, so it does consume host memory even before EkamCore services do meaningful work.
- That memory overhead is real and must be treated as part of the v1 performance budget, especially because EkamCore also plans to run local AI, embeddings, OCR, and photo/background processing on the same machine.
- The exact idle and loaded memory footprint still needs to be measured in `S0-019` and `S0-020`; this spike only confirms that the overhead exists and should not be hand-waved away.

#### Service Supervision

- Docker Desktop gives the manager app a cleaner substrate for multi-service orchestration than raw per-service process management.
- Container lifecycle, health checks, grouped startup, and grouped shutdown are easier to model behind one supervision adapter.

#### Update and Rollback

- Versioned images and compose-style definitions are easier to pin, roll forward, and roll back than a collection of host-installed formulas.
- This fits the manager-app requirement for controlled update and repair flows better than ad hoc service installs.

#### Diagnostics

- Docker gives a stronger boundary around logs, container state, and service topology.
- The manager app can reason about “stack health” more directly than it can with a scattered set of host processes.

#### Support Burden

- For a small team, Docker Desktop reduces the number of custom service-lifecycle problems the manager app has to solve itself.
- The tradeoff is that Docker Desktop itself becomes a dependency the team must support in documentation and troubleshooting.

#### Known Tradeoffs

- Requires Docker Desktop installation and first-run setup.
- Requires admin involvement during install on this host.
- Adds non-trivial disk footprint.
- Carries Docker Desktop licensing considerations that must be documented clearly.

## Option B: Homebrew Services Plus LaunchAgents

### What Was Observed

- This Mac already has a real Homebrew-managed service running:

```text
Name   Status   User          File
mysql  started  hiteshpoddar  ~/Library/LaunchAgents/homebrew.mxcl.mysql.plist
```

- The LaunchAgent exists at:

```text
/Users/hiteshpoddar/Library/LaunchAgents/homebrew.mxcl.mysql.plist
```

- `launchctl print` shows a concrete, inspectable process model:
  - label: `homebrew.mxcl.mysql`
  - program: `/opt/homebrew/opt/mysql/bin/mysqld_safe`
  - working directory: `/opt/homebrew/var/mysql`
  - state: `running`
  - properties include `keepalive` and `runatload`

### Operational Implications

#### Setup Complexity

- For an individual technical service, Homebrew plus LaunchAgents is straightforward and Mac-native.
- For a multi-service product stack, setup complexity grows quickly because each service becomes its own install, configuration, state, and repair path.
- This path may feel lighter for a developer machine that already has Homebrew, but it is not the right default assumption for a clean end-user Mac.

#### Service Supervision

- LaunchAgents provide OS-level process supervision, but not application-level stack orchestration.
- The manager app would need more custom logic to coordinate multiple services, aggregate health, and reason about dependencies between them.

#### Update and Rollback

- Homebrew upgrades are easy to run, but less controlled for a productized stack with multiple moving parts.
- Rollback is weaker and more manual than a containerized image-based path.
- Host-installed service upgrades may also be coupled to data-directory and formula changes that are harder to manage predictably.

#### Diagnostics

- LaunchAgents are inspectable with `brew services`, `launchctl`, and system logs.
- That is workable for technical operators, but it is more fragmented for a manager app trying to present one coherent product-level support surface.

#### Support Burden

- This approach looks simpler at the beginning, but it shifts more custom lifecycle and dependency handling onto the team.
- That makes it attractive for advanced or fallback paths, but heavier as the default product substrate for v1.

#### Known Tradeoffs

- More native to macOS and more transparent to technical users.
- Lower product dependency on Docker Desktop.
- Higher custom orchestration complexity for the EkamCore team.
- Harder to present as one clean, supportable, rollback-aware stack.

## Comparison Summary

| Area | Docker Desktop | Homebrew + LaunchAgents |
| --- | --- | --- |
| First-time setup on a clean user Mac | Heavier install, GUI app, admin prompt observed | Would also require Homebrew installation plus per-service setup |
| Multi-service orchestration | Stronger default fit | Requires more custom coordination |
| Health modeling | Better stack-level abstraction | More fragmented process-level inspection |
| Update flow | Better fit for versioned stack upgrades | More manual and formula-specific |
| Rollback | Better fit for controlled rollback | Weaker and more manual |
| Diagnostics | Stronger unified runtime boundary | More native but more scattered |
| Team support burden | Lower custom orchestration burden | Higher custom lifecycle burden |
| Memory overhead | Real VM/runtime overhead on host | Lower substrate overhead, but service footprint still accumulates |
| User dependency footprint | Larger and more opinionated | Smaller per service, but less cohesive |

## Recommendation for S0-005

The evidence from the reference Mac supports keeping Docker Desktop as the recommended v1 runtime substrate behind the manager app.

Reasoning:

- EkamCore is not a single daemon; it is a local multi-service stack.
- The manager app needs predictable grouped startup, grouped shutdown, health visibility, and repair behavior.
- For clean user machines, Homebrew plus LaunchAgents is not actually the simpler default path once Homebrew installation and per-service setup are counted honestly.
- Docker Desktop adds real onboarding, memory, and licensing caveats, but those caveats are easier to document and support than re-implementing a robust multi-service control plane on top of Homebrew and LaunchAgents during v1.

## Conditions on the Recommendation

If Docker Desktop is accepted in `S0-005`, the repository should document these truths explicitly:

- Homebrew is not a required end-user dependency for v1.
- Docker Desktop is a visible installation dependency in v1.
- The install path may require admin approval and first-run setup steps.
- Docker Desktop consumes host resources, including memory, before EkamCore workloads are added; the performance truth table must capture that honestly.
- Docker Desktop licensing constraints must be called out in user-facing and open-source distribution notes.
- The manager app should hide orchestration details, but not pretend the dependency does not exist.

## Open Follow-up Questions

- Measure Docker Desktop idle memory and startup overhead on the reference host and at least one lower profile host.
- Validate actual EkamCore service startup and health-loop behavior on Docker Desktop once the backend and service skeleton exist.
- Measure startup time, idle memory, and baseline responsiveness in `S0-019` and `S0-020`.
- Compare OrbStack later as a possible future alternative, but do not block Sprint 0 on that evaluation.

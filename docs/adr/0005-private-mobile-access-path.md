# ADR 0005: Private Mobile Access Path

- Status: Accepted
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: Sprint 3 mobile access work
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/adr/0003-auth-session-model.md`

## Context

Private Mobile Access is part of the core product promise. The approved product and architecture docs recommend Tailscale-first guided private networking as the v1 path because it gives the best practical balance between user setup complexity and real remote access to the local hub.

## Decision

EkamCore v1 uses a Tailscale-first approach for Private Mobile Access. Tailscale provides the private network route, but EkamCore still requires normal application authentication and workspace authorization on top of that route.

## Decision Drivers

- Mobile access is a core capability, not a later add-on.
- The team needs a pragmatic v1 remote path rather than inventing a custom networking stack.
- The trust boundary must remain clear: private network access does not replace app-level auth.

## Consequences

### Positive

- Gives the product a realistic remote-access story early.
- Simplifies the first remote path compared with building or supporting multiple networking options at launch.

### Tradeoffs

- Users need a Tailscale account in v1.
- The routing path depends on Tailscale infrastructure even though data processing and storage remain local.

## Alternatives Considered

### Manual WireGuard-Only Setup

- Considered for users who prefer a more self-managed networking story.
- Not selected as the primary v1 path because the setup burden is higher for the target audience.

### Building a Custom Remote Access Layer

- Considered in theory as a more integrated user experience.
- Rejected for v1 because it adds too much scope and security risk for a small team.

## Follow-up Work

- Document onboarding guidance in the manager app.
- Define mobile connectivity-state handling against this networking path.

## Notes

More self-hosted control-plane alternatives can still be explored in later versions without changing the v1 baseline.

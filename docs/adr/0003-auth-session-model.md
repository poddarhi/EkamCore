# ADR 0003: Local Auth and Session Model for v1

- Status: Accepted
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: S0-021, Sprint 1 auth work
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/adr/0004-workspace-scoping.md`, `/Users/hiteshpoddar/EkamCore/docs/auth-session-implementation-note.md`

## Context

EkamCore is a local-first product, but local network access and Tailscale access must not be treated as proof of trust. The functional, architecture, and API docs already define a local account model with application-layer authentication and session handling for both local and remote users.

## Decision

EkamCore v1 uses local account authentication with username or email plus password, secure session tokens with refresh behavior, and session invalidation support. The same authentication path applies on the local network and over Tailscale-based Private Mobile Access.

## Decision Drivers

- Network location is not a safe authorization shortcut.
- Mobile and web clients need one consistent auth/session model.
- Session invalidation is required for a credible local multi-user product.

## Consequences

### Positive

- Keeps security rules consistent regardless of how the user reaches the hub.
- Gives Sprint 1 a clear auth baseline before richer features are layered in.

### Tradeoffs

- Password and session management must be implemented earlier than some prototype teams might prefer.
- More advanced identity options such as passkeys or external providers remain out of scope for v1.

## Alternatives Considered

### Network-Only Trust

- Considered as a shortcut for a LAN-only local product.
- Rejected because it breaks the trust model for Tailscale access and does not provide proper user-level authorization.

### Delaying Session Invalidation

- Considered as a way to reduce Sprint 1 scope.
- Rejected because invalidation is part of the documented v1 security baseline.

## Follow-up Work

- Write the Sprint 1 auth/session implementation note.
- Add the concrete token strategy and lifecycle rules when auth implementation begins.

## Notes

Device-scoped session management, passkeys, and external identity providers remain future enhancements, not part of this v1 decision.

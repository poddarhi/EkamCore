# Auth and Session Implementation Note

This note captures the intended v1 auth/session shape for EkamCore after the Sprint 0 stub slice.

## Current Sprint 0 Exception

- The current OpenAPI contract leaves `security: []` at the root so the thin manager-to-backend demo can run before auth middleware exists.
- That exception applies only to the stub slice.
- Once auth work begins, workspace and user-facing product routes must move behind application-layer authentication even on the local network.

## v1 Goals

- Use one auth model for local web, mobile, and Tailscale-based private access.
- Do not trust LAN presence or Tailscale presence as proof of user identity.
- Support session refresh and explicit invalidation from day one of real auth rollout.

## Recommended Session Shape

### Account Identity

- Local account with username or email plus password.
- Passwords hashed with `Argon2id`.
- Unique account identifier carried through membership and audit records.

### Tokens

- Short-lived access token: target `15 minutes`.
- Long-lived refresh token: target `30 days`.
- Both tokens should be opaque random secrets stored hashed server-side rather than trusted purely client-side.
- Refresh tokens rotate on use and belong to a session family so logout or compromise can invalidate the family.

### Client Transport

- Local web UI: secure `HttpOnly` cookies once the browser-facing surface is formalized.
- Native mobile: OS keychain storage plus `Authorization` header transport.
- Manager app: can follow the browser/web-auth path initially because it is a local administrative shell, but it must still respect normal app auth rules once protected routes exist.

## Route Policy

### May Stay Global

- `GET /v1/health`
- `GET /v1/version`
- future auth bootstrap routes such as login, refresh, and logout

### Must Require Auth

- every workspace-scoped route
- people graph and suggestion surfaces
- write paths to calendar, reminders, contacts, or source connections
- administrative repair actions beyond safe diagnostics

## Session Invalidation Rules

- Logout invalidates the current refresh token and its active access window.
- Password change invalidates every active refresh token family for that account.
- Explicit admin or local-owner revocation invalidates target sessions immediately.
- Session state changes must be visible across local web and mobile access paths without relying on client cooperation.

## Browser Security Notes

- Cookie-based browser auth must include CSRF protection for state-changing routes.
- Login attempts need throttling and lockout/backoff rules even on a local deployment.
- Tailscale transport does not replace app auth; it only narrows network exposure.

## Implementation Sequence

1. Add account, password-hash, session, and refresh-token persistence models.
2. Add login, refresh, logout, and session list/revoke routes.
3. Add auth middleware and protect workspace-scoped routes first.
4. Update the OpenAPI contract so protected routes declare real auth requirements instead of the Sprint 0 temporary exception.
5. Add manager-app and mobile handling for expired sessions and re-auth prompts.

## Open Questions for Later

- whether v1 needs device labels for session management UI
- whether passkeys should be a post-v1 addition or a late-v1 enhancement
- how much admin-only control the manager app should expose for local multi-user support

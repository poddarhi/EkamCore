# Mobile Auth Flow

## Token Storage

| Token | Storage | Lifetime | Rationale |
|-------|---------|----------|-----------|
| Access token (JWT) | In-memory variable (`api/client.ts`) | 15 min | Never persisted to disk. Lost on app kill. |
| Refresh token | iOS Keychain via `react-native-keychain` | 7 days | Survives app restart. Protected by Secure Enclave. |

### Why Not AsyncStorage?

AsyncStorage is unencrypted and readable by jailbroken devices or device backups.
The refresh token grants long-lived access to the user's data, so it must be
stored in the system keychain where the OS enforces access control and encryption.

The access token is short-lived (15 min) and stored only in a JS variable — it
vanishes when the app process is killed, which is acceptable because the refresh
token can obtain a new one.

## Auth Flow

### Login

```
User enters email + password
  → POST /api/v1/auth/login
  → Response: { access_token, refresh_token }
  → Store access_token in memory (setAccessToken)
  → Store refresh_token in iOS Keychain (TokenManager.saveRefreshToken)
  → Decode JWT → build User object → update AuthContext state
  → Navigate to Today screen
```

### App Launch (Silent Refresh)

```
App mounts → AuthProvider useEffect
  → Load refresh_token from Keychain (TokenManager.loadRefreshToken)
  → If no token: show Login screen
  → POST /api/v1/auth/refresh (Bearer <refresh_token>)
  → If success: store new access_token, build User, show Today screen
  → If failure (401/network): clear tokens, show Login screen
```

### Auto-Refresh (Proactive)

The access token expires after 15 minutes. To avoid interrupting the user:

1. After login or successful refresh, `AuthService.needsRefresh(marginMs)` checks
   if the token expires within 60 seconds.
2. A timer (via `setTimeout`) fires 1 minute before expiry.
3. On fire: call `AuthService.refresh()`.
4. If refresh succeeds: schedule next timer from the new token's `exp`.
5. If refresh fails: clear state → user sees Login screen on next navigation.

This matches the web client behavior exactly.

### 401 Intercept (Reactive)

If any API call receives a 401 while an access token exists:

1. `apiFetch` calls the registered `refreshCallback` (one-shot, deduplicated).
2. If refresh succeeds: retry the original request with the new token.
3. If refresh fails: throw the 401 error → AuthContext clears state → Login screen.

Concurrent 401s share the same refresh promise to avoid thundering herd.

### Logout

```
User taps Sign Out
  → POST /api/v1/auth/logout (best-effort, ignore errors)
  → Clear access_token from memory
  → Clear refresh_token from Keychain
  → Navigate to Login screen
```

## Connectivity Considerations

The mobile client connects to the Mac hub via Tailscale. Auth requests may fail
due to network issues rather than invalid credentials.

| Scenario | Behavior |
|----------|----------|
| Network timeout on login | Show "Unable to connect" error, not "Invalid credentials" |
| Network timeout on refresh | Keep showing cached UI, retry on next interval |
| Hub sleeping (port closed) | ConnectivityManager detects `HUB_SLEEPING`, show banner |
| Airplane mode | ConnectivityManager detects `DISCONNECTED_*`, use cached data |

## Phase 2: Biometric Unlock

When the user has logged in at least once (refresh token exists in Keychain):

1. On app foreground (after background or cold start), show biometric prompt.
2. Use `react-native-keychain` with `accessControl: BIOMETRY_ANY_OR_DEVICE_PASSCODE`.
3. If biometric succeeds: load refresh token, perform silent refresh.
4. If biometric fails or is cancelled: show Login screen with email/password.
5. If biometric is not enrolled: skip biometric, go straight to silent refresh.

This provides quick re-entry without typing credentials, while the refresh token
rotation ensures the server can revoke access at any time.

### Keychain Configuration (Phase 2)

```typescript
await Keychain.setGenericPassword('refresh', token, {
  service: 'ekamcore.refresh_token',
  accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE,
  accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
});
```

- `BIOMETRY_ANY_OR_DEVICE_PASSCODE`: Face ID / Touch ID / device passcode
- `WHEN_UNLOCKED_THIS_DEVICE_ONLY`: token not included in backups or migration

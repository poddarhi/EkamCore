# EkamCore Mobile (React Native)

iOS companion app for the EkamCore local-first life assistant.
Connects to the EkamCore API running on the user's Mac via Tailscale.

## Phase 1 Architecture

### Connectivity Model

The mobile app operates in 6 connectivity states managed by `ConnectivityManager`:

| State | Meaning | UX |
|-------|---------|------|
| `CONNECTED` | API healthy, latency < 2s | Full functionality |
| `DEGRADED` | API responds, latency 2–10s | Extended timeouts, subtle indicator |
| `RECONNECTING` | Unreachable < 5 min | Spinner + "Reconnecting..." banner |
| `DISCONNECTED_CACHED` | Unreachable >= 5 min, cache available | Read-only from cache, amber banner |
| `DISCONNECTED_EMPTY` | Unreachable >= 5 min, no cache | Empty state with "Cannot reach hub" |
| `HUB_SLEEPING` | Tailscale up, API port closed | "Hub is sleeping" with wake instructions |

### Data Flow

```
┌──────────┐     Tailscale     ┌──────────┐
│  iPhone   │ ◄──────────────► │   Mac    │
│  (mobile) │    HTTPS/443     │  (hub)   │
└──────────┘                   └──────────┘
     │                              │
     │ apiFetch()                   │ FastAPI
     │ ──────────────────────────►  │ /api/v1/*
     │ ◄────────────────────────    │
     │   ResponseEnvelope           │
     │                              │
     │   On 401: silent refresh     │
     │   On timeout: retry 2x      │
     │   On disconnect: use cache   │
```

### Auth Flow

1. **Login:** `POST /auth/login` → access token (memory) + refresh token (Keychain)
2. **Auto-refresh:** Schedule refresh 1 min before JWT expiry
3. **401 intercept:** `apiFetch` attempts one silent refresh, retries original request
4. **Logout:** Clear memory token + Keychain + navigate to Login screen

### Screen Map (Phase 1)

| Screen | Data Source | Refresh | Cache |
|--------|-----------|---------|-------|
| Today | `GET /api/v1/today` | 5 min | Last successful response |
| Recap | `GET /api/v1/recap` | 1 hour | Per period+date |
| Login | `POST /api/v1/auth/login` | — | — |
| Settings | Local state + flags | 5 min (flags) | — |

### Type System

- `types/cards.ts` — Card discriminated union matching backend `ResponseEnvelope`
- `types/api.ts` — Request/response types for each endpoint
- `config/api.ts` — Base URL, per-connectivity-state timeouts, retry config

### Project Structure

```
src/
  api/              # API client with auth intercept and auto-refresh
    client.ts
  config/           # App configuration
    api.ts          # Base URL, timeouts, retry settings
  contexts/         # React contexts
    AuthContext.tsx  # Token management, login/logout/refresh
    ConnectivityContext.tsx  # Wraps ConnectivityManager for React
    FlagContext.tsx  # Feature flag state
  design-system/    # Shared UI components (mirrors web design system)
  navigation/       # React Navigation stack/tab definitions
    MainNavigator.tsx
  screens/          # Screen components
    LoginScreen.tsx
    TodayScreen.tsx
    PlaceholderScreen.tsx
  services/         # Non-React services
    ConnectivityManager.ts  # Health polling, 6-state connectivity
    TokenManager.ts         # Keychain storage for refresh token
  types/            # TypeScript type definitions
    api.ts          # Endpoint request/response types
    cards.ts        # Card union, payloads, ResponseEnvelope
```

### Development

```bash
# Install dependencies
cd apps/mobile && pnpm install

# iOS (requires Xcode + CocoaPods)
cd ios && pod install && cd ..
pnpm ios

# Run tests
pnpm test
```

### Key Decisions

- **No offline-first database.** Phase 1 uses simple response caching. Phase 2 may
  add WatermelonDB if offline editing is needed.
- **Tailscale required.** The app does not expose the API to the public internet.
  All connections go through Tailscale's encrypted mesh.
- **Keychain for refresh tokens.** Access tokens stay in memory only. Refresh
  tokens use `react-native-keychain` backed by iOS Keychain Services.
- **Design system parity.** Mobile components mirror the web design system tokens
  (colors, spacing, typography) for visual consistency.

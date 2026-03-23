---
name: ekamcore-mobile
description: Use when writing React Native code for the EkamCore mobile app — screens, navigation, caching, connectivity, or any code in the mobile/ directory. Covers iOS and Android specifics including VoiceOver, Dynamic Type, and SQLCipher.
---

# EkamCore Mobile Skill

**Always read Master SKILL.md first.** Load `references/design-tokens-reference.md` and `references/api-contract-summary.md`.

## Project Structure
```
mobile/
  src/
    screens/            # TodayScreen, RecapScreen, SearchScreen, PeopleScreen, PersonDetailScreen, ReviewQueueScreen, SettingsScreen, LoginScreen
    components/         # Cards (EventCard, ReminderCard, etc.), CardDetailSheet, ConfidenceBadge, ConnectivityBanner, ErrorBanner
    navigation/         # MainNavigator (bottom tabs), AuthStack, per-tab stacks
    api/                # ApiClient (wraps generated TS client), errorInterceptor
    services/           # ConnectivityManager, CacheManager (SQLCipher), TokenManager (react-native-keychain)
    contexts/           # AuthContext, FlagContext, ConnectivityContext
    design-system/      # tokens.ts (constants), adapted components
    utils/              # errorMessages.ts, dateFormat.ts
```

## Navigation Architecture (React Navigation v6+)
```
NavigationContainer
├── AuthStack (not authenticated)
│   └── LoginScreen
└── MainTabNavigator (authenticated)
    ├── TodayStack: TodayScreen → CardDetailSheet (modal)
    ├── RecapStack: RecapScreen
    ├── SearchStack: SearchScreen → ResultDetail → PhotoDetail / FileDetail
    ├── PeopleStack: PeopleScreen → PersonDetail, ReviewQueue
    └── SettingsStack: SettingsScreen → SourcesScreen
```
Each tab has own stack. Switching tabs preserves stack state. Double-tap scrolls to top.

## Connectivity State Machine (6 states)
- CONNECTED: normal. DEGRADED: latency 2-10s, amber banner. RECONNECTING: unreachable <5min, retry.
- DISCONNECTED_CACHED: >5min unreachable, show cached data with stale indicator.
- DISCONNECTED_EMPTY: no cache, full-screen error. HUB_SLEEPING: Tailscale reachable but API port closed.
- Poll /health every 10 seconds. Publish state changes via ConnectivityContext.

## SQLCipher Caching
- Key from react-native-keychain. Tables: today_cards, recap_items, recent_queries.
- On fetch success: store in cache. On fetch fail: serve from cache with stale indicator.
- TTLs: Today 4h, Recap 24h, Search 12h. LRU eviction at 100MB.
- On logout: DROP all tables, VACUUM, delete SQLite file, clear keychain.

## Critical Patterns
- All lists: FlatList (not ScrollView) for performance.
- All interactive elements: minimum 44x44px touch target.
- Card tap: opens CardDetailSheet (bottom sheet, 50% initial, draggable to full).
- Disabled tabs: gray icon, tap shows "Coming in a future update" bottom sheet.
- Flags: load from GET /api/v1/flags on launch + every 5min. Offline: use cached flags.
- Auth: access_token in memory. refresh_token in react-native-keychain. Auto-refresh on 401.
- Accessibility: accessibilityLabel on all interactive elements. Test with VoiceOver. Support Dynamic Type at 200%.

## Testing
- Framework: Jest + React Native Testing Library
- Run: `make test-mobile`

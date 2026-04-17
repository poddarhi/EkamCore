# Offline Behavior

The EkamCore mobile app caches data locally so you can still view recent
information when your phone cannot reach the hub. This page explains the
six connectivity states, cache rules, and security behavior.

## Connectivity states

The app continuously monitors the link to your hub and moves through six
states.

| State | Icon / Banner | Behavior |
|-------|---------------|----------|
| **CONNECTED** | None (normal operation) | All data is live. Requests go directly to the hub. |
| **DEGRADED** | Yellow banner: "Slow connection" | The hub is reachable but responses are taking longer than two seconds. The app shows live data but may feel sluggish. |
| **RECONNECTING** | Spinner: "Reconnecting..." | The hub became unreachable less than five minutes ago. The app retries every ten seconds and shows live data from the last successful fetch. |
| **DISCONNECTED_CACHED** | Orange banner: "Offline -- showing cached data" | The hub has been unreachable for more than five minutes. The app displays cached data with a stale indicator timestamp on each card. New requests are queued for when the connection returns. |
| **DISCONNECTED_EMPTY** | Full-screen error with retry button | The hub is unreachable and no cached data is available for the current view. This usually happens on a fresh install before the first sync. |
| **HUB_SLEEPING** | Gray banner: "Hub is asleep" | The hub responded with a sleep status code. Your Mac is in sleep mode or the lid is closed. Wake the Mac to restore service. |

State transitions happen automatically. You do not need to manually switch
modes.

## Cache TTLs

Each tab maintains its own cache with a time-to-live (TTL). Data older than
the TTL is shown with a stale indicator; it is not deleted until the next
successful refresh.

| Tab | TTL | Notes |
|-----|-----|-------|
| **Today** | 4 hours | Briefing cards refresh frequently throughout the day. |
| **Recap** | 24 hours | Yesterday's recap rarely changes, so a longer TTL is used. |
| **Search** | 30 minutes | Search results depend on the query and index state, so they expire quickly. |
| **People** | 4 hours | Same TTL as Today. Profile edits sync immediately when connected. |
| **Settings** | Not cached | Settings always require a live connection to save changes. |

## How caching works

1. Every successful response from the hub is written to an encrypted
   on-device cache stored in the app's sandbox.
2. When the app enters a disconnected state it reads from this cache.
3. Stale data is marked with a timestamp showing when it was last fetched,
   for example "Last updated 45 minutes ago".
4. When connectivity returns, the app refreshes all visible data and
   replaces stale cache entries.

## Queued actions

Actions you take while offline -- such as dismissing a Today card -- are
queued locally. When the connection is restored the queue replays in order.
If a queued action conflicts with a server-side change, the server state
wins and you see a brief notification explaining the conflict.

## Secure wipe on logout

When you tap **Settings > Log Out**, the app performs a secure wipe:

1. Session token is deleted from the iOS keychain.
2. All cached data is deleted from the encrypted sandbox.
3. Biometric credentials are revoked.
4. The app returns to the **Connect to Hub** screen.

No EkamCore data remains on the device after logout.

## Reducing cache size

If storage is a concern, go to **Settings > Cache Size** and choose a
lower limit. The app evicts the oldest entries first when the limit is
reached. The minimum cache size is 50 MB; the default is 500 MB.

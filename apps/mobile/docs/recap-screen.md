# Recap Screen (S06-002)

Planned React Native screen for browsing past days or weeks.
Maps to `RecapStack → RecapScreen` in the main tab navigator.

## Data Source

`GET /api/v1/recap?workspace_id=<uuid>&period=daily|weekly&date=YYYY-MM-DD`

Returns a `ResponseEnvelope`. Cards are `EventCard`, `ReminderCard` (completed
and overdue variants). The screen groups cards into `RecapSection[]` by date
before passing them to `SectionList`.

- **Daily**: one section for the selected date.
- **Weekly**: seven sections (Mon → Sun) for the 7-day window ending on the
  selected date. Empty days are omitted.

Cache TTL: 24 h (SQLCipher local cache). The backend caches 1 h in Redis.

## Layout

```
┌──────────────────────────────────────────────────┐
│  ← Back   Recap              [Daily] [Weekly]    │  ← navigation header
│                                                  │
│  < Apr 7, 2026 >                                 │  ← date navigator
│                                                  │
│  ── Monday, Apr 6 ─────────────────────── (sticky│
│  [ EventCard: Team standup                     ] │
│  [ ReminderCard: ✓ Send weekly report          ] │
│  [ ReminderCard: ⚠ Overdue: submit expense     ] │
│                                                  │
│  ── Tuesday, Apr 7 ─────────────────────── (sticky│
│  [ EventCard: 1:1 with manager                 ] │
│  [ ReminderCard: ✓ Review PR #42               ] │
│                                                  │
│  ── (pull to refresh) ──────────────────────────  │
└──────────────────────────────────────────────────┘
         ↓ tap card ↓
┌──────────────────────────────────────────────────┐
│  ╔══════════════════════════════════════════╗    │
│  ║  CardDetailSheet (bottom sheet)          ║    │
│  ║  • drag handle at top                    ║    │
│  ║  • 50 % initial height, draggable to     ║    │
│  ║    full screen                           ║    │
│  ╚══════════════════════════════════════════╝    │
└──────────────────────────────────────────────────┘
```

## Component Breakdown

### Header
- Period toggle: segmented control (`Daily` / `Weekly`). Changing period resets
  date to yesterday and re-fetches.
- Placed in `navigationOptions` so it stays fixed while the list scrolls.

### Date Navigator
- Previous / Next chevrons + label ("Apr 7, 2026" or "Week of Apr 1–7, 2026").
- Max date: yesterday (UTC). Future dates are disabled.
- Tapping the label opens a modal date picker (daily) or week picker (weekly).

### SectionList
- `sections`: `RecapSection[]` derived from the `ResponseEnvelope` cards.
- `renderSectionHeader`: sticky date label with day-of-week + short date.
  Section headers are sticky (`stickySectionHeadersEnabled={true}`).
- `renderItem`: `<CardRenderer card={item} onPress={openDetailSheet} />` — same
  `CardRenderer` used by TodayScreen.
- `keyExtractor`: card `id` (UUID v7).
- `ListEmptyComponent`: `<EmptyState message="Nothing to show for this period." />`
- `onRefresh` / `refreshing`: pull-to-refresh triggers manual re-fetch and cache
  invalidation for the current period + date.

### CardDetailSheet
- Reuse the shared `CardDetailSheet` bottom sheet component.
- Opens on card tap. Passes the full `Card` object.
- Initial snap point 50 %, draggable to 100 %.

## State

```ts
const [period, setPeriod]     = useState<RecapPeriod>('daily');
const [date, setDate]         = useState<string>(yesterdayISO());
const [sections, setSections] = useState<RecapSection[]>([]);
const [loading, setLoading]   = useState(false);
const [refreshing, setRefreshing] = useState(false);
const [error, setError]       = useState<string | null>(null);
const [selectedCard, setSelectedCard] = useState<Card | null>(null);
```

## Fetch Logic

```
onMount / period change / date change:
  setLoading(true)
  try:
    envelope = await apiClient.getRecap({ workspace_id, period, date })
    setSections(groupCardsIntoSections(envelope.cards, period, date))
    writeToCache(period, date, envelope)   // TTL 24 h
  catch NetworkError:
    cached = readFromCache(period, date)
    if cached → setSections(cached), showStaleIndicator()
    else      → setError('No data available offline')
  finally:
    setLoading(false)
```

## Helper: groupCardsIntoSections

```ts
function groupCardsIntoSections(
  cards: Card[],
  period: RecapPeriod,
  dateISO: string,
): RecapSection[] {
  if (period === 'daily') {
    return [{ date: dateISO, title: formatDayLabel(dateISO), cards }];
  }
  // Weekly: bucket by card date, emit one section per day (skip empties)
  const buckets = new Map<string, Card[]>();
  for (const card of cards) {
    const d = cardDate(card); // extract YYYY-MM-DD from payload
    buckets.set(d, [...(buckets.get(d) ?? []), card]);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([d, dayCards]) => ({
      date: d,
      title: formatDayLabel(d),
      cards: dayCards.sort((a, b) => b.priority_score - a.priority_score),
    }));
}
```

## Accessibility

- Section headers: `accessibilityRole="header"`.
- Period toggle: `accessibilityLabel="Period: Daily"` / `"Period: Weekly"`.
- Date chevrons: `accessibilityLabel="Previous day"` / `"Next day"`.
- Dynamic Type at 200 %: use `Text` with `allowFontScaling={true}` (default).
- VoiceOver reads cards in list order (date asc, priority desc within day).

## Connectivity

Follows standard connectivity state machine:

| State | Behavior |
|---|---|
| CONNECTED | Normal fetch |
| DEGRADED | Fetch with amber banner |
| DISCONNECTED_CACHED | Serve SQLCipher cache, show stale indicator |
| DISCONNECTED_EMPTY | Full-screen error (`EmptyState`) |

## Feature Flag

`recap_enabled` — the endpoint returns 403 when the flag is off.
The tab icon renders as disabled (gray) and shows "Coming in a future update"
bottom sheet on tap when `useFlag('recap_enabled')` returns `false`.

# Search Screen (S09-002)

Planned React Native screen for searching across all EkamCore data types.
Maps to `SearchStack → SearchScreen` in the main tab navigator.

## Data Source

`GET /api/v1/search?q=<text>&workspace_id=<uuid>&type=<filter>&per_page=20&cursor=0`

Returns a `SearchResponse` with typed `Card[]`, `SearchFacets`, and
cursor-based `SearchPagination`.  See `src/types/search.ts` for all
request/response shapes.

Requires feature flag: `search_basic_enabled`.

---

## Layout

```
┌──────────────────────────────────┐
│  ┌────────────────────────┐  🔍 │  ← SearchBar (auto-focus on mount)
│  │ Search EkamCore...     │     │
│  └────────────────────────┘     │
│                                  │
│  [All] [Files] [Photos] [Events] │  ← FilterChips (horizontal scroll)
│  [Reminders] [Contacts]          │
│                                  │
│  ┌──────────────────────────────┐│
│  │ 📄 invoice-q1.pdf            ││  ← FileCard
│  │ Total amount due: $2,500     ││
│  │ Relevance: 0.87              ││
│  ├──────────────────────────────┤│
│  │ 📅 Team standup              ││  ← EventCard
│  │ Today 10:00 – 10:30 · Zoom  ││
│  ├──────────────────────────────┤│
│  │ 📸 Photo · Apr 10            ││  ← PhotoCard
│  │ San Francisco, CA            ││
│  └──────────────────────────────┘│
│                                  │
│  ── Loading more... ──           │  ← Infinite scroll indicator
└──────────────────────────────────┘
```

---

## Components

### SearchBar

- `TextInput` with magnifying glass icon and clear button.
- 300 ms debounce before firing API request (avoids thrashing on every keystroke).
- Auto-focuses on screen mount. Keyboard dismiss on scroll.
- Pressing Enter or the search icon triggers search immediately (bypasses debounce).
- Max input length: 200 characters (matches API validation).
- Accessibility: `accessibilityLabel="Search"`, `returnKeyType="search"`.

### FilterChips

- Horizontal `ScrollView` of pill-shaped chips for each `SearchTypeFilter` value.
- Single-select: tapping a chip sets `filters.type` and re-fetches.
- "All" chip is selected by default and visually distinguished.
- Chip counts: each chip shows the facet count in parentheses after the first
  search completes (e.g. "Files (12)").
- Design tokens: `colors.chipDefault`, `colors.chipActive`, `radius.pill`.

### Result Cards

Cards are rendered via a `renderItem` lookup on `card.type`:

| Type | Component | Key fields shown |
|------|-----------|------------------|
| `file` | `FileResultCard` | filename, snippet (highlighted), mime icon |
| `photo` | `PhotoResultCard` | thumbnail URL, taken_at, location_name |
| `event` | `EventResultCard` | title, start_at, location, calendar_name |
| `reminder` | `ReminderResultCard` | title, due_at, priority badge, overdue flag |
| `contact` | `ContactResultCard` | display_name, organization, email/phone |
| `person` | `ContactResultCard` | (same renderer) |

All cards are tappable and navigate to the relevant detail screen.

### FlatList with Infinite Scroll

```tsx
<FlatList
  data={results}
  renderItem={renderSearchCard}
  keyExtractor={(item) => item.id}
  onEndReached={loadMore}
  onEndReachedThreshold={0.4}
  ListHeaderComponent={<FilterChips />}
  ListEmptyComponent={<EmptyState />}
  ListFooterComponent={isLoadingMore ? <ActivityIndicator /> : null}
  keyboardDismissMode="on-drag"
/>
```

- `onEndReached` calls the API with `cursor = cursor + per_page` when
  `pagination.has_more` is true.
- Pages are appended to a local `results` array (not replaced).
- Pull-to-refresh resets cursor to 0 and replaces all results.

---

## States

### Loading (first fetch)

Full-screen centered `ActivityIndicator` with "Searching..." label below.
No cards or filter chips shown until first response.

### Empty (no results)

Illustration + message varies by active filter:

| Filter | Message |
|--------|---------|
| `all` | "No results found. Try different keywords." |
| `file` | "No documents match your search. Try different keywords or clear filters." |
| `photo` | "No photos match your search." |
| `calendar` | "No events found." |
| `reminder` | "No reminders found." |
| `contact` | "No contacts found." |

A "Clear filters" button appears when `type !== "all"`.

### Error

- Network error: "Could not reach EkamCore. Check your connection and try again."
  with a "Retry" button.
- 401/403: Redirect to login screen via `AuthContext`.
- 5xx / unknown: "Something went wrong." with a "Retry" button.
- Error state replaces the FlatList; filter chips remain visible.

### Loading More (pagination)

Small `ActivityIndicator` in `ListFooterComponent` while the next page loads.
If the next-page request fails, a "Tap to retry" footer replaces the spinner.

---

## Offline Behavior

When `ConnectivityContext.isConnected === false`:

1. **Banner**: `<ConnectivityBanner />` (already exists) slides in at the top
   of the screen with "You're offline — showing cached results".

2. **Cached results**: The search service checks `CachedSearchResult` in
   AsyncStorage (keyed by `query + JSON.stringify(filters)`).
   - If a cache hit exists and is < 24 hours old: display it.
   - If no cache hit: show the empty state with "Search requires a network
     connection." message (no "Clear filters" button).

3. **Search input**: Still editable. On submit, check cache first. If miss,
   show toast: "Search unavailable while offline."

4. **Pagination**: Disabled while offline. "Load more" footer hidden.

5. **Reconnection**: When connectivity restores, the current query is
   automatically re-fetched (replacing stale cache) if the user is still
   on the Search screen.

---

## Navigation

- Tab: `Search` (magnifying glass icon) in the bottom tab navigator.
- Stack: `SearchStack` contains `SearchScreen` → `SearchDetailScreen` (future).
- Deep link: `ekamcore://search?q=<query>` pre-fills the search bar and
  triggers a search on mount.

---

## Feature Flag

Gated on `search_basic_enabled`. When disabled, the Search tab shows
`PlaceholderScreen` with "Search coming soon" message.

---

## Related Files

| File | Purpose |
|------|---------|
| `src/types/search.ts` | Request, response, filter, cache type definitions |
| `src/types/cards.ts` | Card union type and payload interfaces |
| `src/screens/SearchScreen.tsx` | Main search screen (to be implemented) |
| `src/components/SearchBar.tsx` | Debounced search input (to be implemented) |
| `src/components/FilterChips.tsx` | Type filter pills (to be implemented) |
| `src/components/ConnectivityBanner.tsx` | Offline banner (exists) |
| `src/services/SearchService.ts` | API calls + cache layer (to be implemented) |

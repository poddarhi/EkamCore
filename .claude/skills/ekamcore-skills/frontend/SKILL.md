---
name: ekamcore-frontend
description: Use when writing React/TypeScript code for the EkamCore web UI — components, pages, design system, styling, routing, state management, API integration, or any code in the web/ directory. Also use for Storybook stories and web-specific tests.
---

# EkamCore Frontend Skill

**Always read Master SKILL.md first.** Load `references/design-tokens-reference.md` for visual specs and `references/api-contract-summary.md` for API shapes.

## Project Structure
```
web/
  src/
    design-system/
      tokens.css           # CSS custom properties (source of truth for all visual values)
      components/          # Button, Card, Input, Badge, StatusIndicator, Avatar, etc.
    pages/                 # TodayPage, RecapPage, SearchPage, PeoplePage, PersonDetailPage, PhotosPage, FilesPage, SettingsPage, LoginPage, NotFoundPage
    components/            # Shared: Sidebar, TopBar, ErrorBanner, ErrorToast, ConfidenceBadge, SourceList, SearchResultCard, FilterChips, CardSkeleton, EmptyState
    contexts/              # AuthContext (tokens+login+logout), FlagContext (feature flags), ConnectivityContext
    api/                   # Generated client from openapi/ + ApiClient wrapper + errorInterceptor
    utils/                 # errorMessages.ts (error_code→user text), dateFormat.ts
    App.tsx                # React Router routes + ProtectedRoute + FlagProvider
  tailwind.config.ts       # Extends theme with EkamCore tokens
  vite.config.ts
  package.json (pnpm)
```

## CRITICAL PATTERNS

### Page Component Pattern
```tsx
export default function TodayPage() {
  const { data, error, isLoading, mutate } = useSWR('/api/v1/today', fetcher, { refreshInterval: 300_000 });
  const flags = useFlags();

  if (!flags.today_enabled) return <FeatureComingSoon feature="Today" />;
  if (isLoading) return <CardSkeleton count={5} />;
  if (error) return <ErrorBanner message={error.userMessage} onRetry={() => mutate()} />;
  if (!data?.cards.length) return <EmptyState title="Your day will fill up soon" />;

  return <div className="space-y-3">{data.cards.map(card => <CardRenderer key={card.id} card={card} />)}</div>;
}
```

### Component Rules
1. ALL components use Tailwind classes mapping to design tokens. Never hardcode colors/sizes.
2. ALL interactive elements: keyboard accessible (tabIndex, onKeyDown for Enter/Space), focus ring (focus-visible:ring), aria-label for icon-only buttons.
3. ALL pages: loading skeleton → error banner → empty state → content. Always handle all 4 states.
4. ALL data fetching via useSWR with appropriate refreshInterval (Today: 5min, Recap: 1hr, Flags: 5min).
5. NO localStorage or sessionStorage. Use React state (useState/useContext) or SWR cache.
6. Auth tokens: access_token in memory (React ref). refresh_token as HttpOnly cookie (set by server).

### Feature Flag Gating (for pages)
```tsx
function FlaggedRoute({ flagKey, children }: { flagKey: string; children: React.ReactNode }) {
  const enabled = useFlag(flagKey);
  if (!enabled) return <FeatureComingSoon />;
  return <>{children}</>;
}
// In routes: <Route path="/photos" element={<FlaggedRoute flagKey="photos_enabled"><PhotosPage /></FlaggedRoute>} />
```

### Sidebar: disabled items visible but grayed out (shows product roadmap)
```tsx
<NavItem to="/photos" icon={Image} label="Photos" disabled={!flags.photos_enabled} disabledTooltip="Coming in a future update" />
```

### Error Display
- API error → errorInterceptor catches → throws ApiError with error_code
- Component catches → getUserMessage(error_code) from errorMessages.ts → renders ErrorBanner or ErrorToast
- 401 → auto-refresh (transparent). If fails → redirect to /login?returnTo={current}
- 429 → toast with countdown. Auto-retry after delay.
- 500 → ErrorBanner with correlation_id: "Something went wrong. Reference ID: {id}"

### Routes (React Router)
/, /today, /recap, /search, /people, /people/:id, /people/review, /photos, /photos/:id, /files, /files/:id, /settings, /settings/sources, /settings/photo-intelligence, /settings/account, /settings/about, /login, /* (404)

### People Graph Screens (SHIPPED — Sprint 13)
The full People Graph web surface lives under `apps/web/src`. All
pages gate on the `face_clustering_enabled` flag + an active
face-consent SWR hook (`useFaceConsent`) and fall through to
`FeatureComingSoon` / the consent CTA when either is missing.

Component dependency graph (the most common lookups):

- **Pages** — `src/pages/people/`
  - `PeopleListPage.tsx` — grid/list toggle, debounced search,
    confidence chips, multi-select list view (Cmd/Ctrl/Shift-click),
    floating merge action bar, History drawer trigger.
  - `PersonDetailPage.tsx` — header card with inline rename + kebab
    (Merge/Split/Delete), 4 tabs wired to URL hash, Faces management
    section with select-mode + "Split out" bar, delete modal,
    remove-face modal, and child `PhotoLightbox`.
  - `ReviewQueuePage.tsx` — useReducer session state, document-level
    keyboard shortcuts (Enter/R/S/N/1–5/←/→/?/Esc), optimistic
    auto-advance with rollback, batch reject/skip bar.
  - `OperationsHistoryPage.tsx` — stub; the `UndoDrawer` is the
    live surface.
- **Drawer / modals** — `src/components/people/`
  - `UndoDrawer.tsx`, `MergePersonsModal.tsx`, `SplitPersonModal.tsx`
  - `PersonAvatar.tsx` (wraps `design-system/Avatar`; size xl=80px
    falls back to `lg` rendering since the base component only
    supports up to `xl=80px` natively).
  - `TopBarPersonSearch.tsx` — document-level typeahead wired into
    `MainLayout` top bar, gated on consent.
- **Cards** — `src/components/cards/`
  - `PersonCard.tsx` — renders in `CardRenderer` (Today feed) and
    `SearchResultCard` (search results). Pass the `surface`
    prop (`"today"` / `"search"`) for metric attribution.
  - `PhotoCard.tsx` — now opens `PhotoLightbox` on click instead
    of its old inline 90vh modal.
- **Photo lightbox** — `src/components/photos/PhotoLightbox.tsx`
  - Full-screen viewer, measures image rendered rect on load +
    resize to align normalized bbox overlays.
- **API + hooks** — `src/api/people.ts`, `src/api/photos.ts`,
  `src/api/review_queue.ts`, `src/hooks/usePeople.ts`,
  `src/hooks/usePhotoFaces.ts`, `src/hooks/useUndoShortcut.ts`.

### Person Card Pattern
The backend emits a discriminated-union `Card` where
`type === "person"` carries a `PersonPayload`
(`apps/web/src/api/client.ts`):

```typescript
interface PersonPayload {
  source?: "trusted_person";           // route clicks to /people/:id
  person_id: string;
  display_name: string;
  avatar_url: string | null;
  context: "seen_recently" | "upcoming_event" | "catch_up" | "search_match";
  supporting_data?: Record<string, unknown>;
}
```

`CardRenderer.tsx` and `SearchResultCard.tsx` both delegate to
`PersonCard` when `payload.source === "trusted_person"`. Surface
attribution is a prop, not a React context:

```tsx
<CardRenderer card={c} surface="today" />
<SearchResultCard card={c} query={q} />   // internally surface="search"
```

Metrics fire from `PersonCard` itself — `personCard.clickedFromToday`
or `personCard.clickedFromSearch`. Add new context variants by
extending `contextDescription()` in `PersonCard.tsx` and adding a
`today.person.{context}` i18n key.

### Face Overlay Pattern (PhotoLightbox)
Bounding boxes arrive normalized `{x, y, w, h} ∈ [0,1]` from
`GET /api/v1/photos/:id/faces`. The lightbox draws one `<button>`
per face inside an absolutely-positioned wrapper that matches the
image's **rendered** bounding rect (not natural dimensions). The
pattern:

1. Store the `<img>` ref; on `onLoad` + `window.resize`, call
   `measure()` which reads `naturalWidth/Height` +
   `getBoundingClientRect()` of both image and container.
2. Translate the overlay wrapper into the image's position
   relative to the container (`transform: translate(offsetX, offsetY)`)
   and size it to `renderedW/H`.
3. Each bbox button uses percentage positioning inside the wrapper
   (`left: x*100%`, `width: w*100%`, etc.), so the same coordinate
   math works for any viewport.
4. `window.matchMedia('(prefers-reduced-motion: reduce)')` gates
   the fade; tests must stub `window.matchMedia`.

Reuse this pattern for any annotation-over-image UI (future
story: document highlight boxes in the Paperless viewer).

### Keyboard-First UX Pattern (reusable reference)
The `ReviewQueuePage` shortcut state machine is the canonical
pattern for future keyboard-heavy surfaces (Sprint 14 Pack cards,
timeline scrubbers, etc.):

- **Reducer owns the queue cursor**, not SWR. SWR is the source
  of truth for data; the reducer is the local session.
- **Optimistic advance + rollback**: `dispatch({type: "advance"})`
  first, then fire the API; on failure `dispatch({type: "rollback", clusterId})`
  and toast the error.
- **Document-level `keydown`** listener gated on `open/active`,
  with a skip-when-typing-in-input guard (`target.tagName === "INPUT"`
  or `isContentEditable`). Never attach to a focused element —
  the user must be able to drive the page without tabbing.
- **sr-only `aria-live="polite"` region** announces every action
  so the shortcuts are usable for screen reader users.
- **Always register shortcuts inside a `useEffect` keyed on
  enablement** so unmount cleans them up.

`useUndoShortcut` (`apps/web/src/hooks/useUndoShortcut.ts`)
extracts the same pattern as a hook for the Cmd/Ctrl+Z shortcut
wired into both `PeopleListPage` and `PersonDetailPage`. Copy the
hook shape when adding new global chords.

### Undo UX Pattern (dual path)
Every mutation on the People Graph has two undo affordances:

1. **Fast path — Cmd/Ctrl+Z via `useUndoShortcut`.** Calls
   `peopleApi.undoLast()` and revalidates every `/api/v1/people*`
   and `/api/v1/review-queue*` SWR key via `globalMutate` so the
   UI snaps back without per-page code.
2. **Browse path — `UndoDrawer`.** Right-side slide-out backed by
   `usePersonOperations(50)`. Each row summarises `forward_payload`
   via the `summarize(op)` helper and renders either an Undo
   button or a disabled "Undone" label. Clicks go through
   `peopleApi.undoOperation(id)` then the same cache revalidation.

When adding a new mutation: (a) make sure the service writes a
`person_operations` row with a concrete `inverse_payload`, (b)
add a branch to `_HANDLERS` / `_apply()` in
`apps/api/api/services/face/undo_service.py`, and (c) extend
`summarize()` in `UndoDrawer.tsx` so the drawer can describe the
action. No frontend plumbing changes are needed beyond the
summary.

### Photo lightbox entry points
Three callers mount the lightbox — all parent-owned state:
`PhotoCard` (Photos page + Search results via `SearchResultCard`),
`PersonDetailPage` Photos tab, and any future photo grid. The
pattern is the same: local `useState<string | null>` for the open
photo id, render a single `<PhotoLightbox>` at the tab/page root
with `open={openPhoto !== null}`. Never nest lightboxes.

### Styling Rules
- Use Tailwind utilities. Extend via tailwind.config.ts theme (not arbitrary values).
- Design system components in web/src/design-system/components/. Pages import from there.
- Max content width: 960px (max-w-[960px] mx-auto). Sidebar: 240px fixed.
- Responsive: sidebar collapses below 1024px. Single column below 768px.
- Dark mode: deferred to v1.1. Use CSS variables (tokens.css) so only token values change.
- Motion: --duration-normal (0.2s), --easing-default. Respect prefers-reduced-motion.

### Pack Card Components (SHIPPED — Sprint 14)
Three card types surface PLA pack output in the Today feed:

- **FollowUpCard** (`components/cards/FollowUpCard.tsx`) —
  UserPlus icon, person link, Done / Not now / Remind me later.
  Snooze opens `SnoozePicker` (tomorrow / 3 days / next week /
  custom date).
- **WeeklySummaryCard** (`components/cards/WeeklySummaryCard.tsx`)
  — Calendar icon, LLM summary text, stats row, top-persons
  avatar scroll, AI-generated badge, X dismiss.
- **RelationshipReminderCard** (`components/cards/RelationshipReminderCard.tsx`)
  — Heart icon, days-since + relationship context, Done / Not now.

All acknowledge via `packCardsApi.acknowledge(cardId, action, snoozedUntil?)`.
`onAcknowledged` callback triggers `mutate()` in the parent to refresh the feed.

### Pack Settings Page (SHIPPED — Sprint 14)
`/settings/pack` (`pages/settings/PackSettingsPage.tsx`):
Three visual states:
1. Face clustering off → prerequisite banner.
2. PLA off → description + Enable CTA.
3. PLA on → status card (Disable), per-workflow toggles (checkbox + sub-controls: lookback slider, day dropdown, time picker, inactive-days slider), general settings (daily run time, max suggestions), collapsible run history table.

All controls are optimistic: PATCH `/api/v1/settings` on change.
`FlagProvider` now accepts an optional `overrides` prop for tests.

### Today Feed Card Type Registry (Sprint 14 addition)
`CardRenderer.tsx` discriminates pack cards via the `case "pack":` branch.
The `payload.card_type` field (set by `PackCardSource`) selects the component:
- `"follow_up_suggestion"` → `FollowUpCard`
- `"weekly_summary"` → `WeeklySummaryCard`
- `"relationship_reminder"` → `RelationshipReminderCard`

To add a new pack card type:
1. Add the type to `packs/pla/manifest.yaml::card_types`.
2. Add the check constraint value in the Alembic migration.
3. Create the React component under `components/cards/`.
4. Add the `if (cardType === "...")` branch in `CardRenderer`.
5. Add i18n keys for title/body/actions.

### Testing
- Framework: Vitest + React Testing Library
- Location: colocated `__tests__/ComponentName.test.tsx`
- Test: renders correctly, handles loading/error/empty states, flag gating works, accessibility (axe-core)
- Run: `make test-web`

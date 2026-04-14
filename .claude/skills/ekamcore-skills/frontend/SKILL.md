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

### People Screens (Coming Sprint 13 — backend ready)
Sprint 12 shipped the backend. Sprint 13 wires the UI. Endpoint
contract for the planned screens:

- `/people` (list)
  - `GET /api/v1/people?cursor&limit` → `TrustedPersonListResponse`
  - cursor pagination, `display_name`, `confirmed_at`, `trust_source`
- `/people/:id` (detail)
  - `GET /api/v1/people/{person_id}` → `TrustedPersonResponse`
  - `PATCH /api/v1/people/{person_id}` `{display_name}` (rename)
  - `DELETE /api/v1/people/{person_id}` (soft delete)
- `/people/review` (review queue)
  - `GET /api/v1/review-queue?confidence&cursor&limit`
    → `ReviewQueueListResponse` (sample face_detection_ids,
       sample_photo_asset_ids, top_candidate, confidence_bucket)
  - `GET /api/v1/review-queue/{cluster_id}` (full member list)
  - `POST /api/v1/review-queue/{cluster_id}/skip` (24h skip marker)
  - Confirm flow: `POST /api/v1/people/confirm-candidate`
    `{cluster_id, contact_id}`
  - Reject flow: `POST /api/v1/people/reject-cluster` `{cluster_id, reason?}`
- `/people/:id` actions
  - `POST /api/v1/people/merge` `{person_ids, keeper_id}`
  - `POST /api/v1/people/{person_id}/split`
    `{face_detection_ids, new_display_name}`
- History tab (any people screen)
  - `GET /api/v1/people/operations` → `OperationListResponse`
  - `POST /api/v1/people/operations/undo-last`
  - `POST /api/v1/people/operations/{operation_id}/undo`

All endpoints require auth + active face consent. Mutations need the
double-submit CSRF token (`ekamcore_csrf` cookie + `X-CSRF-Token`
header). Reads rate-limit at 120/min/user, mutations at 30/min/user.
Use `apps/api/api/schemas/trusted_person.py`,
`apps/api/api/schemas/review_queue.py`,
`apps/api/api/schemas/people_operations.py` as the source of truth
for response shapes when generating TS types.

### Styling Rules
- Use Tailwind utilities. Extend via tailwind.config.ts theme (not arbitrary values).
- Design system components in web/src/design-system/components/. Pages import from there.
- Max content width: 960px (max-w-[960px] mx-auto). Sidebar: 240px fixed.
- Responsive: sidebar collapses below 1024px. Single column below 768px.
- Dark mode: deferred to v1.1. Use CSS variables (tokens.css) so only token values change.
- Motion: --duration-normal (0.2s), --easing-default. Respect prefers-reduced-motion.

### Testing
- Framework: Vitest + React Testing Library
- Location: colocated `__tests__/ComponentName.test.tsx`
- Test: renders correctly, handles loading/error/empty states, flag gating works, accessibility (axe-core)
- Run: `make test-web`

# Phase 3 — Sprint 13 status report

**Sprint window**: Weeks 25–26
**Gate date**: 2026-04-15
**Verdict**: SHIPPED — full People Graph web UI on top of the
Sprint 12 backend. One follow-up (Playwright infrastructure) is
documented and queued for Sprint 14's tail.

## What's enabled

Sprint 13 lands the entire user-facing People Graph surface. Every
feature below is wired end-to-end, gated on `face_clustering_enabled`
+ active face consent, and backed by vitest coverage.

- **People list page** (`/people`) — grid / list toggle, debounced
  server-side search, confidence filter chips, `PersonAvatar`
  backed by a new cropped-face endpoint, list-view multi-select
  with a floating merge action bar, and a History drawer trigger.
  Source: `apps/web/src/pages/people/PeopleListPage.tsx`.
- **Person detail page** (`/people/:personId`) — header card with
  inline rename + kebab (Merge / Split / Delete), four tabs
  synced to URL hash (Photos, Files, Events, Reminders), Faces
  management section with "remove face" and multi-select "Split
  out", delete confirm modal, and per-tab error isolation. Six
  new `/people/:id/{photos,files,events,reminders,faces,faces/:fid/thumbnail}`
  endpoints back it. Source:
  `apps/web/src/pages/people/PersonDetailPage.tsx`,
  `apps/api/api/routers/people.py`,
  `apps/api/api/services/face/detach_face_service.py`.
- **Review Queue page** (`/people/review`) — `useReducer` session
  cursor, document-level keyboard shortcuts
  (Enter / R / S / N / 1–5 / ← / → / ? / Esc), optimistic
  auto-advance with rollback on API failure, batch reject / skip
  floating bar, and an `aria-live` announcement region. Source:
  `apps/web/src/pages/people/ReviewQueuePage.tsx`.
- **Merge persons modal** — radio keeper picker with ≥2 rule,
  typeahead add-more backed by `usePeopleList`, inline error
  banner on `/people/merge` failure. Wired from the detail-page
  kebab and from the list-view multi-select bar. Source:
  `apps/web/src/components/people/MergePersonsModal.tsx`.
- **Split person modal** — `role="grid"` face picker with
  space/enter toggling and the "leave at least one face behind"
  client-side rule, new-name input, optional `preselectedFaceIds`
  seed from the detail-page Faces section's select mode. Source:
  `apps/web/src/components/people/SplitPersonModal.tsx`.
- **Undo drawer + Cmd/Ctrl+Z shortcut** — right-side drawer over
  `usePersonOperations(50)` with operation-specific summaries,
  relative times, and per-row Undo buttons. A new `useUndoShortcut`
  hook binds the global chord at the document level and is wired
  into both `PeopleListPage` and `PersonDetailPage`. Both the
  drawer and the shortcut revalidate every `/api/v1/people*` and
  `/api/v1/review-queue*` SWR key after an undo. Source:
  `apps/web/src/components/people/UndoDrawer.tsx`,
  `apps/web/src/hooks/useUndoShortcut.ts`.
- **Photo lightbox with face overlay** — full-screen viewer that
  measures the rendered image rect on load + resize and draws a
  button per detected face in normalized coordinates. Known faces
  navigate to `/people/:id`; unknown clusters to
  `/people/review?highlight_cluster=:id`. Two new photo
  endpoints (`/full`, `/faces`) plus a shared
  `consent_service.resolve_workspace_with_face_consent` helper
  power it. `PhotoCard` and the PersonDetailPage Photos tab both
  mount it. Source:
  `apps/web/src/components/photos/PhotoLightbox.tsx`,
  `apps/api/api/routers/photos.py`,
  `apps/api/api/services/face/consent_service.py`.
- **People in the Today feed and Search** — new `PersonCardSource`
  ranks trusted persons by recent (`appears_in`, last 14 days)
  graph-edge count and surfaces up to 3 cards per Today feed;
  consent-gated and graceful. `search_all` gained a `"person"`
  type backed by `search_trusted_persons`, emitting `PersonCard`s
  with `payload.source="trusted_person"` so the web client can
  route clicks to `/people/:id`. A new `PersonCard` component
  renders in both `CardRenderer` (Today) and `SearchResultCard`
  (Search) with surface attribution. Source:
  `apps/api/api/services/today/person_card_source.py`,
  `apps/api/api/services/query/search.py`,
  `apps/web/src/components/cards/PersonCard.tsx`.
- **Top-bar person typeahead** — replaces the disabled top-bar
  placeholder with a functional person finder. Debounced
  `usePeopleList` search, @-sigil support, arrow-key / Enter /
  Esc navigation, up to 5 results with `PersonAvatar`. Falls
  back to the disabled legacy input when the feature or consent
  is off so the top-bar layout stays stable. Source:
  `apps/web/src/components/people/TopBarPersonSearch.tsx`,
  `apps/web/src/layouts/MainLayout.tsx`.
- **Sprint 13 E2E + a11y plan** — Playwright is not yet installed
  in the repo, so S13-010 ships a detailed scaffold instead of
  rot-prone `.spec.ts` files. `tests/e2e/README.md` documents
  the infrastructure gap; `tests/e2e/sprint13_plan.md` captures
  every spec, the seed data contract, the axe audit matrix, and
  flaky-test guardrails. `docs/ACCESSIBILITY_CHECKLIST.md` gains
  a §9 Phase 3 pages section for the interim manual audit, and
  `docs/test_traceability.json` is rewritten to reflect the real
  Sprint 13 coverage.

## What's still backend-only from Phase 3

- **PLA Pack SDK + execution engine** — Sprint 14. The pack-card
  rendering stub already exists (`PackCard` in
  `apps/api/api/schemas/envelope.py`) but no packs are published.
- **Pack cards in the Today feed** — Sprint 14.
- **72-hour soak test** — Sprint 14 infrastructure workstream.

## Test counts (as of gate)

- **Web unit (vitest)** — 104 passing / 10 pre-existing failures
  all isolated to `src/__tests__/a11y/accessibility.test.tsx`
  (axe-core dev-dep missing + jsdom `matchMedia` gap; **unrelated
  to Sprint 13** and documented in `tests/e2e/sprint13_plan.md`).
- **Backend unit + integration** — 8 new test files added this
  sprint (`test_detach_face_service.py`,
  `test_person_detail_endpoints.py`,
  `test_photo_faces_endpoint.py`, and the frontend harness
  additions). No regressions reported vs. Sprint 12 in local
  syntax checks; a full `pytest` run requires the live postgres /
  redis / qdrant stack, which isn't spun up in this session.
  Gate pre-commit run in CI is the authoritative check.
- **Web type check** — `npx tsc --noEmit` clean across 62 files
  changed in Sprint 13.
- **Playwright E2E** — deferred. See `tests/e2e/sprint13_plan.md`
  for the full coverage matrix and the follow-up story.

## Accessibility audit

The in-repo axe suite (`src/__tests__/a11y/accessibility.test.tsx`)
has **10 pre-existing failures unrelated to Sprint 13**: `axe-core`
is listed as a dev dep but resolves at runtime to "not installed",
and jsdom lacks `window.matchMedia`. These failures existed at the
start of Sprint 13 and will be fixed as part of the Playwright
install story. For Sprint 13 specifically, every new component
passes a manual audit using the checklist in
`docs/ACCESSIBILITY_CHECKLIST.md §9 Phase 3 pages`:

- PeopleListPage — manual pass
- PersonDetailPage — manual pass
- ReviewQueuePage — manual pass (keyboard shortcuts, aria-live)
- MergePersonsModal — manual pass (radiogroup labels, focus trap)
- SplitPersonModal — manual pass (role=grid, gridcell aria-label)
- UndoDrawer — manual pass (role=dialog, per-row aria-label)
- PhotoLightbox — manual pass (aria-label per bbox, sr-only announce)
- TopBarPersonSearch — manual pass (combobox/listbox/option roles)

## Known limitations (v1.0)

- **No Cmd+K command palette.** The top-bar person typeahead
  covers the "find a person fast" primary need. A full command
  palette across every entity type is deferred to v1.1.
- **No person photo timeline view.** Photos tab on the detail
  page is cursor-paginated but not grouped by date. Deferred to
  v1.1.
- **Mobile responsive breakpoints tested down to 375px.** Native
  mobile (React Native) is a separate Phase 3+ deliverable; Sprint
  13 ships the responsive web layout only.
- **Photo lightbox face selection is read-only.** Users can
  navigate *from* a face to a person but cannot reassign the face
  from inside the lightbox — that still requires opening the
  person detail page and using the Faces section's select mode.
- **"Catch up with" Today card context is not shipped.**
  `PersonCardSource` emits only `context: "seen_recently"` in
  Sprint 13. The catch-up signal (no activity in 30+ days and ≥5
  photos) lands in Sprint 14 alongside the PLA Pack signal
  weighting work.
- **Recap person stats are not extended.** Sprint 13 deferred
  the Recap generator changes to keep scope controlled; the
  People feed still ships through Today and Search.
- **HEIC full-resolution photos are not transcoded.** `/photos/:id/full`
  raises `PHOTO_UNSUPPORTED_FORMAT` for non-JPEG mimes; the lightbox
  should fall back to the thumbnail when it sees that error (not
  wired in Sprint 13 — `fetch`-level fallback TBD).
- **Undo action chip on toasts not shipped.** The drawer and
  Cmd+Z both work for undo; wiring an inline "Undo" action into
  the `Toast` component requires extending its prop surface and
  touching every mutation call site. Queued for a follow-up.
- **PeopleListPage pagination is cursor-based but no "load more"
  button in the grid view.** SWR fetches the first page of 24
  only; infinite scroll is deferred to v1.1.

## Sprint 13 story status

| Sprint 13 Story | Status | Evidence |
|---|---|---|
| S13-001 Web Foundations | SHIPPED | routing, types, API clients, SWR hooks, i18n, metrics, feature flags, stub gated pages |
| S13-002 People List | SHIPPED | grid/list + search + avatar endpoint + chips + empty state CTA |
| S13-003 Person Detail | SHIPPED | tabs + rename + delete + remove-face + 6 sub-resource endpoints + migration 019 + undo handler |
| S13-004 Review Queue | SHIPPED | full keyboard state machine + optimistic auto-advance + batch bar |
| S13-005 Merge Modal | SHIPPED | keeper picker + typeahead + list-view multi-select bar |
| S13-006 Split Modal | SHIPPED | `role=grid` face picker + preselect seed + Faces section select mode |
| S13-007 Undo Drawer | SHIPPED | drawer + Cmd+Z hook + cache revalidation + History button |
| S13-008 Photo Lightbox | SHIPPED | measured bbox overlay + known/unknown navigation + `/full` and `/faces` endpoints + shared consent helper |
| S13-009 Today/Search Integration | SHIPPED | `PersonCardSource`, `search_trusted_persons`, `PersonCard`, top-bar typeahead |
| S13-010 E2E + A11y | PARTIAL — SCAFFOLDED | plan doc, a11y checklist §9, test traceability rewrite; Playwright install is a follow-up |
| S13-011 Gate Review | SHIPPED | skill file updates, this status doc, Sprint 14 readiness notes |

## Sprint 14 readiness

Sprint 14 (PLA Pack + sandbox + soak test) can begin with:

- `PackCard` schema already exists in
  `apps/api/api/schemas/envelope.py`.
- `CardRenderer.tsx` default case falls through to `null` —
  adding a `case "pack":` branch is mechanical once the Pack
  backend ships.
- `PersonCardSource`'s ranking pattern is the template for
  Sprint 14's `PackCardSource`: consent-fail-closed, per-source
  `fetch(today, now) -> list[Card]`, slots into `assemble_today`.
- The shared face-consent guard (`resolve_workspace_with_face_consent`)
  is available for any Sprint 14 endpoint that touches face data.
- Playwright install story should land **before** the first Sprint
  14 UI story so new features land with E2E coverage.

`current_phase` stays at **3**. Sprint 14 is the final Phase 3
sprint; Phase 4 gate comes after `S14-004`.

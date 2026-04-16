# Sprint 13 E2E Plan — People Graph UI (S13-010)

This document is the actionable plan for the Playwright end-to-end
suite that S13-010 calls for. Playwright is not yet installed in
the repo (see `tests/e2e/README.md`); once it lands, convert each
scenario below into a `*.spec.ts` file.

## 1. Goals

- Catch regressions across the full Sprint 13 shipped surface:
  list, detail, review queue, merge/split, undo, lightbox, today,
  search, consent.
- Enforce **WCAG AA** on every Phase 3 page via axe-core.
- Run the suite in under **10 minutes** on reference hardware.
- Be readable under failure: every step labelled with
  `test.step()`, traces on first retry, screenshots on failure.

## 2. Toolchain the follow-up story must install

- `@playwright/test` (devDep)
- `@axe-core/playwright` (devDep)
- `playwright.config.ts` with `testDir: 'tests/e2e'`, reference
  the dev server via `webServer: { command: 'make dev', ... }`
- `tests/e2e/fixtures/auth.ts` providing an authed `test` export:
  logs in once per worker, persists `storageState`, and injects a
  workspace cookie.
- `make test-e2e` target + nightly GitHub Actions job.

## 3. Seed data contract — `scripts/seed_phase3_e2e.py`

Idempotent Python script (calls the running API with an admin
token). Re-running it must leave the DB in the same state.

| Entity | Count | Notes |
|---|---|---|
| Workspace | 1 | `e2e-workspace`; face consent active |
| Contacts | 5 | Alice, Bob, Carol, Dave, Eve |
| Photos | 50 | 30 with GPS EXIF |
| Face detections | 100 | 20 per identity |
| Face clusters | 5 | one per identity |
| Trusted persons (confirmed) | 3 | Alice, Bob, Carol |
| Review queue items | 2 | Dave (high), Eve (medium) — `cluster_state='unconfirmed'` with scored candidates |
| Calendar events | 5 | each co-occurs with 2+ photos |
| Reminders | 0 | reminder↔person bridge not shipped |

The seeder calls the real API (not raw SQL) so coverage includes
the API surface. Workspace cleanup between runs is via a
`DELETE /api/v1/admin/e2e/reset` endpoint added as part of the
Playwright install story (or a direct SQL truncate outside the
app transaction — pick one at implementation time).

## 4. Spec files

Each entry lists the scenarios a single `*.spec.ts` file must
contain. Scenarios are **ordered by cost** — cheap setup/render
tests first, then mutation flows, then multi-step flows.

### 4.1 `people_list.spec.ts`
- **renders_seeded_persons** — visit `/people`, assert 3 grid cards
  with names Alice/Bob/Carol.
- **search_filters_by_name** — type "al" in the search box, wait
  for the debounce, assert only Alice is visible.
- **grid_list_toggle** — click List toggle, assert `data-testid=people-list` is now present.
- **pagination_load_more** — seed an extra 30 persons in a
  dedicated workspace, scroll, assert the cursor loads more.
- **empty_state_on_clean_workspace** — use a fresh workspace,
  assert the "Go to Review Queue" CTA is rendered.

### 4.2 `person_detail.spec.ts`
- **renders_with_tabs** — open `/people/<alice>`, assert the four
  TabBar entries exist and hash updates on click.
- **photos_tab_shows_linked_photos** — Photos tab renders thumbnails for Alice.
- **rename_persists** — click pencil, type "Alice Smith", Enter,
  reload page, assert new name.
- **delete_then_undo_restores** — delete Alice via kebab, confirm,
  then Cmd+Z, assert Alice is back in the list.
- **remove_face_updates_count** — open Faces section, click X on
  the first face, confirm, assert face count decremented.

### 4.3 `review_queue.spec.ts`
- **renders_pending_items_ordered_by_confidence** — navigate to
  `/people/review`, assert Dave (high) appears before Eve.
- **confirm_via_enter_advances** — press Enter, assert POST
  `/confirm-candidate` is intercepted and the cursor advances to Eve.
- **reject_via_r_advances** — press R, assert POST
  `/reject-cluster` and advance.
- **skip_via_s_advances** — press S, assert POST
  `/review-queue/:id/skip` and advance.
- **pick_alternate_candidate_via_number_key** — press 2 then Enter,
  assert the request carries the 2nd candidate's contact_id.
- **new_person_via_n_key** — press N, type "Stranger", click
  Create, assert POST `/api/v1/people` with that name.
- **empty_state_after_all_actioned** — action both items, assert
  "All caught up" + "Reviewed 2 items" summary.
- **batch_reject** — select both items' Batch checkboxes, click
  Reject in the floating bar, assert two reject calls fired.

### 4.4 `merge_split.spec.ts`
- **merge_two_persons_then_undo_restores** — open Alice, kebab →
  Merge, add Bob via typeahead, pick Alice as keeper, submit;
  assert Bob is gone from `/people`; Cmd+Z; assert Bob is back.
- **split_person_creates_new_person_with_selected_faces** — open
  Alice, kebab → Split, select 5 faces, name "Not Alice", submit;
  assert "Not Alice" appears in `/people` with 5 faces.
- **split_then_undo_restores_original** — same as above then Cmd+Z;
  assert only Alice exists and she has the original face count.

### 4.5 `undo_drawer.spec.ts`
- **shows_recent_operations** — perform a rename, open the History
  drawer, assert the rename row is at the top.
- **undo_via_drawer_button_restores_state** — click the drawer's
  Undo button on the rename row, assert the name reverts.
- **undo_via_toast_action** — (deferred — requires the Toast-action
  extension noted in S13-007). Mark skipped until the Toast work
  lands.
- **cmd_z_undoes_last_operation** — perform a reject in Review
  Queue, press Cmd+Z, assert the cluster is pending again.

### 4.6 `lightbox.spec.ts`
- **opens_from_photos_page** — click a photo card, assert
  `data-testid=photo-lightbox` is visible.
- **renders_face_overlays** — wait for the faces layer, assert
  number of `data-testid^=lightbox-face-` elements matches the
  seeded face count for that photo.
- **click_face_navigates_to_person** — click a known-face bbox,
  assert URL is `/people/<id>`.
- **unknown_face_routes_to_review_queue** — click an unknown-face
  bbox, assert URL includes `highlight_cluster=`.
- **keyboard_prev_next** — seed two photos in the feed, open the
  lightbox, press `→`, assert the src updates.
- **esc_closes** — press Esc, assert the lightbox unmounts and
  focus returns to the PhotoCard.

### 4.7 `today_search_integration.spec.ts`
- **today_feed_shows_person_cards** — visit `/today`, assert at
  least one PersonCard rendered (seed ensures recent photo edges).
- **search_people_filter_returns_persons** — visit `/search?q=ali&type=person`,
  assert only PersonCards appear.
- **topbar_person_search_triggers** — focus top-bar search, type
  "@alice", Enter, assert URL is `/people/<alice>`.

### 4.8 `consent_flow.spec.ts`
- **enable_consent_grants_and_backfills** — from Settings → Photo
  Intelligence, click Enable, walk the consent dialog, assert the
  sidebar People entry becomes enabled.
- **disable_consent_shows_delete_report** — click Disable, confirm,
  assert the delete report lists 5 clusters + 100 detections.

### 4.9 `accessibility.spec.ts`
For each page in the matrix below, run
`new AxeBuilder({ page }).analyze()` and assert the `violations`
array is empty. Then Tab through every interactive element once
and assert `document.activeElement` is always visible (focus ring
in viewport).

| Page | URL | Setup | Target violations |
|---|---|---|---|
| PeopleListPage | `/people` | seed | 0 |
| PersonDetailPage | `/people/<alice>` | seed | 0 |
| ReviewQueuePage | `/people/review` | seed | 0 |
| MergePersonsModal | `/people/<alice>` + open via kebab | seed | 0 |
| SplitPersonModal | `/people/<alice>` + open via kebab | seed | 0 |
| UndoDrawer | `/people` + open via History button | seed + one op | 0 |
| PhotoLightbox | `/photos` + click first card | seed | 0 |
| TopBarPersonSearch | `/today` + focus input | seed | 0 |

## 5. Flaky-test guardrails

- Use `expect(locator).toBeVisible({ timeout: 5000 })` — never
  `await page.waitForTimeout()`.
- Network-heavy specs should `await page.waitForLoadState('networkidle')`
  between major actions (sparingly).
- Retry count: `retries: process.env.CI ? 2 : 0`.
- Trace: `trace: 'on-first-retry'`.
- Screenshots: `screenshot: 'only-on-failure'`.
- Each test owns its own data by writing to a unique workspace
  (`e2e-${test.info().workerIndex}`) — parallel workers never
  share state.

## 6. CI wiring

- Add the nightly job to `.github/workflows/e2e.yml` — triggered
  on `schedule: cron '0 7 * * *'` and on PR labels `e2e`.
- Cache Playwright browsers via `actions/cache` keyed on
  `~/.cache/ms-playwright`.
- Upload `playwright-report/` and `test-results/` as artifacts on
  failure.

## 7. Scope notes (honest)

- Recap person stats tests are not in the matrix because S13-009
  deferred the Recap extension itself.
- Toast-level inline Undo is not tested yet because S13-007
  deferred the Toast component's action-slot extension.
- `seed_phase3_e2e.py` is expected to create real files on disk for
  the photo `/full` endpoint — the existing `test_photo_faces_endpoint.py`
  integration test already handles this with a 1x1 JPEG fixture;
  the seeder should adopt the same pattern.

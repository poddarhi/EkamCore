# Sprint 14 E2E Plan — PLA Pack + Person-Context Queries (S14-012)

Extends `sprint13_plan.md` with Sprint 14 scenarios. Same
infrastructure prerequisite (Playwright not yet installed).

## New spec files

### `pack_settings.spec.ts`
- **enable_pla**: navigate to /settings/pack → face clustering
  prerequisite → enable → toggle appears.
- **configure_workflow_toggles**: toggle follow-ups off →
  setting PATCHed → toggle back on.
- **daily_run_time**: change time picker → PATCHed.
- **disable_pla**: click Disable → confirm modal → PATCHed.

### `pack_cards.spec.ts`
- **follow_up_appears_in_today**: trigger daily → /today shows
  FollowUpCard with person name.
- **acknowledge_done_removes**: click Done → card fades out →
  reload → card gone.
- **snooze_hides_temporarily**: click Remind me later → Tomorrow
  → card gone → advance clock 1 day → card back.
- **weekly_summary_renders**: trigger weekly → Today shows
  WeeklySummaryCard with stats + AI badge.
- **relationship_reminder_actions**: Done + Not now both work.

### `person_query.spec.ts`
- **who_is_returns_profile**: type "who is Alice" in query box →
  PersonCard in results.
- **files_for_person**: "files for Bob" → FileCards appear.
- **at_search_opens_person**: type "@alice" in top bar → pick →
  navigates to /people/:id.

### `accessibility_phase3_complete.spec.ts`
- **PackSettingsPage**: axe 0 violations.
- **TodayPage with pack cards**: axe 0 violations.
- **FollowUpCard keyboard**: Tab through Done / Not now / Snooze.
- **SnoozePicker keyboard**: Tab through date buttons + input.
- **WeeklySummaryCard**: screen reader reads summary text.
- **RelationshipReminderCard keyboard**: Tab through actions.

## Seed data additions

Extend `seed_phase3_e2e.py` (from sprint13_plan.md §3) with:
- 5 pack_runs (3 daily completed, 1 weekly completed, 1 failed).
- 10 pack_cards (follow-up, weekly, relationship, some acknowledged).
- `pla_pack_enabled` flag ON for the e2e workspace.

## Flaky-test guardrails

Same as sprint13_plan.md §5. Pack card tests additionally need
`await page.waitForResponse('**/pack-cards**')` after
acknowledge clicks so the SWR revalidation settles before
asserting card removal.

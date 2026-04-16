# tests/e2e — Playwright end-to-end suite

**Status:** infrastructure-pending. As of S13-010 the EkamCore repo
does not yet have Playwright installed. This directory currently
holds only planning artifacts; runnable specs land in the follow-up
story that installs `@playwright/test`, adds `playwright.config.ts`,
and wires a seed script into CI.

## What lives here today

- `README.md` — this file.
- `sprint13_plan.md` — the full plan for Sprint 13 People Graph UI
  end-to-end coverage. Every spec the S13-010 story calls for is
  listed with its scenarios, the keyboard paths, and the axe
  assertions. This is the input for the Playwright-install story.

## What the follow-up story must add

1. `package.json` devDeps: `@playwright/test`, `@axe-core/playwright`.
2. `playwright.config.ts` at the repo root (or `apps/web/`)
   pointing at `http://localhost:5173` for the dev build.
3. A `tests/e2e/fixtures/auth.ts` file exporting a `test` fixture
   that logs in once, saves `storageState`, and reuses it across
   specs.
4. `scripts/seed_phase3_e2e.py` — idempotent seed for the data
   contract documented in `sprint13_plan.md §3`.
5. `make test-e2e` target and a nightly GitHub Actions job.
6. Convert `sprint13_plan.md` scenarios into `*.spec.ts` files.

## Scope guardrails

- **Runtime budget:** 10 minutes for the full Sprint 13 suite.
- **No hardcoded sleeps** — rely on Playwright auto-waiting.
- **Trace on first retry** + screenshots on failure.
- **`test.step()`** for every logical step so failure reports are
  self-explanatory.
- **Axe scan on every page** with the checklist in
  `docs/ACCESSIBILITY_CHECKLIST.md §9` as the definition of done.

## Why the specs aren't here yet

Writing Playwright specs that can't run is worse than writing
nothing — they rot, drift from the real UI, and give a false sense
of coverage. `sprint13_plan.md` captures the intent precisely
enough for a follow-up engineer to implement quickly once the
Playwright toolchain is in place, without losing the scenario
coverage the story asked for.

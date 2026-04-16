# EkamCore Accessibility Checklist (G-14 / ART-26)

**Target:** WCAG 2.1 Level AA
**Scope:** Web app (`apps/web/`) — all user-facing pages and components

This checklist covers items that **automated tools (axe-core) cannot detect**. The automated suite in `src/__tests__/a11y/accessibility.test.tsx` catches ~40% of WCAG issues. Everything below requires manual review by an engineer before each release.

---

## 1. Keyboard Navigation

Test every page using **only the keyboard** (no mouse, no touch).

- [ ] **Tab order is logical** — moves left-to-right, top-to-bottom, matching visual layout.
- [ ] **No keyboard traps** — focus can always escape every widget (dropdowns, modals, date pickers).
- [ ] **Skip to main content link** — visible on first Tab, moves focus to `<main>`.
- [ ] **All interactive elements reachable** — buttons, links, inputs, custom widgets.
- [ ] **Custom widgets use correct keys** — arrow keys for menus/listboxes, Enter/Space to activate.
- [ ] **Escape closes modals and dropdowns** — Modal, NotificationBell, date range picker.
- [ ] **Focus returns to trigger** — after closing a modal, focus moves back to the button that opened it.
- [ ] **No `tabindex > 0`** — only `tabindex="0"` or `"-1"` is allowed.

## 2. Focus Management

- [ ] **Focus is visible on every interactive element** — 2–3px ring, high contrast, not removed via `outline: none` without a replacement.
- [ ] **Focus moves predictably on page transition** — new page focuses `<h1>` or the skip-nav target.
- [ ] **Modal opens with focus on first focusable element** — not on the backdrop.
- [ ] **Focus trap engaged for modals and mobile drawer** — verified via `useFocusTrap` hook usage.
- [ ] **Focus restored on modal close** — to the element that opened it.

## 3. Semantic HTML & Landmarks

- [ ] **One `<h1>` per page** — matches page title.
- [ ] **Heading hierarchy is correct** — no skipped levels (h1 → h2 → h3, not h1 → h3).
- [ ] **Landmarks present** — `<header>`, `<nav>`, `<main>`, `<aside>` (where applicable), `<footer>`.
- [ ] **`<main>` has `id="main-content"`** — skip link target.
- [ ] **Navigation is wrapped in `<nav>`** — with `aria-label` distinguishing multiple navs.
- [ ] **Lists use `<ul>`/`<ol>`/`<li>`** — not `<div>` pretending to be a list.

## 4. Forms

- [ ] **Every input has a visible label** — via `<label>` or `aria-label`, never placeholder-only.
- [ ] **Labels are associated via `for`/`id`** — clicking the label focuses the input.
- [ ] **Required fields indicated** — both visually (asterisk) and via `required` attribute.
- [ ] **Error messages linked via `aria-describedby`** — announced when focus lands on the field.
- [ ] **Error messages use `role="alert"`** — announced on submission failure.
- [ ] **Form submission gives feedback** — success banner, loading spinner, or screen reader announcement.
- [ ] **Inputs have appropriate `autocomplete` attributes** — `email`, `current-password`, `name`.
- [ ] **Disabled inputs explain why** — via `title` or adjacent text, not just visual greying.

## 5. Text Alternatives

- [ ] **All `<img>` tags have `alt` text** — meaningful images describe content; decorative images use `alt=""`.
- [ ] **Icon-only buttons have `aria-label`** — e.g. NotificationBell, close buttons.
- [ ] **Decorative icons use `aria-hidden="true"`** — lucide-react icons inside labeled buttons.
- [ ] **SVG graphics have `<title>` or `aria-label`** — if conveying information.
- [ ] **Placeholder is not the only label** — placeholder disappears on typing.

## 6. Color & Contrast

- [ ] **Normal text contrast ≥ 4.5:1** — verified via design tokens (all pass — see tokens.css analysis).
- [ ] **Large text contrast ≥ 3:1** — 18pt+ or 14pt+ bold.
- [ ] **UI component contrast ≥ 3:1** — buttons, form borders, focus indicators.
- [ ] **Information is not conveyed by color alone** — error states also use icons and text; status badges include labels.
- [ ] **Link text is distinguishable from body text** — underline or non-color cue, not just color.

## 7. Text & Content

- [ ] **Link text is meaningful** — no "click here" or "read more"; use "Read the privacy policy".
- [ ] **Button text describes the action** — "Save settings", not "OK".
- [ ] **Abbreviations are expanded** — `<abbr title="World Wide Web">WWW</abbr>`.
- [ ] **Language is set** — `<html lang="en">` in index.html.
- [ ] **Page title reflects content** — unique per page, set via document.title.
- [ ] **Text can be resized to 200%** — without horizontal scroll or content clipping.
- [ ] **Line spacing is readable** — `leading-*` classes used consistently.

## 8. Dynamic Content & Announcements

- [ ] **Loading states announced** — `aria-busy="true"` or live region.
- [ ] **Success messages announced via `aria-live="polite"`** — e.g. "Settings saved".
- [ ] **Errors announced via `aria-live="assertive"` or `role="alert"`** — for urgent feedback.
- [ ] **Notifications update the live region** — new notification bell count announced.
- [ ] **Search results count announced** — "Showing 20 of 100 results".
- [ ] **Use `announceToScreenReader()` from `utils/a11y.ts`** — for all async feedback that isn't tied to a visible alert.

## 9. Motion & Animation

- [ ] **`prefers-reduced-motion` respected** — tokens.css sets durations to 0s via `@media (prefers-reduced-motion: reduce)`.
- [ ] **Auto-playing animations can be paused** — no indefinite loops without a control.
- [ ] **No flashing content** — nothing flashes more than 3 times per second.
- [ ] **Transitions are short** — <500ms for most interactions.

## 10. Media

- [ ] **No auto-playing audio** — N/A (EkamCore has no audio).
- [ ] **Video has captions** — N/A (EkamCore has no video).
- [ ] **Photos have meaningful alt text** — PhotosPage uses location name or "Photo" fallback.

## 11. Responsive & Zoom

- [ ] **Works at 320px viewport width** — no horizontal scroll.
- [ ] **Works at 200% browser zoom** — no content cut off.
- [ ] **Works with text-only zoom** — text can scale without layout breaking.
- [ ] **Touch targets ≥ 44×44 px** — buttons, links, checkboxes on mobile.
- [ ] **Orientation supported** — portrait and landscape both work.

## 12. Screen Reader Testing

Test at least one page end-to-end with each screen reader:

- [ ] **VoiceOver (macOS)** — Cmd+F5 to start, Ctrl+Option+arrow to navigate.
- [ ] **VoiceOver (iOS)** — triple-click home/side button.
- [ ] **NVDA (Windows)** — if Windows users are in scope.
- [ ] **All interactive elements are announced with their role** — "button", "link", "heading level 2".
- [ ] **Focus order matches reading order** — screen reader doesn't skip around unexpectedly.
- [ ] **Form submission errors are announced** — not silently set.

## 13. Automated Test Coverage

- [ ] **axe-core tests pass with 0 violations** — `pnpm test -- a11y` (see `src/__tests__/a11y/accessibility.test.tsx`).
- [ ] **New pages have a11y tests added** — required before merge.
- [ ] **Component tests check for ARIA attributes** — `getByRole`, `getByLabelText`.
- [ ] **Storybook axe addon enabled** — if Storybook is in use (deferred until Phase 4).

## 14. Documentation

- [ ] **This checklist reviewed before each release** — engineer signs off on every item.
- [ ] **Known a11y issues tracked in issues/** — with target fix dates.
- [ ] **New components document their a11y contract** — in JSDoc or Storybook.

---

## Sign-off

**Release version:** ________________
**Reviewer:** ________________
**Date:** ________________

All unchecked items must have an explanation in the release notes or be filed as known issues.

## 9. Phase 3 pages (People Graph UI) — S13-010 audit

Every page below must pass axe with **0 violations** and a manual
keyboard-only traversal before Sprint 13 gate. Run the automated
axe sweep from `tests/e2e/accessibility.spec.ts` (scaffolded in
`tests/e2e/sprint13_plan.md` — Playwright infra lands in a follow-up
story). Until then, use the in-browser axe DevTools extension and
the notes below as the manual pass.

### PeopleListPage (`/people`)
- [ ] Skip-nav link lands on `<main>` before the search input.
- [ ] `LayoutGrid` / `ListIcon` toggle has `aria-pressed` + visible focus ring.
- [ ] Grid cards expose `aria-label={display_name}` (each `<button>` in `PersonGrid`).
- [ ] History button (`aria-label="Recent changes"`) is reachable and has focus ring.
- [ ] Multi-select checkboxes in list view announce "Select {name}".
- [ ] Floating bulk action bar has `role="region"` + `aria-label`.

### PersonDetailPage (`/people/:id`)
- [ ] Single `<h1>` — the person's display name; rename input re-exposes it via `aria-label`.
- [ ] Pencil rename button has `aria-label={t("person.detail.rename")}`.
- [ ] TabBar has `role="tablist"`; each panel has `id="panel-{key}"` and `role="tabpanel"`.
- [ ] Delete modal is focus-trapped and returns focus to the kebab on close.
- [ ] Faces grid: each face button has `aria-label="Not {name}"`.

### ReviewQueuePage (`/people/review`)
- [ ] Keyboard shortcuts (Enter/R/S/N/1-5/←/→/?/Esc) documented in the hint banner.
- [ ] sr-only `aria-live="polite"` announcement region updates after every action.
- [ ] Filter chips expose `aria-selected` and `role="option"` (already do via FilterChip).
- [ ] Create-new-person modal's Esc path is unambiguous.

### MergePersonsModal
- [ ] `role="radiogroup"` with `aria-label="Choose the keeper"` wraps the rows.
- [ ] Each row label reads "Keep {name} as the merged person".
- [ ] Disabled Merge button has `aria-disabled` + visible reason.

### SplitPersonModal
- [ ] Face grid uses `role="grid"` with `role="gridcell"` children.
- [ ] Each cell's `aria-label` includes position + selected state.
- [ ] Space/Enter toggles selection without scrolling the grid.
- [ ] New-name input has an associated `<label htmlFor>`.

### UndoDrawer
- [ ] `role="dialog" aria-modal="true" aria-labelledby="undo-drawer-title"`.
- [ ] Each Undo button has `aria-label="Undo: {summary}"`.
- [ ] Undone rows render as disabled text, not as a muted button (screen reader clarity).

### PhotoLightbox
- [ ] Full-screen overlay uses `role="dialog"` + `aria-label="Photo viewer"`.
- [ ] Each face bbox button has `aria-label="Face of {name}. Press Enter to view person."` (or "Unknown" equivalent).
- [ ] sr-only status region announces person count on open.
- [ ] Reduced-motion users do not see the fade transition.
- [ ] Esc closes; focus returns to the opening PhotoCard/PhotoTile.

### TopBarPersonSearch
- [ ] `role="combobox"` on the input; dropdown has `role="listbox"`.
- [ ] Each result row is `role="option"` with `aria-selected`.
- [ ] Arrow-key navigation does not scroll the underlying page.

---

### Known Limitations (v1.0)

- **Mobile drawer focus trap**: Not yet implemented via `useFocusTrap` — manual Tab escape works but focus can leak to background content. Tracked in issue #TBD.
- **NotificationBell dropdown**: No arrow-key navigation between notifications yet. Tab and Enter/Escape work. Tracked for v1.1.
- **Modal trigger buttons**: `aria-expanded` not consistently applied to buttons that open modals. Audit pending for Phase 3.
- **Ollama loading spinner**: Uses CSS animation without `aria-busy` on the container. Low priority since the spinner is brief.

---

## References

- [WCAG 2.1 Quick Reference](https://www.w3.org/WAI/WCAG21/quickref/)
- [Deque University axe rules](https://dequeuniversity.com/rules/axe/)
- [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/patterns/)
- `apps/web/src/utils/a11y.ts` — runtime helpers (`announceToScreenReader`, `useFocusTrap`, `skipToContent`)
- `apps/web/src/test-setup.ts` — custom `toHaveNoA11yViolations` matcher
- `apps/web/src/design-system/tokens.css` — color contrast tokens

# Accessibility Requirements (S10-001)

EkamCore mobile app targets WCAG 2.1 AA compliance. Every screen and
component must support VoiceOver, Dynamic Type, reduced motion, and
high contrast without separate code paths — accessibility is built in,
not bolted on.

---

## VoiceOver Support

Every interactive element must be reachable and operable with VoiceOver.

### Per-screen requirements

| Screen | VoiceOver behavior |
|--------|-------------------|
| **Login** | Focus moves to email field on mount. Error alert announced immediately. "Sign in" button includes loading state in label. |
| **Today** | Cards read as: "{type}: {title}. {time}. Priority {score}." Swipe right to advance between cards. |
| **Recap** | Section headers announce date. Cards within each section follow Today pattern. Period picker announces current selection. |
| **Search** | Search bar focused on mount. Results announced: "{count} results found." Each result card includes type, title, and relevance. Filter chips announce selected state. |
| **People** | Contact cards: "{name}, {organization}." Detail view reads fields in order: name, org, email, phone. |
| **Photos** | Photo cards: "Photo taken {date} at {location}." Detail view announces metadata. Thumbnail images use alt text from location or date. |
| **Settings** | Toggle switches announce current state: "{label}, {on/off}." |
| **Connectivity banner** | Announced as alert when connection state changes. |

### Element labeling rules

1. Every `TouchableOpacity` / `Pressable` must have `accessibilityLabel`.
2. Icon-only buttons must have a descriptive label (not the icon name).
3. Decorative images use `accessibilityElementsHidden={true}`.
4. Grouped content (e.g., a card with title + subtitle) uses `accessible={true}`
   on the container with a composed `accessibilityLabel`.
5. Loading spinners: `accessibilityLabel="Loading"` + `accessibilityRole="progressbar"`.
6. Error states: `accessibilityRole="alert"` + `accessibilityLiveRegion="assertive"`.

### Navigation

- Bottom tab bar: each tab has `accessibilityLabel` matching the page title.
- Stack navigation: back button has `accessibilityLabel="Go back"`.
- Modals: focus traps inside the modal. Dismiss button labeled "Close".

---

## Dynamic Type

All text must scale with the user's Dynamic Type setting, up to 200%.

### Implementation

- **Never use fixed `fontSize`** in component styles. Always reference
  `Typography.*` tokens from `design-system/tokens.ts`, which will be
  updated to use `PixelRatio.getFontScale()` when Dynamic Type support
  is implemented.
- Until then, the current fixed sizes (15px body, 20px h2, etc.) serve as
  the 100% baseline.
- Containers must use `flexShrink` / `flexWrap` to accommodate larger text.
- No `numberOfLines` truncation on essential content (titles, error messages).
  Supplementary content (subtitles, metadata) may truncate with `…`.
- Test at 100%, 150%, and 200% scale.

### Font scale reference

| Token | 100% | 150% | 200% |
|-------|------|------|------|
| caption | 12 | 18 | 24 |
| small | 13 | 19.5 | 26 |
| body | 15 | 22.5 | 30 |
| h3 | 18 | 27 | 36 |
| h2 | 20 | 30 | 40 |
| h1 | 24 | 36 | 48 |
| display | 32 | 48 | 64 |

---

## Touch Targets

All interactive elements must have a minimum touch target of **44 × 44 pt**
(Apple HIG requirement).

### Rules

- Buttons, switches, and touchable areas: `minHeight: 44, minWidth: 44`.
- If the visual element is smaller (e.g., a 20pt icon button), expand the
  `hitSlop` prop: `hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}`.
- Filter chips in horizontal scroll: min 44pt height, min 44pt width (including
  padding).
- List items that are tappable: min 44pt row height.
- Do not place two touch targets closer than 8pt apart.

---

## Reduced Motion

Respect the user's `prefers-reduced-motion` setting.

### Implementation

- Use `AccessibilityInfo.isReduceMotionEnabled()` (or the `useReducedMotion`
  hook from `react-native-reanimated`) to detect the setting.
- When reduced motion is active:
  - Replace slide/fade transitions with instant state changes.
  - Disable skeleton pulse animations — show static gray placeholders.
  - Disable pull-to-refresh bounce animation.
  - Loading spinners remain (they convey essential state).
- The `a11y.ts` utility exports a `useReducedMotion()` hook for convenience.

---

## High Contrast Mode

Support iOS "Increase Contrast" accessibility setting.

### Implementation

- Use `AccessibilityInfo.isHighContrastEnabled?.()` (iOS 14+) or fall back to
  checking `UIAccessibility.isDarkerSystemColorsEnabled` via native bridge.
- When high contrast is active:
  - Borders increase from 1pt to 2pt.
  - Badge and chip backgrounds darken by one step in the neutral scale
    (e.g., `neutral100` → `neutral200`).
  - Text colors shift from `neutral600` to `neutral900` for secondary text.
  - Confidence badge text uses the border color instead of the lighter text
    color (e.g., high badge: `#28A745` text instead of `#1B6E2E`).
- Do **not** change primary action colors — they already meet 4.5:1 contrast
  ratio against white (#1F3864 on white = 10.5:1).

---

## Screen Reader Test Plan

Run before every release. Requires a physical device (VoiceOver on Simulator
has known differences from device behavior).

### Setup

1. Enable VoiceOver: Settings → Accessibility → VoiceOver → On.
2. Set Dynamic Type to 200%: Settings → Display & Text Size → Larger Text.
3. Enable Reduce Motion: Settings → Accessibility → Motion → Reduce Motion.
4. Enable Increase Contrast: Settings → Accessibility → Display → Increase Contrast.

### Test matrix

| # | Screen | Action | Expected VoiceOver output |
|---|--------|--------|--------------------------|
| 1 | Login | Focus on mount | "Email, text field" |
| 2 | Login | Enter invalid creds, submit | "Error: Invalid email or password, alert" |
| 3 | Login | Submit with valid creds | "Sign in, button, loading" → navigates to Today |
| 4 | Today | Swipe through cards | Each card announces type, title, time |
| 5 | Today | Tap a card | Navigates to detail; back button announces "Go back" |
| 6 | Search | Open search tab | Search bar focused, "Search, text field" |
| 7 | Search | Type and get results | "{N} results found" announced |
| 8 | Search | Tap filter chip | "{type} filter, selected" announced |
| 9 | Search | Empty results | "No results found" announced as live region |
| 10 | Connectivity | Go offline | Banner: "You're offline" announced as alert |
| 11 | Connectivity | Come back online | Banner dismissed, no announcement |
| 12 | All screens | Dynamic Type 200% | No text clipped. All content scrollable. |
| 13 | All screens | Reduce Motion | No slide animations. Spinners still visible. |
| 14 | All screens | High Contrast | Borders thicker. Text darker. |

### Pass criteria

- Every test passes on iPhone SE (smallest screen) and iPhone 15 Pro Max.
- No "unlabeled button" VoiceOver warnings in Accessibility Inspector.
- No touch target smaller than 44pt in Accessibility Inspector size report.

---

## Related Files

| File | Purpose |
|------|---------|
| `src/utils/a11y.ts` | Accessibility label constants and utility types |
| `src/design-system/tokens.ts` | Typography tokens (Dynamic Type baseline) |
| `src/components/ConnectivityBanner.tsx` | Reference implementation with accessibilityRole="alert" |
| `src/screens/LoginScreen.tsx` | Reference implementation with VoiceOver labels |

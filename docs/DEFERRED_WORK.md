# Deferred Work

Running log of stubs, deferrals, and items not fully verified. Append-only.

## 2026-06-11 — Chat blank-bubble bug + slow startup + starter cleanup

### Root cause (corrected)
The "blank bubble / vertical dashed line" was **not** a model or Metal problem.
Inspecting persisted AsyncStorage showed the model produced perfect text (e.g.
"1. Build a rustic wooden cabin\n2. ...") on both Metal and CPU. The real bug is
in `react-native-markdown-display`: its `ordered_list_content` / `bullet_list_content`
Views default to `flex: 1` (flexBasis 0%), which collapses to ~zero width on iOS
inside an auto-width chat bubble, wrapping list text one character per line.

- An earlier hypothesis (Metal broken on the iOS Simulator → force CPU via
  `DeviceInfo.isEmulator()`) was **reverted** — inference was never broken; that
  change was an unjustified perf pessimization based on a wrong diagnosis.

### Done
- **Markdown fix** (`src/components/MessageBubble.tsx`): override
  `ordered_list_content` / `bullet_list_content` to `flexGrow:0, flexShrink:1,
  flexBasis:'auto'` so list text uses intrinsic width and wraps normally.
- **Startup speed** (`src/services/llama.ts`): `use_mlock: false` + `use_mmap: true`.
  `use_mlock: true` forced the entire GGUF to be paged into RAM before the model
  load returned (~15-20s stall at launch on device). mmap loads lazily.
- **Empty-output safety net** (`src/context/AppContext.tsx`): if a generation
  returns whitespace-only text, show a Retry note instead of a blank bubble.
- **Cleanup** (`src/screens/ChatScreen.tsx`): removed the 4 conversation-starter
  chips (Spark an idea / Help me write / Explain something / Summarize text) and
  their styles; landing hero is now greeting-only.

### NOT verified (needs a run)
- **Startup time on the physical iPhone** after `use_mlock:false` — the headline
  fix. Expected to drop from ~15-20s to a few seconds; measure on device.
- **Markdown list rendering on iOS** after the flex fix — confirm a numbered/
  bulleted reply renders horizontally (no vertical character column). No UI
  automation (idb) available, so this needs a manual send + look.

### Known leftover
- Conversations generated before these fixes are persisted; old list-heavy
  replies may still look broken in History until regenerated. Optional cleanup.

## 2026-06-12 — Build warnings + startup verification + deploy

### Verified
- **Startup**: ~15-20s → ~2-3s on the physical iPhone (user-confirmed). The
  remaining 2-3s is the model weight load; acceptable. Background-load is the
  next lever if instant UI is ever wanted.
- **iOS markdown list rendering**: confirmed fixed on the iOS Simulator — a
  generated numbered list renders horizontally with normal wrapping (no vertical
  character column). Screenshot evidence captured during the session.
- **Both platforms deployed**: iPhone (Release, devicectl install) and Android
  emulator (installDebug). Clean landing (no starter chips) confirmed on both.

### Xcode build warnings: 200-300 → 20
- Root cause: third-party CocoaPods (RN core, llama.rn, folly, etc.) deprecation/
  nullability warnings. Fixed via `ios/Podfile` post_install loop setting
  `GCC_WARN_INHIBIT_ALL_WARNINGS=YES` + `CLANG_WARN_DOCUMENTATION_COMMENTS=NO`
  on all pod targets. Requires `pod install` (done) + rebuild.
- Remaining 20 are all benign framework-level, NONE from our code:
  2× "run script phase runs every build" (RN's own Hermes/bundle phases),
  3× `libtool: has no symbols`, ~15× Hermes "variable not declared" for JS
  globals (Promise/setTimeout/Blob/…) in the minified bundle. Not worth patching
  RN's generated build phases to reach literal zero.

### LogBox "Open debugger to view warnings" banner
- **Dev-only.** The shipped Release bundle was inspected: the LogBox string and
  HMR/dev-server refs are stripped (`__DEV__=false`), so end users never see it.
- RN 0.85 routes JS console.warn to the React Native DevTools (fusebox), not the
  Metro terminal — and the fusebox inspector rejects raw CDP clients (close 1006),
  so the exact dev warnings could not be captured headlessly. Live testing showed
  NO banner after generate+render with current code. If specific dev warnings
  resurface, open the debugger (`j` in Metro) to read them and fix at source.

## 2026-06-12 — Keyboard overlaps TextInput on Personalization ("Adapt to me") sheet

### Root cause
`src/components/PersonalizationSheet.tsx` is a bottom-anchored sheet
(`root: { justifyContent: 'flex-end' }`) inside a `Modal`, but was NOT wrapped in a
`KeyboardAvoidingView`. iOS Modals do no automatic keyboard avoidance, so the on-screen
keyboard slid up *over* the bottom-pinned TextInputs ("Add a fact" / "Preferred answer
style") — the user couldn't see what they were typing. Confirmed against the working
reference: `ModelsScreen`'s "Add a custom model" sheet has the identical structure but
DOES wrap it in `<KeyboardAvoidingView behavior={ios?'padding':undefined}>` and works.

### Done
- Wrapped the sheet root in `KeyboardAvoidingView` (behavior `padding` on iOS, undefined
  on Android), matching the `ModelsScreen` idiom exactly. `tsc` clean, ESLint clean
  (only a pre-existing unrelated inline-style warning on the toggle row).

### NOT verified (needs a device/sim run)
- On-device confirmation on the physical iPhone that the sheet now rises above the
  keyboard and both inputs stay visible while typing. Keyboard-avoidance is native
  layout behavior and can't be meaningfully unit-tested in Jest; verify by opening
  Settings → "Adapt to me" and focusing each input.

### Known leftover (deliberately deferred)
- `src/components/ConnectionsSheet.tsx` (remote endpoints) has the IDENTICAL defect
  (same bottom-sheet-in-Modal, no KAV). NOT fixed — the remote-connection feature is
  being redesigned per the desktop-pairing-bridge spec
  (`docs/superpowers/specs/2026-06-12-desktop-pairing-bridge-design.md`), so it's not
  worth touching now. Apply the same KAV wrap if/when that sheet survives the redesign.
- Android: user reported the app "stopped" in the emulator (cause unknown, not
  investigated this session). The KAV fix uses `behavior={undefined}` on Android (the
  platform handles soft-input via `windowSoftInputMode`), so it's a no-op there.

## 2026-06-12 (later) — Deploy of keyboard fix; iOS Simulator build blocker

### Deployed (keyboard fix from earlier this day)
- **Physical iPhone (Release):** built clean (0 linker errors), installed + launched on
  "Arpan's iPhone" (udid 00008120-001115340A50C01E). NOTE: `react-native run-ios --udid`
  wants the RN-CLI udid (00008120-…), NOT the `devicectl` CoreDevice UUID
  (A1DE11F4-…) — using the latter silently mis-resolves the destination to
  `Release-iphoneos-maccatalyst` and "builds" without producing a device app.
- **Android emulator (`ekam_test`, Debug):** `installDebug` + `adb reverse tcp:8081` +
  explicit `am start -n com.ekamcore/.MainActivity`. Screenshot confirms clean landing,
  no red box. Pulls JS (incl. the fix) from Metro.
- Visual confirmation of the keyboard behavior itself (sheet rising above keyboard) on
  device is still pending the user's eyes — the deploy is done, the look-see is not.

### BLOCKER — iOS Simulator (Debug) link fails: react-native-svg vs RN 0.85 prebuilt React
- `ld: Undefined symbols for architecture arm64` — `typeinfo`/`vtable` for
  `facebook::react::Props`, `YogaStylableProps`, `BaseViewProps`,
  `DebugStringConvertible`, referenced from `libRNSVG.a` (Fabric component props:
  RNSVGCircleProps, etc.).
- Investigated: not a stale cache (fully clean rebuild after wiping DerivedData failed
  identically); recent git changes (Podfile warning hook, pbxproj font encodings + team
  id) are unrelated; the prebuilt `React.xcframework` HAS a simulator slice but does NOT
  export those Fabric `typeinfo`/`vtable` symbols (only local `shared_ptr` template
  helpers). Device-Release links because `-dead_strip` removes the unreferenced RNSVG
  Fabric code; Debug-sim (`-O0`, no strip) keeps it and the missing symbols surface.
- NOT yet fixed. Candidate fixes (each needs a clean rebuild to validate, ~15 min, and
  carries regression risk to the working builds, so deferred for a deliberate attempt):
  1. Build React Native from source for the sim instead of prebuilt
     (RCT_USE_PREBUILT_RNCORE=0 or RN 0.85 equivalent) so Fabric typeinfo/vtable are
     emitted and linkable.
  2. Upgrade/patch `react-native-svg` to a version compatible with RN 0.85 prebuilt
     frameworks.
  3. Podfile post_install: force the EkamCore target (or RNSVG) link/visibility so the
     Fabric base-class RTTI resolves for the sim slice.
- Toolchain note: builds must run under Homebrew node@24 (`/opt/homebrew/opt/node@24`);
  the default shell node was 20.20.1 (below the >=22.11 engines floor). Metro restarted
  under node@24.

### RESOLVED — iOS Simulator linker blocker (same day)
- Root cause confirmed: RN 0.85 defaults `RCT_USE_PREBUILT_RNCORE='1'`; the prebuilt
  React xcframework does NOT export the Fabric C++ typeinfo/vtable symbols that
  react-native-svg's from-source Fabric code links against.
- Fix: `RCT_USE_PREBUILT_RNCORE=0` → `pod install` rebuilds React **core from source**
  (React-Core, React-Fabric, React-RCTFabric, …), which emits the missing symbols.
  Persisted in `ios/Podfile` (`ENV['RCT_USE_PREBUILT_RNCORE'] ||= '0'`) so future
  `pod install`s don't revert.
- Result: clean Debug sim build now links with **0 linker errors**, installs + launches
  on iPhone 17 Pro sim (iOS 26.5), renders correctly (screenshot verified). The initial
  white screen the user saw was just the first-load Metro bundle.
- Trade-off accepted: builds now compile React core from source (slower first clean
  build, faster incrementally). Applies to device + sim alike.
- All three targets now run the keyboard fix: physical iPhone (Release), Android
  emulator (Debug), iOS Simulator (Debug).

## 2026-06-12 (later still) — Full build-warning audit + main-target suppression
- Full Release build captured ALL warnings (not just screenshot-visible). Total 364:
  - 232 `libtool: '*.o' has no symbols` — benign; NEW, introduced by building React core
    from source (the iOS-Simulator fix). Unavoidable with from-source; not cleanly
    suppressible.
  - 72 `pointer/block missing nullability type specifier` — from React-Core PUBLIC
    headers compiled by the **main EkamCore target** (the Podfile pod-only warning hook
    doesn't cover the app target). FIXED.
  - 44 `RCT* is deprecated (legacy architecture)` (RCTRootView/RCTSurface/etc.) — same,
    main-target compiling React headers. FIXED.
  - 11 Hermes "variable not declared" (JS globals) + 4 script-phase/deployment-target —
    benign, inherent.
  - 0 location (fixed earlier), 0 iPad app-icon (iPhone-only fix worked; earlier "2" was
    a grep false-match).
- Fix: added to the EkamCore app target (Debug+Release) in project.pbxproj:
  `CLANG_WARN_NULLABILITY_COMPLETENESS = NO` + `GCC_WARN_ABOUT_DEPRECATED_FUNCTIONS = NO`.
  Verified via incremental rebuild: main-target nullability=0, deprecated=0, BUILD
  SUCCEEDED.
- Net: 364 → ~247 warnings, ALL remaining benign (232 from-source libtool + 15 inherent).
  None from app code; none affect the shipped app or App Store. User chose "keep sim +
  trim noise" over reverting to prebuilt (which would be ~16-20 warnings but re-break the
  iOS Simulator Debug build).

## 2026-06-12 (close-out) — User-verified on devices
- **Keyboard fix** ("Adapt to me" sheet rises above keyboard): VERIFIED by user on
  device — closes the earlier "NOT verified (needs a device/sim run)" item.
- **Title Case casing sweep**: VERIFIED on Android (screenshot) and iPhone (Release,
  reinstalled via `devicectl` after a run-ios wireless tunnel hiccup `CoreDeviceError
  4000`; the embedded jsbundle was confirmed to contain the new strings).
- Both platforms running the latest build: physical iPhone (Release) + Android emulator
  (Debug). Vision/multimodal feature is spec-only — NOT in any build yet.

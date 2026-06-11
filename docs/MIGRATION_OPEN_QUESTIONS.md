# EkamCore — Migration Open Questions

Tracking the decisions left open after migrating the on-device LLM app into this
repo and renaming it `LocalLLM` → `EkamCore`. Resolve and check these off; this
file can be deleted once everything is settled.

Status as of 2026-06-11: env fixed (Node 24); iOS (Debug launch + Release build)
and Android (Gradle Debug build + emulator launch) both verified; `tsc`, ESLint
(0 errors), and `npm test` all pass. Remaining: on-device iOS archive,
end-to-end chat tap-through, and the push destination.

## Resolved

- [x] **1. User-facing display name → `EkamCore`.** Changed `CFBundleDisplayName`
  (iOS `ios/EkamCore/Info.plist`), `app_name` (Android
  `android/app/src/main/res/values/strings.xml`), and `displayName` (`app.json`)
  from `LockChat AI` to `EkamCore`. Also updated in-app text (SplashScreen,
  Settings), the download `User-Agent`, and docs.

- [x] **2. Bundle identifier → `com.ekamcore` (verified consistent).** iOS
  `PRODUCT_BUNDLE_IDENTIFIER` (both Debug + Release configs) and Android
  `applicationId`/`namespace` all read `com.ekamcore`. No registered store ID was
  provided, so the migration default stands.

- [x] **3. Jest test setup fixed — `npm test` passes (exit 0).** Added
  `jest.setup.js` mocking the native modules (`llama.rn`, `react-native-blob-util`,
  `@react-native-async-storage/async-storage`, `@react-native-clipboard/clipboard`,
  `react-native-safe-area-context`), extended `transformIgnorePatterns`, and
  enabled fake timers so `SplashScreen`'s `setTimeout` can't fire post-teardown.
  The smoke test now unmounts the renderer. ESLint override added so the Jest
  config/setup files lint clean.

- [x] **4. Node version locked.** `package.json` requires `>= 22.11.0`. `nvm`
  was not installed and Homebrew had only `node@20`/`node@24`, so we use the
  already-installed **Node 24** (satisfies the engines floor) and added `.nvmrc`
  pinned to `24`.

- [x] **5a. iOS native build — verified.** `cd ios && pod install` (80 pods).
  Debug build builds, installs, and launches on the iPhone 17 Pro (iOS 26.5)
  simulator; the onboarding UI renders. Release build (`-configuration Release
  -sdk iphonesimulator`) reports `** BUILD SUCCEEDED **` with an embedded
  `main.jsbundle`. Note: Xcode 26.5 needed `xcodebuild -downloadPlatform iOS`
  first — the iOS 26.5 simulator runtime was missing, which had blocked *all*
  simulator destination resolution.

- [x] **5b. Android native build — verified.** Installed the missing SDK pieces
  (platform 36, build-tools 36.0.0, NDK 27.1.12297006, CMake 3.22.1, emulator,
  `system-images;android-36;google_apis;arm64-v8a`) into the existing Homebrew
  SDK root, created an AVD (`ekam_test`, API 36 arm64), and ran
  `./gradlew :app:assembleDebug` → `BUILD SUCCESSFUL` (incl. the native
  llama.cpp NDK/CMake compile; ~220 MB APK). Installed + launched on the
  emulator; the Chat screen renders. `android/local.properties` (gitignored)
  points `sdk.dir` at `/opt/homebrew/share/android-commandlinetools`.

## Still open

- [ ] **5c. On-device iOS Release / archive.** Only simulator builds verified.
  A signed device build/archive needs the dev Team (`P3P44YNXFN`) and is subject
  to free-profile limits (3 apps / 7-day expiry). Decide when to do a real device
  install.

- [ ] **5d. End-to-end chat verification.** App launches and renders, but
  download → load → chat was not driven (no UI-automation tooling installed:
  `idb`/`cliclick` absent). Verify by tapping through the running simulator, or
  install `idb` to automate it.

- [x] **6. Push — done.** Created an orphan branch `app-main` (clean app-only
  root commit, no old-product history; tree identical to `development`'s tracked
  files) and pushed it to `origin` (`poddarhi/EkamCore`). It's isolated from
  `development` (the old product's line) and from `main`. The old-product history
  remains on `development` if ever needed.

## Done (earlier)

- [x] Migrated the on-device LLM app into this repo; preserved `docs/` and
  top-level product docs.
- [x] Renamed internal identifiers `LocalLLM` → `EkamCore` across iOS, Android,
  and JS; AsyncStorage keys `localllm.*` → `ekamcore.*`.
- [x] Consolidated README (app README is canonical, rebranded EkamCore); old
  product README archived to `docs/EKAMCORE_PRODUCT_README.md`.

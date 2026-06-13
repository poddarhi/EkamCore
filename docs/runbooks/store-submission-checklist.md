# EkamCore — App Store & Google Play Submission Checklist

_Date: 2026-06-13 · For the Phase 0 soft launch. Status: pre-submission (nothing submitted yet)._

This lists **everything required** to upload EkamCore to the Apple App Store and the Google
Play Store. Items marked **🔴 BLOCKER** must be done before you can submit at all. Items marked
**⚠️** are EkamCore-specific gotchas discovered from the current build.

---

## 0. Hard blockers to know up front

| # | Blocker | Why | Store |
|---|---------|-----|-------|
| 1 | **🔴 Paid Apple Developer Program ($99/yr)** | Current iOS builds use a **free personal profile** (7-day expiry, 3-app limit). The App Store requires a paid membership. | Apple |
| 2 | **🔴 Replace the Android signing key** | The release APK is currently signed with the **debug keystore** (`signingConfigs.debug`). Play **rejects** debug-signed uploads — you must generate a real upload keystore. | Google |
| 3 | **🔴 Build an Android App Bundle (.aab)** | New Play apps must upload an **.aab**, not an APK. We've only built APKs so far. | Google |
| 4 | **🔴 Public Privacy Policy URL** | **Both** stores require a hosted privacy policy URL. | Both |
| 5 | **🔴 Google Play Developer account ($25 one-time)** | Required to publish on Play. | Google |

---

## 1. Apple App Store

### Accounts & legal
- [ ] 🔴 Apple Developer Program membership active ($99/yr).
- [ ] App Store Connect access; **Agreements, Tax, and Banking** completed (free apps still need the Paid/Free agreement accepted).

### App identity & signing
- [ ] Explicit **App ID** registered for `com.ekamcore` (not wildcard) in the Developer portal.
- [ ] **Distribution certificate** + **App Store provisioning profile** (or Xcode automatic signing with the paid team).
- [ ] App record created in **App Store Connect** (name "EkamCore", primary language, bundle id, SKU).
- [ ] Marketing **version** (e.g. 1.0.0) + **build number** (increment every upload).

### Build & upload
- [ ] Archive in **Release**, signed for **distribution**, uploaded via Xcode Organizer or **Transporter**.
- [ ] arm64 device build (already how we build).
- [ ] ⚠️ **`PrivacyInfo.xcprivacy` privacy manifest** present and accurate — declare required-reason APIs (file timestamp / disk space / `UserDefaults`; `RNDeviceInfo` already ships a privacy bundle — confirm it covers what we call).
- [ ] ⚠️ **Export compliance**: set `ITSAppUsesNonExemptEncryption = NO` in `Info.plist` if we only use standard HTTPS (we do) — avoids the per-upload encryption questionnaire.

### Store listing assets
- [ ] **App icon** 1024×1024 (no alpha/transparency) + full icon set in the asset catalog.
- [ ] **Screenshots**: 6.9"/6.7" iPhone set is **mandatory**; add 6.5"/5.5" and iPad sets if those are supported.
- [ ] (Optional) App preview video.
- [ ] **Subtitle**, **promotional text**, **description**, **keywords**.
- [ ] **Support URL** (required), Marketing URL (optional).
- [ ] 🔴 **Privacy Policy URL**.

### Review & compliance
- [ ] **App Privacy** nutrition label — EkamCore is on-device; if nothing leaves the device, declare **"Data Not Collected"** (a genuine selling point — keep it true).
- [ ] **Age rating** questionnaire.
- [ ] ⚠️ **Review notes**: explain that LLM **models are downloaded on-device at the user's request** (large GGUF files) and that chat runs fully offline — heads off reviewer confusion.
- [ ] No demo account needed (no login).
- [ ] (Recommended) Push a **TestFlight** build first for a real-device beta before production review.

---

## 2. Google Play Store

### Accounts & legal
- [ ] 🔴 Play **Developer account** ($25 one-time) + Developer Distribution Agreement accepted.
- [ ] Payments profile (needed even for free apps).

### App identity & signing
- [ ] `applicationId com.ekamcore` (already set).
- [ ] 🔴 Generate a **release/upload keystore** and wire it into `android/app/build.gradle` (replace the `signingConfigs.debug` reference for `release`). Store the keystore + passwords safely (losing it loses the ability to update the app, unless using Play App Signing).
- [ ] Enrol in **Play App Signing** (Google holds the app signing key; you upload with your upload key).
- [ ] **versionCode** (integer, increment every upload) + **versionName**.
- [ ] ⚠️ Confirm **targetSdkVersion** meets Play's current minimum (Play requires targeting a recent API level — verify against the current requirement and bump if needed).

### Build & upload
- [ ] 🔴 Build a signed **Android App Bundle**: `./gradlew :app:bundleRelease` → `app-release.aab` (not the APK we've been making).
- [ ] arm64 + armeabi-v7a/x86_64 ABIs as appropriate (RN handles; AAB splits per device).

### Store listing assets
- [ ] **App icon** 512×512 (32-bit PNG).
- [ ] **Feature graphic** 1024×500.
- [ ] **Phone screenshots** (min 2, up to 8); tablet screenshots if supporting tablets.
- [ ] **Short description** (≤80 chars) + **full description** (≤4000 chars).
- [ ] **App category** + tags; **contact email** (required).
- [ ] 🔴 **Privacy Policy URL**.

### Play Console declarations (all required to publish)
- [ ] **Data safety** form — Play's privacy disclosure; declare collection/sharing (on-device → minimal/none, matched to reality).
- [ ] **Content rating** (IARC questionnaire).
- [ ] **Target audience & content** (age groups).
- [ ] **Ads** declaration (no ads → declare "no ads").
- [ ] **Government app / financial / health** declarations (all N/A).
- [ ] Select **countries/regions** + **pricing** (free).

### Release flow (recommended)
- [ ] Start with **Internal testing** track → **Closed** → **Open** → **Production**. Internal testing first catches signing/AAB issues fast.

---

## 3. Shared assets to produce once (used by both stores)

- [ ] **Privacy policy** (host it — e.g. a GitHub Pages / simple site). Since EkamCore is privacy-first and on-device, the policy is short and is itself marketing.
- [ ] **App icon** master (export 1024² for Apple, 512² for Play).
- [ ] **Screenshots** captured on real devices (we have the iPhone + emulator running) — chat screen, model catalog, a recall/long-chat moment.
- [ ] **Copy**: app name, subtitle/short description, full description, keywords.
- [ ] **Category** decision (suggest **Productivity** or **Utilities**).
- [ ] ⚠️ Decide how to message **runtime model downloads** (hundreds of MB, Wi-Fi recommended) in the description so users aren't surprised.

---

## 4. Fastest path to first submission (suggested order)

1. Buy both developer accounts (Apple $99/yr, Google $25 once). *(blockers 1 + 5)*
2. Write + host the privacy policy. *(blocker 4)*
3. Android: create upload keystore, wire release signing, build `.aab`, push to **Internal testing**. *(blockers 2 + 3)*
4. iOS: with the paid account, archive + upload to **TestFlight**.
5. Produce icon + screenshots + copy once; fill both store listings.
6. Complete each store's privacy/data + rating declarations.
7. Submit to review (Play first — usually faster; Apple review can take longer).

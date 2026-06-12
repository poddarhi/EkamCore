# On-Device Vision Models + Gated Photo Attach — Design

_Date: 2026-06-12 · Status: design approved (3 sections), pending written-spec review_

This cycle adds **image/vision** support to EkamCore's on-device chat: model
**categorization**, a **gated attach→download** flow for photos, and **vision
inference + display**. Voice input is a **separate next cycle** that reuses this
cycle's categorization + gating backbone. Video is **out** (not feasible on-device).

---

## 1. Motivation & feasibility

Two pre-publish limitations were raised: (1) no voice input, (2) no image/video models
with a gated attach flow + model categorization. Feasibility was checked against the
actual dependencies before designing:

- ✅ **Image/vision — feasible on-device.** `llama.rn` 0.12.4 already exposes multimodal
  vision: `initMultimodal`, `getMultimodalSupport → {vision, audio}`, a media marker
  (`RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER`), and `image_url` in completions. A vision model
  is **two files**: the base GGUF **+ an mmproj projector**.
- ✅ **Voice — feasible** (next cycle): on-device STT (whisper.rn for offline, matching
  the privacy positioning) → text → existing chat. Deferred.
- ❌ **Video — NOT feasible on-device.** No on-device video-understanding LLM runs on a
  phone; llama.cpp/llama.rn do image + audio, not video. Dropped. Heavy vision/video is a
  future capability of the **desktop bridge** (separate spec
  `2026-06-12-desktop-pairing-bridge-design.md`), where a paired computer can run models
  the phone can't.

**Shared insight:** voice and vision share one pattern — *a capability is locked until its
model is downloaded; tapping it when absent routes to the right Models category, then it
lights up.* So **categorization + the gating mechanism is a reusable backbone**, and vision
(this cycle) and voice (next) are two consumers of it.

---

## 2. Scope this cycle

| | Piece | This cycle? |
|---|---|---|
| **A** | Model categorization (catalog `kind`, Models screen sections, capability resolver) | **YES — foundation** |
| **C** | Image/vision: gated attach (library + camera), two-file download, inference, display | **YES** |
| **B** | Voice input (mic → STT → chat) | No — next cycle, reuses A's backbone |
| **D** | Video | No — infeasible on-device |

---

## 3. Locked decisions

- **One model at a time** (phone RAM). A chosen vision model becomes the **active/loaded**
  model and handles both the image and ongoing text (vision models do text too).
- **Gate behavior when an attach action is tapped** (the resolved rule):
  - **No vision model downloaded** → don't open the picker; route to **Models → Vision** to
    download (manual choice there).
  - **Exactly one downloaded** → select it silently.
  - **More than one downloaded** → quick in-place chooser ("Use which image model?") → pick.
  - Then ensure that model is active (swap + `initMultimodal` if needed), then launch
    library/camera.
- **Attach sources:** Photo Library + Camera (video dropped).
- **Image-picker library:** `react-native-image-picker` (handles both library + camera;
  lighter than vision-camera for this need).
- **Casing:** new UI copy follows the app-wide **Title Case** convention for short
  labels/badges (separate copy-polish pass tracks the rest).

---

## 4. Section 1 — Categorization & data model (foundation)

- **`ModelInfo`** gains: `kind: 'text' | 'vision'` (existing entries implicitly `text`,
  backward-compatible); `mmprojUrl?: string` + `mmprojSizeBytes?: number` (vision needs the
  second projector file).
- **A vision model is "downloaded" only when BOTH** the base GGUF and its mmproj are present
  and verified.
- **Models screen** is sectioned by kind — a **Text** group and a **Vision** group (same card
  style, labeled sections). Vision cards show the **combined** size (base + mmproj) and a
  **Vision** badge so the larger download is honest up front.
- **Capability resolver** — new `src/services/capabilities.ts` answers "which downloaded
  models satisfy capability X?" e.g. `downloadedVisionModels()`. The attach gate (this cycle)
  and the voice gate (next cycle) both consume it.
- **Download service** learns about an optional companion file; "ready" = base + mmproj both
  verified.

## 5. Section 2 — Attach flow & vision inference

- **Entry:** the existing "+" sheet (`ChatPlusSheet`) gains **"Photo Library"** and
  **"Camera"** actions. New permissions, properly filled: `NSCameraUsageDescription` +
  `NSPhotoLibraryUsageDescription` (iOS), camera permission (Android).
- **Gate** (Section 3 decisions above): resolve `downloadedVisionModels()` → none = route to
  Models/Vision; one = use; many = in-place chooser. Ensure chosen model is active; if not,
  swap (unload text model, load vision GGUF, `initMultimodal(mmprojPath)`) with a visible
  **"Loading <model>…"** state (swap takes seconds). Then launch the picker/camera.
- **Inference:** picked image is copied into app storage (persists), downscaled to a sane max
  dimension, and sent via `llama.rn`'s multimodal API (media marker / `image_url` with the
  local path) **alongside the user's typed prompt**. Response **streams** through the existing
  generation path.
- **Display & persistence:** the user's message bubble renders a **thumbnail + text**;
  `MessageBubble` and the conversation message model gain an optional `imagePath` so attached
  images survive in history.
- **Errors:** permission denied → prompt to enable in Settings; multimodal init fails
  (bad/mismatched mmproj) → clear error; image too large → downscaled; low-RAM swap failure →
  graceful message (device-aware sizing already helps).

## 6. Section 3 — Catalog, files, testing

**Seed vision models** (each = base GGUF + mmproj; URLs/sizes verified at implementation,
same as the text catalog):
- **SmolVLM-500M Instruct** — tiny & fast; the "first vision model to try."
- **Qwen2-VL-2B Instruct** — more capable, larger; the "good results" option.

**Files touched** (small, focused units):
- `types.ts` — `ModelInfo.{kind, mmprojUrl, mmprojSizeBytes}` + message `imagePath`
- `src/data/models.ts` — vision entries
- `src/services/download.ts` — two-file download (ready only when both verified)
- `src/services/llama.ts` — `initMultimodal` + image completion
- **new** `src/services/capabilities.ts` — `downloadedVisionModels()`
- `src/screens/ModelsScreen.tsx` — sections + Vision badge
- `src/components/ChatPlusSheet.tsx` — attach actions + gate + chooser
- `src/screens/ChatScreen.tsx` — wire attach → gate → picker → send
- `src/components/MessageBubble.tsx` — image thumbnail
- `src/context/AppContext.tsx` — attachment state + model swap
- `src/services/conversations.ts` — persist `imagePath`
- iOS `Info.plist` (camera + photo descriptions) + `pod install`; Android manifest (camera)
- **new dep** `react-native-image-picker`

**Testing.**
- Unit (pure, matching existing `remote.ts`/`catalog.ts` style): capability resolver,
  two-file download readiness, `kind` handling.
- Device: three gate states (none / one / many), model swap, inference, image-in-history,
  permission-denied paths. Multimodal inference is device-only (not unit-testable).

---

## 7. Risks to validate early

- Exact `llama.rn` 0.12.4 multimodal call shape (image_url vs media marker; message format).
- Finding small vision **GGUF + matching mmproj** pairs that actually run within phone RAM.
- `react-native-image-picker` compatibility with **RN 0.85 new architecture** (and the
  from-source React setup).
- Model-swap latency UX (seconds-long load when switching text → vision).

## 8. Open items for the implementation plan

- Confirm seed model URLs (base + mmproj) and combined sizes.
- Final `llama.rn` multimodal wiring (init + per-message image attach + streaming).
- Image storage location, downscale target dimension, and thumbnail rendering.
- In-place vision-model chooser UI (reuse existing sheet/picker patterns).
- Permission request UX copy (Title Case).

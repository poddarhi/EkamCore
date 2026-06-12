# Multimodal Vision + Gated Photo Attach — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-device image understanding to EkamCore: vision-capable models (base GGUF + mmproj projector), a gated "attach photo" flow that routes to a download when no vision model is present, multimodal inference via `llama.rn`, and image-in-history display.

**Architecture:** Build on the existing single-model-at-a-time design. A vision model is two files (base + mmproj); it counts as downloaded only when both are present. Loading a vision model calls `initMultimodal(mmprojPath)` after `initLlama`. Sending a photo copies/downscales it into app storage, prepends the `<__media__>` marker to the user turn, and passes `media_paths` to `completion()`. A pure capability resolver answers "which downloaded models can see images?" and drives the attach gate.

**Tech Stack:** React Native 0.85 (new arch), TypeScript strict, `llama.rn` 0.12.4 (multimodal: `initMultimodal` / `getMultimodalSupport` / `media_paths` + `RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER`), `react-native-image-picker` 8.x, `react-native-blob-util` (storage), AsyncStorage (persistence), Jest.

---

## Deviation from spec (read first)

The spec (`docs/superpowers/specs/2026-06-12-multimodal-vision-attach-design.md`) proposes a new `ModelInfo.kind: 'text' | 'vision'` field. **The codebase already has `ModelInfo.vision?: boolean`** (`src/types.ts:40-41`) and it is already consumed by `ChatPlusSheet.tsx:44` (`loadedModel?.vision`). To stay DRY and avoid a parallel taxonomy, this plan **uses the existing `vision: boolean`** as the category discriminator and adds only the two new fields the spec actually requires for the second file: `mmprojUrl?` and `mmprojSizeBytes?`. "Vision section" on the Models screen = `models.filter(m => m.vision)`. Everything else in the spec is implemented as written.

## Verified facts (checked at planning time, 2026-06-12)

- `llama.rn` 0.12.4 exposes: `context.initMultimodal({ path, use_gpu?, image_min_tokens?, image_max_tokens? }): Promise<boolean>`, `getMultimodalSupport(): Promise<{vision, audio}>`, `isMultimodalEnabled()`, `releaseMultimodal()`. `completion()` accepts top-level `media_paths?: string | string[]`. The media marker constant is `RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER === '<__media__>'`.
- `react-native-image-picker` latest is `8.2.1` (supports the new architecture; provides both `launchImageLibrary` and `launchCamera` with `maxWidth`/`maxHeight`/`quality` downscaling).
- Seed models (HEAD-verified URLs + exact `content-length`):
  - **SmolVLM-500M Instruct** — base `SmolVLM-500M-Instruct-Q8_0.gguf` = 436,806,912 B (~437 MB); mmproj `mmproj-SmolVLM-500M-Instruct-Q8_0.gguf` = 108,783,360 B (~109 MB). Combined ~546 MB. Repo: `ggml-org/SmolVLM-500M-Instruct-GGUF`.
  - **Qwen2-VL-2B Instruct** — base `Qwen2-VL-2B-Instruct-Q4_K_M.gguf` = 986,046,944 B (~986 MB); mmproj `mmproj-Qwen2-VL-2B-Instruct-Q8_0.gguf` = 709,883,360 B (~710 MB). Combined ~1.7 GB. Repo: `ggml-org/Qwen2-VL-2B-Instruct-GGUF`.

## File structure (what changes and why)

| File | Responsibility / change |
|---|---|
| `src/types.ts` | `ModelInfo.mmprojUrl?`, `mmprojSizeBytes?`; `ChatMessage.imagePath?` |
| `src/data/models.ts` | Two vision catalog entries (real URLs + sizes above) |
| `src/services/download.ts` | `mmprojFilePath()`, `requiredFilesFor()` (pure), two-file `isModelDownloaded`, mmproj-aware list/delete, `startMmprojDownload` |
| `src/services/capabilities.ts` | **new** — pure `downloadedVisionModels()`, `isVisionModel()` |
| `src/services/llama.ts` | `loadModel(..., mmprojPath?)` → `initMultimodal`; `generate()` accepts `imagePath?` → `media_paths` + marker |
| `src/services/conversations.ts` | persist `imagePath` |
| `src/context/AppContext.tsx` | download mmproj alongside base; load passes mmproj path; `sendMessage(text, imagePath?)`; copy image to storage; persist imagePath |
| `src/components/ChatPlusSheet.tsx` | Photo/Camera always tappable → gate (none/one/many) → callback up to ChatScreen |
| `src/screens/ChatScreen.tsx` | pending-image state; launch picker/camera; pass imagePath to send |
| `src/components/MessageBubble.tsx` | render `imagePath` thumbnail |
| `src/screens/ModelsScreen.tsx` | Vision section + combined-size + Vision badge |
| `ios/EkamCore/Info.plist` | `NSCameraUsageDescription`, `NSPhotoLibraryUsageDescription` |
| `android/app/src/main/AndroidManifest.xml` | `CAMERA` permission |
| `__tests__/capabilities.test.ts` | **new** — resolver + `isVisionModel` |
| `__tests__/download.test.ts` | **new** — `requiredFilesFor` pure test |
| `__tests__/conversations.test.ts` | add imagePath persistence case |

Implement tasks **in order** (later tasks depend on earlier types/functions). Commit after each task.

---

### Task 1: Data model — vision fields + message imagePath

**Files:**
- Modify: `src/types.ts:40-41` (ModelInfo), `src/types.ts:54-62` (ChatMessage)

- [ ] **Step 1: Add mmproj fields to `ModelInfo`**

Replace the existing `vision?` line (`src/types.ts:40-41`):

```typescript
  /** True if the model can understand images (base GGUF + mmproj projector). */
  vision?: boolean;
  /** Direct download URL for the multimodal projector (mmproj) file. Vision only. */
  mmprojUrl?: string;
  /** Approximate mmproj download size in bytes (for honest combined-size UI). */
  mmprojSizeBytes?: number;
```

- [ ] **Step 2: Add `imagePath` to `ChatMessage`**

Replace `src/types.ts:54-62`:

```typescript
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** Local filesystem path to an attached image (user turns only). */
  imagePath?: string;
  /** transient flag while the assistant token stream is in flight */
  streaming?: boolean;
  /** tokens-per-second once generation finishes */
  tokensPerSecond?: number;
}
```

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS (no errors; new optional fields are backward-compatible).

- [ ] **Step 4: Commit**

```bash
git add src/types.ts
git commit -m "feat(types): add vision mmproj fields and message imagePath"
```

---

### Task 2: Catalog — seed vision models

**Files:**
- Modify: `src/data/models.ts` (append two entries to `CATALOG`)
- Test: `__tests__/catalog.test.ts` (add assertions if the file already validates catalog invariants; otherwise skip — covered by Task 3 resolver tests)

- [ ] **Step 1: Add the two vision entries**

Insert these objects into the `CATALOG` array in `src/data/models.ts` (place after the existing text entries, before any custom/closing bracket). Use exact verified URLs and sizes:

```typescript
  {
    id: 'smolvlm-500m-instruct-q8',
    name: 'SmolVLM 500M Instruct',
    description: 'Tiny vision model — the first to try for on-device image chat.',
    params: '500M',
    quant: 'Q8_0',
    sizeBytes: 436_806_912,
    url: 'https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF/resolve/main/SmolVLM-500M-Instruct-Q8_0.gguf',
    vision: true,
    mmprojUrl:
      'https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF/resolve/main/mmproj-SmolVLM-500M-Instruct-Q8_0.gguf',
    mmprojSizeBytes: 108_783_360,
    publisher: 'Hugging Face',
    tagline: 'See images on any phone',
    goodFor: ['Vision', 'Chat'],
    license: 'Apache-2.0',
  },
  {
    id: 'qwen2-vl-2b-instruct-q4',
    name: 'Qwen2-VL 2B Instruct',
    description: 'More capable vision model. Larger download, better answers.',
    params: '2B',
    quant: 'Q4_K_M',
    sizeBytes: 986_046_944,
    url: 'https://huggingface.co/ggml-org/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf',
    vision: true,
    mmprojUrl:
      'https://huggingface.co/ggml-org/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-Q8_0.gguf',
    mmprojSizeBytes: 709_883_360,
    publisher: 'Qwen (Alibaba)',
    tagline: 'Stronger on-device vision',
    goodFor: ['Vision', 'Chat'],
    license: 'Apache-2.0',
  },
```

- [ ] **Step 2: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Run existing catalog tests (guard against shape regressions)**

Run: `npx jest catalog --silent`
Expected: PASS (or "no tests" — either is fine; no failures).

- [ ] **Step 4: Commit**

```bash
git add src/data/models.ts
git commit -m "feat(catalog): add SmolVLM-500M and Qwen2-VL-2B vision models"
```

---

### Task 3: Capability resolver (pure, TDD)

**Files:**
- Create: `src/services/capabilities.ts`
- Test: `__tests__/capabilities.test.ts`

- [ ] **Step 1: Write the failing test**

Create `__tests__/capabilities.test.ts`:

```typescript
import { ModelInfo } from '../src/types';
import {
  isVisionModel,
  downloadedVisionModels,
} from '../src/services/capabilities';

const model = (over: Partial<ModelInfo> = {}): ModelInfo => ({
  id: 'm1',
  name: 'M1',
  description: '',
  sizeBytes: 1,
  url: 'u',
  params: '1B',
  quant: 'Q4',
  ...over,
});

describe('isVisionModel', () => {
  it('is true only when vision flag set', () => {
    expect(isVisionModel(model({ vision: true }))).toBe(true);
    expect(isVisionModel(model({ vision: false }))).toBe(false);
    expect(isVisionModel(model())).toBe(false);
  });
});

describe('downloadedVisionModels', () => {
  const models = [
    model({ id: 'text1' }),
    model({ id: 'vis1', vision: true }),
    model({ id: 'vis2', vision: true }),
  ];

  it('returns only vision models whose id is downloaded', () => {
    const out = downloadedVisionModels(models, ['text1', 'vis2']);
    expect(out.map(m => m.id)).toEqual(['vis2']);
  });

  it('returns empty when no vision model is downloaded', () => {
    expect(downloadedVisionModels(models, ['text1'])).toEqual([]);
  });

  it('returns all downloaded vision models for the many case', () => {
    const out = downloadedVisionModels(models, ['vis1', 'vis2']);
    expect(out.map(m => m.id)).toEqual(['vis1', 'vis2']);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest capabilities --silent`
Expected: FAIL ("Cannot find module '../src/services/capabilities'").

- [ ] **Step 3: Write minimal implementation**

Create `src/services/capabilities.ts`:

```typescript
import { ModelInfo } from '../types';

/** A model can understand images when its `vision` flag is set. */
export function isVisionModel(model: ModelInfo): boolean {
  return model.vision === true;
}

/**
 * The set of vision-capable models that are fully downloaded. `downloadedIds`
 * is the ground-truth ready list (a vision model only appears there once BOTH
 * its base GGUF and mmproj are present — see download.ts). The attach gate (and
 * the future voice gate) consume this to decide none/one/many.
 */
export function downloadedVisionModels(
  models: ModelInfo[],
  downloadedIds: string[],
): ModelInfo[] {
  return models.filter(m => isVisionModel(m) && downloadedIds.includes(m.id));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx jest capabilities --silent`
Expected: PASS (4 assertions).

- [ ] **Step 5: Commit**

```bash
git add src/services/capabilities.ts __tests__/capabilities.test.ts
git commit -m "feat(capabilities): add vision capability resolver"
```

---

### Task 4: Download service — two-file (base + mmproj)

**Files:**
- Modify: `src/services/download.ts` (paths, readiness, list, delete, mmproj fetch)
- Test: `__tests__/download.test.ts` (pure `requiredFilesFor` only — fs is native)

Background: `MODELS_DIR` and `modelFilePath(model)` (`${MODELS_DIR}/${model.id}.gguf`) already exist (`download.ts:7-12`). mmproj uses a sibling name `${model.id}.mmproj.gguf`.

- [ ] **Step 1: Write the failing test**

Create `__tests__/download.test.ts`:

```typescript
import { ModelInfo } from '../src/types';
import { requiredFilesFor } from '../src/services/download';

const model = (over: Partial<ModelInfo> = {}): ModelInfo => ({
  id: 'm1',
  name: 'M1',
  description: '',
  sizeBytes: 1,
  url: 'u',
  params: '1B',
  quant: 'Q4',
  ...over,
});

describe('requiredFilesFor', () => {
  it('text model requires only the base gguf', () => {
    const files = requiredFilesFor(model());
    expect(files).toHaveLength(1);
    expect(files[0]).toMatch(/m1\.gguf$/);
  });

  it('vision model requires base gguf + mmproj', () => {
    const files = requiredFilesFor(model({ vision: true, mmprojUrl: 'mm' }));
    expect(files).toHaveLength(2);
    expect(files[0]).toMatch(/m1\.gguf$/);
    expect(files[1]).toMatch(/m1\.mmproj\.gguf$/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest download --silent`
Expected: FAIL ("requiredFilesFor is not a function" / not exported).

- [ ] **Step 3: Add `mmprojFilePath` + `requiredFilesFor` and make readiness two-file**

In `src/services/download.ts`, add after `modelFilePath` (after line 12):

```typescript
export function mmprojFilePath(model: ModelInfo): string {
  return `${MODELS_DIR}/${model.id}.mmproj.gguf`;
}

/** All files that must be present on disk for this model to be usable. */
export function requiredFilesFor(model: ModelInfo): string[] {
  const files = [modelFilePath(model)];
  if (model.mmprojUrl) {
    files.push(mmprojFilePath(model));
  }
  return files;
}
```

Replace `isModelDownloaded` (`download.ts:35-42`) so a vision model needs both files:

```typescript
export async function isModelDownloaded(model: ModelInfo): Promise<boolean> {
  for (const path of requiredFilesFor(model)) {
    if (!(await RNBlobUtil.fs.exists(path))) {
      return false;
    }
    // Base must be a few MB; an mmproj can be smaller but is still > 1 MB.
    if ((await fileSize(path)) < 1_000_000) {
      return false;
    }
  }
  return true;
}
```

In `listDownloadedModelIds` (`download.ts:54-64`), skip mmproj sidecars so they are never mistaken for a base model. Change the loop guard:

```typescript
    for (const f of files) {
      if (!f.endsWith('.gguf') || f.endsWith('.mmproj.gguf')) {
        continue;
      }
      const size = await fileSize(`${MODELS_DIR}/${f}`);
      if (size > 1_000_000) {
        ids.push(f.replace(/\.gguf$/, ''));
      }
    }
```

> Note: `listDownloadedModelIds` (launch fast-path) lists base files only. Full vision readiness (both files) is enforced by `isModelDownloaded`, which AppContext calls when computing `downloadedIds` (Task 7). An interrupted vision download leaves a base without mmproj; `isModelDownloaded` returns false, so it won't appear as ready.

- [ ] **Step 4: Make `deleteModel` remove the mmproj too**

Replace `deleteModel` (`download.ts:71-75`, the visible head) with a loop over required files:

```typescript
export async function deleteModel(model: ModelInfo): Promise<void> {
  for (const path of requiredFilesFor(model)) {
    if (await RNBlobUtil.fs.exists(path)) {
      await RNBlobUtil.fs.unlink(path);
    }
  }
}
```

- [ ] **Step 5: Add an mmproj download helper mirroring `startDownload`**

`startDownload(model, onProgress)` already streams the base to `${dest}.part` then moves it (`download.ts:92-153`). Add a sibling that downloads the mmproj to `mmprojFilePath`. Add after `startDownload`:

```typescript
/**
 * Download the mmproj companion for a vision model. Mirrors startDownload but
 * targets `${id}.mmproj.gguf`. Resolves when the file is verified (> 1 MB).
 */
export function startMmprojDownload(
  model: ModelInfo,
  onProgress: (received: number, total: number) => void,
): DownloadHandle {
  const dest = mmprojFilePath(model);
  const temp = `${dest}.part`;
  let task: StatefulPromise<FetchBlobResponse> | null = null;

  const run = async (): Promise<void> => {
    await ensureModelsDir();
    if (await RNBlobUtil.fs.exists(temp)) {
      await RNBlobUtil.fs.unlink(temp);
    }
    task = RNBlobUtil.config({ path: temp, fileCache: true }).fetch(
      'GET',
      model.mmprojUrl as string,
      { 'User-Agent': 'EkamCore/1.0 (llama.rn)' },
    );
    let last = 0;
    task.progress({ interval: 300 }, (received, total) => {
      last = Number(received);
      onProgress(Number(received), Number(total));
    });
    await task;
    const size = await fileSize(temp);
    if (size < 1_000_000) {
      await RNBlobUtil.fs.unlink(temp).catch(() => {});
      throw new Error(`mmproj download too small (${last} bytes)`);
    }
    if (await RNBlobUtil.fs.exists(dest)) {
      await RNBlobUtil.fs.unlink(dest);
    }
    await RNBlobUtil.fs.mv(temp, dest);
  };

  return {
    task: run(),
    cancel: () => {
      task?.cancel(() => {});
    },
  };
}
```

> If your local `startDownload` body differs (e.g. different `RNBlobUtil.config` options or header object), mirror **that** exact shape instead — read `download.ts:92-153` and copy its idiom. The contract that matters: stream to `.part`, verify > 1 MB, `mv` to final, expose `{ task, cancel }`.

- [ ] **Step 6: Typecheck + run pure test**

Run: `npx tsc --noEmit && npx jest download --silent`
Expected: PASS (2 assertions); tsc clean.

- [ ] **Step 7: Commit**

```bash
git add src/services/download.ts __tests__/download.test.ts
git commit -m "feat(download): two-file vision download (base + mmproj)"
```

---

### Task 5: llama.ts — multimodal init + image completion

**Files:**
- Modify: `src/services/llama.ts:1-3` (imports), `:21-45` (loadModel), `:58-118` (GenerateOptions + generate)

- [ ] **Step 1: Import the media marker**

Replace `src/services/llama.ts:1`:

```typescript
import { initLlama, LlamaContext, RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER } from 'llama.rn';
```

- [ ] **Step 2: Teach `loadModel` to init multimodal**

Replace the signature + body of `loadModel` (`llama.ts:21-45`). Add an optional `mmprojPath` param; after `initLlama`, call `initMultimodal` when given:

```typescript
export async function loadModel(
  modelId: string,
  filePath: string,
  onProgress?: (percent: number) => void,
  mmprojPath?: string,
): Promise<LoadedModel> {
  await releaseModel();

  const context = await initLlama(
    {
      model: filePath,
      use_mlock: false,
      use_mmap: true,
      n_ctx: 2048,
      n_gpu_layers: Platform.OS === 'ios' ? 99 : 0,
    },
    p => onProgress?.(p),
  );

  if (mmprojPath) {
    // Enable vision. use_gpu follows the same Metal/CPU split as the base model.
    const ok = await context.initMultimodal({
      path: mmprojPath,
      use_gpu: Platform.OS === 'ios',
    });
    if (!ok) {
      await context.release();
      throw new Error('Failed to enable vision (mmproj incompatible with this model).');
    }
  }

  current = { context, filePath, modelId };
  return current;
}
```

- [ ] **Step 3: Extend `GenerateOptions` with an optional image**

Replace `GenerateOptions` (`llama.ts:58-64`):

```typescript
export interface GenerateOptions {
  systemPrompt: string;
  history: ChatMessage[];
  temperature?: number;
  maxTokens?: number;
  onToken: (token: string) => void;
  /** Local image path to attach to the latest user turn (vision models). */
  imagePath?: string;
}
```

- [ ] **Step 4: Attach the image in `generate`**

In `generate` (`llama.ts:75-118`), the message array is built at lines 83-88 and `completion()` is called at lines 90-99. Replace the destructure + message-build + completion call so that, when `imagePath` is set, the marker is prepended to the most recent user message and `media_paths` is passed.

Replace lines 81 (`const { systemPrompt, ... } = options;`) through the `completion(` options object:

```typescript
  const { systemPrompt, history, temperature = 0.7, maxTokens = 512, imagePath } =
    options;

  const chatHistory = history.filter(m => m.role !== 'system');
  const messages = [
    { role: 'system', content: systemPrompt },
    ...chatHistory.map((m, i) => {
      // Prepend the media marker to the LAST user turn when an image is attached.
      const isLastUser =
        imagePath != null && m.role === 'user' && i === chatHistory.length - 1;
      return {
        role: m.role,
        content: isLastUser
          ? `${RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER}\n${m.content}`
          : m.content,
      };
    }),
  ];

  const started = Date.now();
  let tokenCount = 0;

  const result = await current.context.completion(
    {
      messages,
      jinja: true,
      n_predict: maxTokens,
      temperature,
      stop: ['<|im_end|>', '<|eot_id|>', '<|end_of_text|>', '</s>'],
      ...(imagePath ? { media_paths: [imagePath] } : {}),
    },
    data => {
      if (data.token) {
        tokenCount += 1;
        options.onToken(data.token);
      }
    },
  );
```

> `media_paths` wants a bare filesystem path (no `file://`). The caller (Task 6) strips the scheme before storing `imagePath`.

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS. (`media_paths` and `initMultimodal` are typed in `llama.rn` 0.12.4 — verified.)

- [ ] **Step 6: Commit**

```bash
git add src/services/llama.ts
git commit -m "feat(llama): multimodal init + per-message image attach"
```

---

### Task 6: Persist imagePath (TDD) + image storage helper

**Files:**
- Modify: `src/services/conversations.ts:44-50` (persist imagePath)
- Modify: `src/services/download.ts` (add `chatImagesDir` + `persistChatImage`)
- Test: `__tests__/conversations.test.ts` (add a case)

- [ ] **Step 1: Add the failing persistence test**

Append to `__tests__/conversations.test.ts` (reuse its existing `msg`/`meta` factories; if `msg` doesn't accept image, add a literal object as below):

```typescript
describe('image attachments', () => {
  it('persists and restores imagePath alongside content', async () => {
    const messages: ChatMessage[] = [
      { id: 'u1', role: 'user', content: 'what is this?', imagePath: '/img/a.jpg' },
      { id: 'a1', role: 'assistant', content: 'a cat', tokensPerSecond: 12 },
    ];
    const m = meta({ id: 'cimg' });
    await saveConversation(m, messages);
    const loaded = await loadMessages('cimg');
    expect(loaded[0].imagePath).toBe('/img/a.jpg');
    expect(loaded[1].imagePath).toBeUndefined();
  });
});
```

> Ensure `ChatMessage` and any needed factories are imported at the top of the test file (they already are for the existing suites). `meta`/`saveConversation`/`loadMessages` are already used in this file.

- [ ] **Step 2: Run to verify it fails**

Run: `npx jest conversations --silent`
Expected: FAIL (`loaded[0].imagePath` is `undefined` — not yet persisted).

- [ ] **Step 3: Persist `imagePath` in `saveConversation`**

In `src/services/conversations.ts`, replace the `clean` map (`:45-50`):

```typescript
  const clean = messages.map(m => ({
    id: m.id,
    role: m.role,
    content: m.content,
    ...(m.imagePath != null ? { imagePath: m.imagePath } : {}),
    ...(m.tokensPerSecond != null ? { tokensPerSecond: m.tokensPerSecond } : {}),
  }));
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx jest conversations --silent`
Expected: PASS (existing cases + the new one).

- [ ] **Step 5: Add a chat-image storage helper to download.ts**

Picked images live in temp dirs that the OS may purge; copy into the app's Documents so history survives. Add to `src/services/download.ts` (near `MODELS_DIR`):

```typescript
const CHAT_IMAGES_DIR = `${RNBlobUtil.fs.dirs.DocumentDir}/chat-images`;

/**
 * Copy a picked image into persistent app storage and return a bare filesystem
 * path (no scheme) suitable for both `<Image>` display and llama.rn media_paths.
 */
export async function persistChatImage(srcUri: string, id: string): Promise<string> {
  const exists = await RNBlobUtil.fs.exists(CHAT_IMAGES_DIR);
  if (!exists) {
    await RNBlobUtil.fs.mkdir(CHAT_IMAGES_DIR);
  }
  const src = srcUri.replace(/^file:\/\//, '');
  const dest = `${CHAT_IMAGES_DIR}/${id}.jpg`;
  await RNBlobUtil.fs.cp(src, dest);
  return dest;
}
```

- [ ] **Step 6: Typecheck + full unit run**

Run: `npx tsc --noEmit && npx jest --silent`
Expected: PASS (all suites).

- [ ] **Step 7: Commit**

```bash
git add src/services/conversations.ts src/services/download.ts __tests__/conversations.test.ts
git commit -m "feat(storage): persist message imagePath + chat-image copy helper"
```

---

### Task 7: AppContext — download mmproj, load with vision, sendMessage(image)

**Files:**
- Modify: `src/context/AppContext.tsx` — `download`, `load`, `runSend`/`sendMessage`, imports

This wires the services together. Read the current `download`, `load` (`~:371-387`), and `runSend` (`~:459-617`) before editing; match their existing idiom (state setters, error handling). The required behavior changes:

- [ ] **Step 1: Import the new helpers**

Add to the existing imports from `../services/download`:

```typescript
import {
  // ...existing imports (modelFilePath, startDownload, isModelDownloaded, etc.)...
  mmprojFilePath,
  startMmprojDownload,
  persistChatImage,
} from '../services/download';
```

- [ ] **Step 2: Download the mmproj after the base, for vision models**

In the `download(model)` action, after the base `startDownload` completes successfully and before marking the model ready / adding its id to `downloadedIds`, chain the mmproj when present. Insert into the success path:

```typescript
        if (model.mmprojUrl) {
          // Vision model: also fetch the projector. Readiness requires both.
          await new Promise<void>((resolve, reject) => {
            const h = startMmprojDownload(model, (received, total) => {
              // Surface combined progress against base+mmproj total when known.
              setDownloads(d => ({
                ...d,
                [model.id]: {
                  ...(d[model.id] ?? {}),
                  received,
                  total,
                  phase: 'mmproj',
                },
              }));
            });
            h.task.then(resolve).catch(reject);
          });
        }
```

> Adapt the `setDownloads` shape to whatever `DownloadState` actually is in this file (the agent map noted `downloads: Record<string, DownloadState>`). If `DownloadState` has no `phase`, either add `phase?: 'base' | 'mmproj'` to its type or drop the field — the functional requirement is just "don't mark ready until mmproj finishes." After both files exist, recompute readiness via `isModelDownloaded(model)` exactly as the base-only flow does today.

- [ ] **Step 3: Load vision models with their mmproj**

In the `load(model)` action (`~:371-387`), pass the mmproj path when the model is a vision model:

```typescript
      await loadModel(
        model.id,
        modelFilePath(model),
        p => setLoadProgress(p),
        model.mmprojUrl ? mmprojFilePath(model) : undefined,
      );
```

Keep the rest (`setLoadedModelId`, `setActiveRemote(null)`, `saveLastModelId`) unchanged.

- [ ] **Step 4: Extend `sendMessage` / `runSend` to carry an image**

Change the public `sendMessage` signature to accept an optional image and thread it into the user message + the `generate` call.

Update the type in the `AppState` interface (the `sendMessage` field):

```typescript
  sendMessage: (text: string, imagePath?: string) => Promise<void>;
```

Update the `sendMessage` wrapper (`~:619-622`):

```typescript
  const sendMessage = useCallback(
    (text: string, imagePath?: string) => runSend(text, messages, imagePath),
    [runSend, messages],
  );
```

In `runSend(text, history, imagePath?)`:
1. Add `imagePath?: string` to its parameter list.
2. When building the user `ChatMessage` (the append at `~:461-470`), set `imagePath` on it (use the bare path returned by `persistChatImage` — see Step 5).
3. In the **local** generation branch (`~:523-531`), pass `imagePath` through to `generate({ ..., imagePath })`.
4. Leave the remote branch unchanged (remote vision is out of scope; if `imagePath` is set and `activeRemote` is active, fall back to text-only — the gate in Task 8 already prevents attaching when on remote).

Concretely, the user-message construction becomes:

```typescript
    const userMsg: ChatMessage = {
      id: makeId(),            // use whatever id helper this file already uses
      role: 'user',
      content: text,
      ...(imagePath ? { imagePath } : {}),
    };
```

and the local generate call:

```typescript
      const res = await generate({
        systemPrompt,
        history: nextHistory,   // whatever variable the existing call uses
        onToken: handleToken,   // existing callback
        imagePath,
      });
```

- [ ] **Step 5: Persist the image before send (in ChatScreen — see Task 9)**

`persistChatImage` is called from ChatScreen right after the user picks an image (Task 9), so by the time `sendMessage(text, persistedPath)` runs, `imagePath` is already a stable Documents path. No extra copy in AppContext.

- [ ] **Step 6: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS. Fix any signature mismatches surfaced by the compiler (this is the integration task — the types are the safety net).

- [ ] **Step 7: Commit**

```bash
git add src/context/AppContext.tsx
git commit -m "feat(context): vision download+load and image-aware sendMessage"
```

---

### Task 8: ChatPlusSheet — attach gate (none / one / many)

**Files:**
- Modify: `src/components/ChatPlusSheet.tsx:19-44` (props + state), `:93-110` (attach rows)

The sheet currently disables Photo unless the *loaded* model is vision (`supportsVision`, line 44). New behavior per spec: Photo/Camera are **always** tappable; on tap, resolve `downloadedVisionModels` → none routes to Models, one selects silently, many opens an in-place chooser; then ensure that model is active and bubble the chosen source up to ChatScreen to launch the picker.

- [ ] **Step 1: Add callback props + capability state**

Extend the component props (`:19-27`) to accept handlers from ChatScreen:

```typescript
export function ChatPlusSheet({
  visible,
  onClose,
  onGoToModels,
  onPickImage,
}: {
  visible: boolean;
  onClose: () => void;
  onGoToModels: () => void;
  /** Called once a vision model is active; source picks the input. */
  onPickImage: (source: 'library' | 'camera') => void;
}) {
```

Add to the `useApp()` destructure (`:30-40`): `models`, `downloadedIds`, `load`, `loadingModelId` are already there. Add a resolver call after line 44:

```typescript
  const visionModels = downloadedVisionModels(models, downloadedIds);
```

and import it at the top:

```typescript
import { downloadedVisionModels } from '../services/capabilities';
```

- [ ] **Step 2: Implement the gate handler**

Add inside the component (near `switchModel`, `~:69`):

```typescript
  const [chooserSource, setChooserSource] = useState<null | 'library' | 'camera'>(null);

  const beginAttach = (source: 'library' | 'camera') => {
    if (activeRemote) {
      return; // remote vision unsupported; row is disabled in this case
    }
    if (visionModels.length === 0) {
      onClose();
      onGoToModels(); // route to Models → download a vision model
      return;
    }
    if (visionModels.length === 1) {
      ensureActiveThenPick(visionModels[0].id, source);
      return;
    }
    setChooserSource(source); // many → show in-place chooser
  };

  const ensureActiveThenPick = async (modelId: string, source: 'library' | 'camera') => {
    if (modelId !== loadedModelId || activeRemote) {
      const m = models.find(x => x.id === modelId);
      if (m) {
        await load(m); // swaps + initMultimodal; shows "Loading…" via loadingModelId
      }
    }
    onClose();
    onPickImage(source);
  };
```

- [ ] **Step 3: Make the attach rows live**

Replace the two attach-related `AttachRow`s (`:93-110`). `AttachRow` is presentational (`:207-237`) — add an `onPress` prop to it and wire both rows. First extend `AttachRow`'s props/handler:

```typescript
function AttachRow({
  icon,
  label,
  sub,
  disabled,
  onPress,
  styles,
  colors,
}: {
  icon: IconName;
  label: string;
  sub: string;
  disabled?: boolean;
  onPress?: () => void;
  styles: ReturnType<typeof makeStyles>;
  colors: ThemeColors;
}) {
  return (
    <Pressable
      style={[styles.row, disabled && styles.rowDisabled]}
      disabled={disabled}
      onPress={onPress}>
      {/* keep the existing inner JSX (icon + labels) unchanged */}
    </Pressable>
  );
}
```

Then the rows:

```typescript
          <Text style={styles.sectionLabel}>Attach</Text>
          <AttachRow
            icon="grid"
            label="Photo Library"
            sub={
              activeRemote
                ? 'Not Available On Remote'
                : visionModels.length === 0
                ? 'Get A Vision Model'
                : 'Send A Photo'
            }
            disabled={!!activeRemote}
            onPress={() => beginAttach('library')}
            styles={styles}
            colors={colors}
          />
          <AttachRow
            icon="camera"
            label="Camera"
            sub={activeRemote ? 'Not Available On Remote' : 'Take A Photo'}
            disabled={!!activeRemote}
            onPress={() => beginAttach('camera')}
            styles={styles}
            colors={colors}
          />
          <AttachRow
            icon="fileText"
            label="File"
            sub="Coming Soon"
            disabled
            styles={styles}
            colors={colors}
          />
```

> Copy is Title Case per the app convention (spec §3). If the `camera` icon name doesn't exist in the `Icon` set, reuse an existing one (e.g. `grid`) — check `src/components/Icon` for valid `IconName`s and pick the closest; note the substitution in the commit body.

- [ ] **Step 4: Add the in-place chooser (many case)**

Render a small selection list when `chooserSource` is set, above the model switcher. Reuse the existing `styles.row`/`styles.rowLabel`:

```typescript
          {chooserSource && (
            <>
              <Text style={styles.sectionLabel}>Use Which Image Model?</Text>
              {visionModels.map(m => (
                <Pressable
                  key={m.id}
                  style={styles.row}
                  onPress={() => {
                    const src = chooserSource;
                    setChooserSource(null);
                    ensureActiveThenPick(m.id, src);
                  }}>
                  <Text style={styles.rowLabel} numberOfLines={1}>
                    {m.name}
                  </Text>
                </Pressable>
              ))}
            </>
          )}
```

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS. (Add a `rowDisabled` style if it doesn't already exist in `makeStyles` — a faded `opacity: 0.45` is fine, matching the prior disabled look.)

- [ ] **Step 6: Commit**

```bash
git add src/components/ChatPlusSheet.tsx
git commit -m "feat(chat): gated photo/camera attach with vision-model chooser"
```

---

### Task 9: Install image-picker + ChatScreen wiring

**Files:**
- Add dep: `react-native-image-picker`
- Modify: `src/screens/ChatScreen.tsx` (pending image state, picker launch, pass to send, render ChatPlusSheet's new prop)
- Modify: iOS `Info.plist`, Android manifest, `pod install`

- [ ] **Step 1: Install the dependency**

Run:

```bash
npm install react-native-image-picker@^8.2.1
cd ios && pod install && cd ..
```

Expected: package added; pods install without error (new-arch supported in 8.x).

- [ ] **Step 2: Add iOS permission strings**

In `ios/EkamCore/Info.plist`, add before the closing `</dict>`:

```xml
	<key>NSCameraUsageDescription</key>
	<string>EkamCore uses the camera so your on-device AI can see photos you take. Images never leave your phone.</string>
	<key>NSPhotoLibraryUsageDescription</key>
	<string>EkamCore reads photos you choose so your on-device AI can describe them. Images never leave your phone.</string>
```

- [ ] **Step 3: Add Android camera permission**

In `android/app/src/main/AndroidManifest.xml`, after the existing `INTERNET` permission line:

```xml
    <uses-permission android:name="android.permission.CAMERA" />
```

> `react-native-image-picker` 8.x uses the system photo picker on modern Android and requests camera permission at runtime; no storage permission is needed for library reads.

- [ ] **Step 4: Wire ChatScreen → picker → send**

In `src/screens/ChatScreen.tsx`, import the picker and `persistChatImage`, add pending-image state, implement the `onPickImage` handler, pass it to `ChatPlusSheet`, and include the persisted path in the send. Add imports:

```typescript
import { launchImageLibrary, launchCamera } from 'react-native-image-picker';
import { persistChatImage } from '../services/download';
```

Add state near the other `useState`s (`~:124-130`):

```typescript
  const [pendingImage, setPendingImage] = useState<string | null>(null);
```

Add the handler (the picker downscales via `maxWidth/maxHeight`; we then copy into Documents):

```typescript
  const onPickImage = async (source: 'library' | 'camera') => {
    const opts = {
      mediaType: 'photo' as const,
      maxWidth: 1024,
      maxHeight: 1024,
      quality: 0.85 as const,
    };
    const res =
      source === 'camera'
        ? await launchCamera(opts)
        : await launchImageLibrary(opts);
    if (res.didCancel || res.errorCode || !res.assets?.[0]?.uri) {
      return;
    }
    const persisted = await persistChatImage(res.assets[0].uri, makeImageId());
    setPendingImage(persisted);
  };
```

Use the file's existing id helper for `makeImageId()`; if none exists, `String(Date.now())` is acceptable here.

Update the send path (`~:193-202`) to include and clear the pending image:

```typescript
  const send = (value: string) => {
    atBottomRef.current = true;
    sendMessage(value, pendingImage ?? undefined);
    setPendingImage(null);
  };
```

> Allow sending an image with empty text (some users just attach a photo). If the current `onSend` early-returns on empty `text`, relax it to also send when `pendingImage` is set.

Pass the new prop to `ChatPlusSheet` (`~:467-471`):

```typescript
        <ChatPlusSheet
          visible={plusOpen}
          onClose={() => setPlusOpen(false)}
          onGoToModels={onGoToModels}
          onPickImage={onPickImage}
        />
```

- [ ] **Step 5: Show the pending image above the composer (small preview + remove)**

Above the text input row, render a thumbnail when `pendingImage` is set so the user sees what they're about to send:

```typescript
        {pendingImage && (
          <View style={styles.pendingImageRow}>
            <Image source={{ uri: `file://${pendingImage}` }} style={styles.pendingThumb} />
            <Pressable onPress={() => setPendingImage(null)} hitSlop={8}>
              <Icon name="x" size={16} color={colors.textDim} />
            </Pressable>
          </View>
        )}
```

Add `pendingImageRow`/`pendingThumb` styles (a 48×48 rounded thumb in a row) to this screen's `makeStyles`. Ensure `Image` is imported from `react-native`.

- [ ] **Step 6: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json ios/ android/app/src/main/AndroidManifest.xml src/screens/ChatScreen.tsx
git commit -m "feat(chat): image picker + permissions + pending-image composer"
```

---

### Task 10: MessageBubble — image thumbnail in history

**Files:**
- Modify: `src/components/MessageBubble.tsx:93-114` (renderBody)

- [ ] **Step 1: Render the attached image**

In `renderBody` (`:93-114`), render the image above the text for user turns. For the user branch:

```typescript
  if (isUser) {
    return (
      <>
        {message.imagePath && (
          <Image
            source={{ uri: `file://${message.imagePath}` }}
            style={styles.messageImage}
            resizeMode="cover"
          />
        )}
        {message.content ? <Text style={styles.userText}>{message.content}</Text> : null}
      </>
    );
  }
```

Import `Image` from `react-native` if not already imported, and add a `messageImage` style (e.g. `width: 200, height: 200, borderRadius: 12, marginBottom: message.content ? 6 : 0`) to `makeStyles`.

- [ ] **Step 2: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/MessageBubble.tsx
git commit -m "feat(chat): render attached image thumbnail in message history"
```

---

### Task 11: ModelsScreen — Vision section + combined size + badge

**Files:**
- Modify: `src/screens/ModelsScreen.tsx:36-99` (sectioning), `src/components/ModelCard.tsx:108-139` (badge + combined size)

- [ ] **Step 1: Show combined size + Vision badge on vision cards**

In `ModelCard.tsx`, where the size meta renders (`~:137`, `formatBytes(model.sizeBytes)`), show base + mmproj when present:

```typescript
        <Meta
          label={formatBytes(model.sizeBytes + (model.mmprojSizeBytes ?? 0))}
          styles={styles}
        />
```

And add a Vision badge in the header row (next to the name, `~:110-112`), mirroring the existing `loadedBadge` style:

```typescript
        {model.vision && (
          <View style={styles.visionBadge}>
            <Icon name="grid" size={11} color={colors.onPrimary} />
            <Text style={styles.loadedBadgeText}>Vision</Text>
          </View>
        )}
```

Add a `visionBadge` style (copy `loadedBadge`, swap the background to an accent/neutral so it reads differently from ACTIVE). Use a valid `IconName` (reuse `grid` if no `eye`).

- [ ] **Step 2: Group the Models list into Text and Vision sections**

In `ModelsScreen.tsx` (`:36-99`), after the existing tier sort, split featured models so vision models render under their own labeled section. Minimal approach — append a Vision section after the text tiers:

```typescript
  const featured = models.filter(m => !m.custom);
  const textModels = featured.filter(m => !m.vision);
  const visionModelsList = featured.filter(m => m.vision);
```

Render the existing tier-grouped nodes from `textModels` (replace `sortedFeatured` source with `textModels`), then after them:

```typescript
        {visionModelsList.length > 0 && (
          <>
            <Text style={styles.sectionHeader}>Vision</Text>
            {visionModelsList.map(m => (
              <ModelCard key={m.id} model={m} onPress={() => setDetailModel(m)} />
            ))}
          </>
        )}
```

Use the screen's existing section-header style (the same one used for tier headings, `tierHeading`); if it's inline, reuse that style object.

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/screens/ModelsScreen.tsx src/components/ModelCard.tsx
git commit -m "feat(models): Vision section, combined size, and Vision badge"
```

---

### Task 12: Device verification (vision is device-only)

Multimodal inference cannot be unit-tested; it must run on a real device. Validate the four risk areas from the spec §7.

- [ ] **Step 1: Build & launch (iPhone preferred; Simulator OK for UI/gate flow)**

Run: `npm run ios` (or the Release device build used previously). Expected: app launches, no red box.

- [ ] **Step 2: Gate — NONE downloaded**

With no vision model downloaded, open "+" → tap **Photo Library**. Expected: sheet closes and navigates to Models (no picker opens).

- [ ] **Step 3: Download a vision model (two files)**

In Models → Vision, download **SmolVLM 500M**. Expected: progress runs through base then mmproj; card shows combined ~546 MB and a **Vision** badge; becomes ready only after both files land.

- [ ] **Step 4: Gate — ONE downloaded + inference**

Open "+" → **Photo Library** → pick a photo. Expected: model auto-selects (shows "Loading…" if swapping), picker opens, pending thumbnail appears above composer, send → assistant streams a description of the image. Verify the user bubble shows the thumbnail.

- [ ] **Step 5: Camera path + permission**

"+" → **Camera** → first run prompts for camera permission → capture → send. Expected: permission prompt uses the Info.plist copy; capture flows to inference.

- [ ] **Step 6: Gate — MANY downloaded**

Download **Qwen2-VL-2B** too. "+" → **Photo Library** → expect the **"Use Which Image Model?"** chooser → pick one → it activates → picker opens.

- [ ] **Step 7: History persistence**

Send an image message, leave the chat, reopen it. Expected: the thumbnail + text are still there (imagePath persisted). Kill and relaunch the app → still present.

- [ ] **Step 8: Record results**

Append a short results note (pass/fail per step, device, model) to `docs/DEFERRED_WORK.md` per the deferred-work-log convention. Commit:

```bash
git add docs/DEFERRED_WORK.md
git commit -m "docs: record on-device vision verification results"
```

---

## Self-review notes

- **Spec coverage:** §4 categorization → Tasks 1–3, 11. §5 attach/inference/display/persist → Tasks 5, 7, 8, 9, 10, 6. §6 catalog/files/tests → Tasks 2, 3, 4, 6, 9 (deps/permissions). §7 risks → validated in Task 12 (multimodal call shape = Task 5; small GGUF+mmproj pairs = verified URLs in Task 2; image-picker new-arch = Task 9 Step 1; swap latency UX = "Loading…" in Tasks 7–8). §8 open items → seed URLs/sizes (confirmed), llama wiring (Task 5), image storage/downscale/thumbnail (Tasks 6, 9, 10), chooser (Task 8), permission copy (Task 9).
- **Deviation:** `vision: boolean` reused instead of new `kind` (documented at top) — keeps `ChatPlusSheet:44`'s existing usage valid.
- **Type consistency:** `mmprojFilePath`, `requiredFilesFor`, `persistChatImage`, `startMmprojDownload`, `downloadedVisionModels`, `isVisionModel` used with identical signatures across tasks. `media_paths` (bare path) and `imagePath` (bare path) are consistently scheme-free; `<Image>` adds `file://` at render only.
- **Integration risk concentrated in Task 7** (AppContext) — it touches existing flows by reference rather than full-rewrite because the file is large; the compiler (`tsc --noEmit`) is the guardrail and each touched action keeps its existing setters.

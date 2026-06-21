# EkamCore 🧠📱

**EkamCore** is a proprietary, privacy-first AI assistant that runs Large
Language Models **entirely on your device**. Download a model once, then chat,
draft, summarize, and work with AI **fully offline** — your conversations,
documents, and data never leave the phone.

No accounts. No servers. No cloud. Your intelligence stays yours.

---

## Why EkamCore

- **Own your intelligence.** Inference happens locally — nothing is uploaded,
  logged, or sent to a third party.
- **Works anywhere.** Once a model is downloaded, the app needs no internet to
  think, chat, or run tools.
- **Fast on real hardware.** iOS uses Metal GPU acceleration; Android runs on an
  optimized CPU path for broad device support.

---

## Features

- **On-device chat** — a streaming conversational assistant with live token
  output and tokens/second metrics. Stop generation mid-stream at any time.
- **Conversation history** — multiple saved conversations, persisted locally on
  the device.
- **AI Tools** — guided one-tap workflows built on the local model: email
  generation, email replies, meeting summarization, and more.
- **Vision / image input** — attach images to supported multimodal models.
- **Model manager** — browse a curated catalog of phone-friendly models
  (text and image), download with progress tracking, load, unload, and delete.
- **Add any GGUF model** — paste a Hugging Face `resolve` URL, or search
  Hugging Face directly from inside the app.
- **Personalization & settings** — themes, default model, and assistant
  preferences, all stored on-device.
- **100% local persistence** — models, conversations, and settings live only on
  the device. No backend is involved.

---

## App layout

EkamCore is organized into four tabs:

| Tab          | What it does                                                        |
| ------------ | ------------------------------------------------------------------- |
| **Chat**     | Talk to the loaded model; manage conversation history.              |
| **Tools**    | Run guided AI workflows (email, summaries, etc.).                   |
| **Models**   | Download, load, and manage text and image models.                   |
| **Settings** | Personalization, themes, default model, and app preferences.        |

---

## Tech stack

| Concern              | Library / technology                          |
| -------------------- | --------------------------------------------- |
| Framework            | React Native 0.85 (bare CLI), React 19, TS    |
| On-device inference  | `llama.rn` (llama.cpp bindings)               |
| Model downloads      | `react-native-blob-util`                      |
| Persistence          | `@react-native-async-storage/async-storage`   |
| Image input          | `react-native-image-picker`                   |
| Markdown rendering    | `react-native-markdown-display`               |
| Vector / SVG UI       | `react-native-svg`                            |
| Device info           | `react-native-device-info`                    |
| Safe areas            | `react-native-safe-area-context`              |

> iOS inference is GPU-accelerated via Metal (`n_gpu_layers: 99`); Android runs
> on CPU for broad device compatibility. These are tunable in
> `src/services/llama.ts`.

---

## Project structure

```
App.tsx              custom bottom-tab shell (Chat · Tools · Models · Settings)
src/
  components/        Button, ProgressBar, ModelCard, MessageBubble,
                     HistoryPanel, Onboarding, SplashScreen, sheets, …
  context/           AppContext.tsx (models + chat), ThemeContext.tsx
  data/              models.ts (curated GGUF catalog), tools.ts (AI tools)
  screens/           ChatScreen, ToolsListScreen, ToolRunnerScreen,
                     ModelsScreen, HuggingFaceSearch, SettingsScreen
  services/          llama.ts (inference), download.ts, storage.ts,
                     conversations.ts, memory.ts, huggingface.ts,
                     catalog.ts, capabilities.ts, device.ts, remote.ts
  utils/             format.ts, modelFit.ts
  theme.ts  typography.ts  applyFonts.ts  types.ts
ios/  android/       native projects
```

---

## Prerequisites

- **Node.js** `>= 22.11.0` and **npm**
- **Watchman** (recommended on macOS): `brew install watchman`
- **iOS:** Xcode + CocoaPods (`sudo gem install cocoapods`)
- **Android:** Android Studio, an SDK + emulator (or a USB device), JDK 17

> A physical device is recommended — LLM inference is CPU/GPU heavy and runs far
> faster on real hardware than on a simulator/emulator.

---

## Setup

From the project folder (`EkamCore/`):

```bash
# 1. Install JS dependencies
npm install

# 2. iOS only: install native pods
cd ios && pod install && cd ..
```

---

## Run

Start the Metro bundler in one terminal:

```bash
npm start
```

Then, in a second terminal, launch a platform:

**Android** (emulator running or device connected):

```bash
npm run android
```

**iOS** (macOS only):

```bash
npm run ios
# or target a specific device:
npx react-native run-ios --device "Your iPhone"
```

---

## Using the app

1. Open the **Models** tab.
2. Tap **Download** on a model (start with the smallest if you're unsure).
   - Or use **Add model from GGUF URL** / **Search Hugging Face** to pull any
     compatible `.gguf` model.
3. Once downloaded, tap **Load** to load it into memory.
4. Switch to **Chat** and start talking — **no internet needed**.
5. Explore the **Tools** tab for guided workflows like email drafting and
   meeting summaries.
6. Tap ■ to stop generation; manage saved chats from the history panel.

---

## Notes & troubleshooting

- **First launch is heavy.** The native build (especially `llama.rn`) takes a
  while to compile the first time.
- **iOS memory:** very large models may need the *Increased Memory Limit*
  capability in Xcode (`Signing & Capabilities`). Bundled small models run
  within default limits on modern devices.
- **Android memory:** `android:largeHeap="true"` is already set in the manifest.
- **Downloads need internet (once).** Inference and chat are fully offline.
- **Model URLs:** the catalog points at public Hugging Face GGUF files. If a URL
  ever moves, use **Add model from GGUF URL** with a current link.

---

## Commands

- `npm start` — Metro bundler
- `npm run ios` / `npm run android` — build & launch
- `npm test` — Jest
- `npm run lint` — ESLint
- `cd ios && pod install` — install iOS pods

---

## License

MIT. Third-party open-source components (including `llama.rn` / llama.cpp and
the other libraries listed under *Tech stack*) remain subject to their own
licenses, and downloaded model files are governed by their respective model
licenses.

# EkamCore 🧠📱

A bare **React Native (no Expo)** app that runs Large Language Models **fully
on-device**. Download a small GGUF model once, then chat with it completely
offline — your conversations never leave the phone.

Inspired by [PocketPal AI](https://github.com/a-ghorbani/pocketpal-ai) and built
on the same core engine, [`llama.rn`](https://github.com/mybigday/llama.rn)
(llama.cpp bindings for React Native).

## Features

- **100% offline inference** — powered by `llama.rn` / llama.cpp.
- **Model manager** — download, track progress, load, unload, and delete models.
- **Curated catalog** of tiny phone-friendly models (Qwen2.5, SmolLM2, Llama 3.2).
- **Add any GGUF URL** (e.g. a Hugging Face `resolve` link).
- **Streaming chat UI** with live token output and tokens/second metrics.
- **Stop generation** mid-stream.
- On-device storage of downloaded models and settings (no servers involved).

## Tech stack

| Concern              | Library                                  |
| -------------------- | ---------------------------------------- |
| Inference            | `llama.rn`                               |
| Model downloads      | `react-native-blob-util`                 |
| Persistence          | `@react-native-async-storage/async-storage` |
| Safe areas           | `react-native-safe-area-context`         |
| Framework            | React Native 0.85 (bare CLI)             |

## Project structure

```
src/
  components/    Button, ProgressBar, ModelCard, MessageBubble
  context/       AppContext.tsx  (global state: models + chat)
  data/          models.ts       (curated GGUF catalog)
  screens/       ModelsScreen, ChatScreen
  services/      llama.ts (inference), download.ts, storage.ts
  utils/         format.ts
App.tsx          custom bottom-tab shell
```

---

## Prerequisites

- **Node.js** 20+ and **npm**
- **Watchman** (recommended on macOS): `brew install watchman`
- **iOS:** Xcode + CocoaPods + Ruby bundler (`sudo gem install cocoapods bundler`)
- **Android:** Android Studio, an SDK + emulator (or a USB device), JDK 17

> A physical device is recommended — LLM inference is CPU/GPU heavy and faster
> on real hardware than on a simulator/emulator.

---

## Setup

From the project folder (`EkamCore/`):

```bash
# 1. Install JS dependencies (already done if you cloned this folder)
npm install

# 2. iOS only: install native pods (uses your system CocoaPods)
cd ios && pod install && cd ..
```

> If you prefer the bundled Ruby toolchain instead, run `bundle install` once
> (to install the gems in `Gemfile`) and then `bundle exec pod install`. The
> plain `pod install` above is simpler and avoids the bundler step.

---

## Run

Start the Metro bundler in one terminal:

```bash
npm start
```

Then in a second terminal, launch a platform:

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
2. Tap **Download** on a model (start with *Qwen2.5 0.5B* — it's the smallest).
   - Or tap **“+ Add model from GGUF URL”** to paste any `.gguf` link.
3. Once downloaded, tap **Load** to load it into memory.
4. Switch to the **Chat** tab and start chatting — **no internet needed**.
5. Tap the ■ button to stop generation; **Clear** to reset the conversation.

---

## Notes & troubleshooting

- **First launch is heavy.** The native build (especially `llama.rn`) takes a
  while to compile the first time.
- **iOS memory:** very large models may need the *Increased Memory Limit*
  capability in Xcode (`Signing & Capabilities`). The bundled small models run
  within default limits on modern devices.
- **Android memory:** `android:largeHeap="true"` is already set in the manifest.
- **Downloads need internet (once).** Inference and chat are fully offline.
- **Model URLs:** the catalog points at public Hugging Face GGUF files. If a URL
  ever moves, use **Add model from GGUF URL** with a current link.
- **iOS GPU (Metal)** is enabled (`n_gpu_layers: 99`); Android runs on CPU for
  broad device compatibility. Tune these in `src/services/llama.ts`.

## License

MIT — for learning/demo purposes. Model files are subject to their own licenses.

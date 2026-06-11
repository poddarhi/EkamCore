# EkamCore — on-device LLM chat (React Native)

This repo is a **bare React Native (no Expo) app** that runs LLMs **fully on-device**
via `llama.rn` (llama.cpp bindings). Download a GGUF model once, then chat offline.
Both the user-facing display name and the internal project name are **EkamCore**
(`app.json`). See `README.md` for setup, run, and troubleshooting.

> History note: this repo previously held a different, larger "EkamCore" product
> (backend/frontend/infra/ml). That product's docs were removed from the working
> tree on 2026-06-10 — they remain in **git history** (before that commit) if ever
> needed. Ignore any backend/Qdrant/sprint/roadmap/pol-005 material you may see in
> history — it does not apply to this app.

## Stack
- **Framework:** React Native 0.85 (bare CLI), React 19, TypeScript.
- **Inference:** `llama.rn` (llama.cpp). iOS uses Metal (`n_gpu_layers: 99`), Android CPU.
- **Downloads:** `react-native-blob-util`. **Persistence:** `@react-native-async-storage/async-storage`.
- **Node:** `>= 22.11.0` (see `package.json` engines).

## Structure
```
App.tsx          custom bottom-tab shell
src/
  components/    Button, ProgressBar, ModelCard, MessageBubble
  context/       AppContext.tsx (global state: models + chat)
  data/          models.ts (curated GGUF catalog)
  screens/       ModelsScreen, ChatScreen
  services/      llama.ts (inference), download.ts, storage.ts
  theme.ts typography.ts applyFonts.ts types.ts utils/
ios/ android/    native projects
```

## Commands
- `npm start` — Metro bundler · `npm run ios` / `npm run android` — build & launch
- `npm test` — Jest · `npm run lint` — ESLint
- iOS pods: `cd ios && pod install`

## Conventions
- TypeScript strict; match existing component/style idiom in `src/`.
- AsyncStorage keys are namespaced `ekamcore.*`.
- Conventional commits.

## graphify (optional, local)
Knowledge graph lives at `graphify-out/` (gitignored). If present, read
`graphify-out/GRAPH_REPORT.md` before broad architecture questions; run
`graphify update .` after code changes to refresh it (AST-only, no API cost).

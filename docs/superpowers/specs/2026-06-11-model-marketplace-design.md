# Model Marketplace (Phase A) — Design

_Date: 2026-06-11 · Status: approved, building_

## Problem

The model catalog is a hardcoded list of 4 (`src/data/models.ts`). Users can't see the
breadth of available on-device models, there's no guidance on which model suits which task,
no per-model detail view, and updating the list requires shipping a new app build.

## Goals (Phase A)

- **Remote, editable Featured catalog** — no app rebuild to add/feature a model.
- **Richer metadata** — publisher, "good for" use-cases, description, specs.
- **Fit-sorted list** — Runs great → Runs well → May run slowly → Too large, with tier headers.
- **Tappable model detail screen** — plain-language, device-tailored, distinct from LM Studio.
- Offline-safe: cache the remote catalog; fall back to cache, then to a bundled seed.

## Non-goals (Phase B / later)

- Live "Browse Hugging Face" search UI (query HF, pick a quant, one-tap add). The existing
  "Add from GGUF URL" remains for the long tail meanwhile.
- Automated catalog refresh job (manual remote JSON now).
- Image/vision support (the `vision` flag is recorded but not wired).

## Catalog source

A JSON file committed at `catalog/featured.json` in the GitHub repo, served via the free
jsDelivr CDN:

`https://cdn.jsdelivr.net/gh/poddarhi/EkamCore@app-main/catalog/featured.json`

Editing that file (and pushing) updates every user's Featured list with no rebuild. (Requires
the repo to be public, which it is. jsDelivr caches branch URLs ~12h; acceptable for now.)

## Data model (`src/types.ts`)

Extend `ModelInfo` with optional, back-compatible fields:

```ts
publisher?: string;       // "Google", "Meta", "Qwen", "Microsoft", ...
tagline?: string;         // one-line hook
goodFor?: string[];       // ["Chat", "Coding", "Reasoning", "Summarizing"]
longDescription?: string; // paragraph for the detail screen
contextLength?: number;   // tokens
license?: string;         // "Apache-2.0", "Llama-3.2", ...
releasedAt?: string;      // ISO date → drives a "NEW" badge
vision?: boolean;         // future image support (not wired in Phase A)
```

## Catalog service (`src/services/catalog.ts`)

- `fetchFeaturedCatalog(): Promise<ModelInfo[] | null>` — GET the jsDelivr URL, validate, cache
  to `ekamcore.featuredCatalog.v1`, return models (or null on any failure).
- `loadCachedCatalog(): Promise<ModelInfo[] | null>` — read the cache.
- `validateCatalog(data): ModelInfo[] | null` — accept `{version, models[]}`, keep only entries
  with valid `id/name/url/sizeBytes/params/quant`; drop the rest. Pure + unit-tested.

The bundled `CATALOG` (current 4) stays as the offline seed.

## State (`AppContext`)

- New `featured: ModelInfo[]` state, seeded with bundled `CATALOG`.
- On startup, progressive enhancement: `loadCachedCatalog()` → if present, replace; then
  `fetchFeaturedCatalog()` → if present, replace. Never blocks the UI; offline keeps the seed.
- `models = [...featured, ...customModels]` (unchanged downstream).

## UI

**Models screen (`ModelsScreen`)**
- Sort featured models by fit tier order (`great, good, slow, too-large, unknown`); within a tier,
  larger/newer first. Render a small **tier section header** ("Runs great on your device", etc.)
  before each group. Custom models stay in their own trailing group.
- Tapping a card **body** opens the detail sheet; the Download/Load/trash buttons remain separate.

**Model detail sheet (`src/components/ModelDetail.tsx`)** — a slide-up modal:
- Header: name, publisher, "NEW" badge if `releasedAt` is recent.
- **Personalized fit hero**: "On your {device} ({RAM} GB), this should run {great/well/slowly}"
  (or "may be too large"), colored by tier — the key differentiator vs LM Studio.
- "Good for" chips, `longDescription`, a specs grid (params · quant · size · context · license).
- Download/Load actions (reuse existing context actions) + "View on Hugging Face" link.

**ModelCard** — gains an `onPress` that opens the detail sheet; action buttons unchanged.

## Differentiation from LM Studio

Mobile-first, plain-language, **fit tailored to the actual phone's RAM**, curated "what's it good
for" guidance, privacy-framed — instead of desktop VRAM/quant tables and developer jargon.

## Testing

- Unit-test `validateCatalog` (valid passes, malformed entries dropped, bad root → null) and the
  fit-sort comparator ordering. Mock `fetch` for the fetch path.
- Existing `modelFit` tests stay green.
- Manual: launch with network (remote list loads, fit-sorted, detail opens) and airplane mode
  (falls back to cache/seed, no crash) on both platforms.

## Rollout note

Phase A is pure JS/TS (uses built-in `fetch` + existing AsyncStorage) — no native deps, so it
ships via Metro reload, no rebuild. Requires pushing `catalog/featured.json` for jsDelivr.

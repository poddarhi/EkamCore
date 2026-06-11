# Browse Hugging Face (Phase B) — Design

_Date: 2026-06-11 · Status: approved (user: "move to Phase B"), building_

## Problem

The Featured catalog is curated and finite. Users should be able to find and add **any** GGUF
model on Hugging Face — the "entire marketplace" — directly from the app.

## Goal

Search Hugging Face for GGUF models, pick a quantization, and add it to the app with full
metadata (so it gets a fit badge + detail sheet and can be downloaded/loaded like any model).

## Hugging Face API (public, unauthenticated)

- **Search:** `GET https://huggingface.co/api/models?search=<q>&filter=gguf&limit=25&sort=downloads&direction=-1`
  → `[{ id, author, downloads, likes }]`. Empty query (sorted by downloads) = "trending".
- **Files:** `GET https://huggingface.co/api/models/<id>/tree/main`
  → `[{ path, size, lfs:{ size } }]`. Keep `*.gguf`; size is `lfs.size ?? size`.
- **Download URL:** `https://huggingface.co/<id>/resolve/main/<path>`.

## Service (`src/services/huggingface.ts`)

- `searchGgufModels(query): Promise<HfRepo[]>` — returns `{ id, author, downloads, likes }`; `[]` on failure.
- `listQuants(repoId): Promise<HfQuant[]>` — `.gguf` files only, **excluding sharded multi-part
  files** (`-00001-of-00000N`); returns `{ filename, quant, sizeBytes, url }` sorted by size asc.
- `parseQuant(filename): string` — extract the quant label (`Q4_K_M`, `IQ4_XS`, `F16`, …). Pure.
- `pickRecommended(quants): HfQuant | null` — prefer `Q4_K_M`, else `Q4_K_S`, else `Q4_0`, else the
  median-by-size entry. Pure.

`HfRepo` and `HfQuant` are local interfaces. Network functions never throw (return `[]`/`null`).

## State (`AppContext`)

- New action `addModel(model: ModelInfo): Promise<void>` — append a fully-formed model (with
  `custom: true`) to `customModels` and persist (generalizes the existing `addCustomModel`, which
  stays for the raw-URL flow).

## UI

**Models screen** — a primary **"Browse Hugging Face"** button (the existing "Add from GGUF URL"
stays as a secondary/advanced option). Opens the search modal.

**`src/screens/HuggingFaceSearch.tsx`** (full-screen modal):
- Search `TextInput` (debounced ~400 ms). Empty = trending GGUF repos.
- Results list: repo name, author, downloads/likes. States: loading, empty, offline/error.
- Tap a repo → **quant sheet**:
  - Fetch `listQuants`. Show **Recommended** (from `pickRecommended`) with size + device fit badge.
  - "More quantizations" expands the full list, each with size + fit badge.
  - Tap a quant → build a `ModelInfo` `{ id: "hf-<repo>-<quant>", name, publisher: author,
    params: "—", quant, sizeBytes, url, custom: true, longDescription }` → `addModel` → close →
    it appears under "Your added models", downloadable/loadable, with a fit badge + detail sheet.

## Testing

- Unit-test `parseQuant` (Q-series, IQ-series, F16, no-match) and `pickRecommended` (prefers
  Q4_K_M; median fallback). Mock `fetch` is not required for the pure helpers.
- Manual: search "gemma", open a repo, see recommended quant + fit, add it, confirm it lands in
  "Your added models" and downloads; offline shows a graceful message.

## Non-goals

- Auth/private repos, multi-part (sharded) models, vision wiring, automated curation.

## Rollout

Pure JS/TS (built-in `fetch`) — ships via Metro reload, no rebuild.

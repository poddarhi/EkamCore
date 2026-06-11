# EkamCore — Backlog

Captured items to address going forward. Not yet scheduled. Newest first.

---

## Downloads — robustness (reported from device testing, 2026-06-11)

Observed on a real iPhone: starting a model download, backgrounding the app,
then returning left the download **corrupted**; stopping a download **restarts
from the beginning** rather than resuming.

Root cause (see `src/services/download.ts`):
- Foreground `react-native-blob-util` fetch; iOS suspends it when backgrounded,
  which can truncate the transfer.
- Finalize only checks the temp file is `> 1 MB` — it does **not** verify the
  full expected size, so a truncated (but >1 MB) partial can be saved as a
  "complete" model and later fail to load.
- No HTTP `Range` request → every (re)start downloads from byte 0.

**Space concern (answered):** the temp file is a single `<id>.gguf.part` with
`overwrite: true`, finalized to `<id>.gguf` only on full completion. Restarting
overwrites the same temp file, so it does **not** accumulate space per model.
A stale `.part` can linger only if the OS kills the app mid-download (bounded:
≤ 1 stale partial per model; overwritten on next attempt).

To do:
1. **Verify full size before finalizing** — compare the `.part` size to
   `model.sizeBytes` (catalog value) within a small tolerance; reject + clean up
   truncated downloads instead of saving them. (Directly fixes the "corrupted"
   symptom.)
2. **Resumable downloads** — send `Range: bytes=<existing-part-size>-` and append,
   so stopping/backgrounding resumes instead of restarting.
3. **Background-safe transfers** — use iOS/Android background download sessions so
   minimizing the app doesn't interrupt/corrupt the download.
4. **Orphan cleanup** — sweep stale `*.part` files in the models dir on launch.

## Feature — user-settable default model

Let users pick a **default model** that auto-loads on app launch. Today
`loadLastModelId`/`saveLastModelId` exist but the app deliberately does **not**
auto-load ("heavy") — it only remembers the last selection visually
(`AppContext` startup effect). Add an explicit "Set as default" affordance
(e.g. in the model detail sheet or Settings) plus an opt-in "load my default on
launch" behavior.

# Phase 1 — Persistent Chat History (Design)

_Date: 2026-06-11 · Status: approved direction, pending spec review_

## Problem

Chat history is purely in-memory. In `AppContext.tsx` the `messages` array lives only in React
state, is never written to storage, and is wiped (`setMessages([])`) every time a model is loaded.
On both iOS and Android, history therefore vanishes when the user leaves chat or restarts the app,
and there is no way to revisit a past conversation. Persistent, browsable history is the foundation
for the Phase 2 (behavioral memory) and Phase 3 (personal-compute) work described in
`docs/ROADMAP.md`.

## Goals

- Conversations persist across app restarts on both platforms.
- Users can keep **multiple conversations** (a thread list), reopen any of them, and delete them.
- Switching models no longer wipes the active conversation.
- Purely additive to the existing chat UI; no regression to the landing hero / message list.

## Non-goals (deferred)

- Behavioral/factual memory and personalization (Phase 2).
- Personal-compute bridge and in-chat remote model switching (Phase 3).
- On-device weight fine-tuning (not feasible via `llama.rn`).
- Search across conversations, folders/tags, export, cloud sync.

## Data model (`src/types.ts`)

```ts
export interface ConversationMeta {
  id: string;
  title: string;        // auto-derived from first user message, truncated ~40 chars
  createdAt: number;
  updatedAt: number;
  modelId: string | null;   // model used most recently in this thread (for subtitle/display)
  messageCount: number;
}
```

`ChatMessage` is unchanged. A conversation = `ConversationMeta` + its `ChatMessage[]`. The transient
`streaming` flag is never persisted.

## Storage layout (AsyncStorage, `ekamcore.*` namespace)

A lightweight **index** plus per-conversation **blobs**, so we never rewrite all history on every
turn and the list loads without loading every message:

- `ekamcore.conversations.index.v1` → `ConversationMeta[]`, sorted by `updatedAt` desc.
- `ekamcore.conversation.<id>.v1` → `ChatMessage[]` for that thread (lazy-loaded on open).

**Persistence timing:** at the *end of each completed turn* (after the assistant message finishes
streaming, or on stop/error with whatever exists) — never mid-token. Each save writes the blob and
updates that conversation's index entry (`updatedAt`, `messageCount`, `modelId`, and `title` if still
untitled).

## New service: `src/services/conversations.ts`

Owns all conversation persistence; keeps `storage.ts` for simple key/values.

- `listConversations(): Promise<ConversationMeta[]>`
- `loadMessages(id: string): Promise<ChatMessage[]>`
- `saveConversation(meta: ConversationMeta, messages: ChatMessage[]): Promise<void>`
- `deleteConversation(id: string): Promise<void>`
- `renameConversation(id: string, title: string): Promise<void>`

All wrapped in try/catch returning safe defaults (mirrors existing `storage.ts` idiom).

## State (`src/context/AppContext.tsx`)

- New state: `conversations: ConversationMeta[]` and `activeConversationId: string | null`.
- The existing `messages` array represents the **active conversation's** messages.
- **Startup:** load the index for the history list; chat opens fresh on the landing hero (no thread
  auto-opened). Past threads are resumed from the history panel.
- New/changed actions:
  - `newConversation()` — clears active thread, `messages = []`, hero shows. Replaces today's
    `clearChat` semantics (the "New"/"+" buttons call this).
  - `openConversation(id)` — lazy-loads the thread's blob into `messages`, sets `activeConversationId`.
  - `deleteConversation(id)` — removes blob + index entry; if the active thread was deleted, reset to
    a new conversation.
  - `renameConversation(id, title)` — updates the index entry.
- `sendMessage` — if there is no active thread, **lazily create one** on the first message; append
  messages as today; on turn completion (success/stop/error) persist the blob and update the index
  (title from first user message, `updatedAt`, `messageCount`, `modelId = loadedModelId`).
- **Fix:** remove `setMessages([])` from `load()` so switching models keeps the active conversation.
  Record the model on the conversation at send time.

## UI

- **History button** (list/clock icon) added top-left of the **Chat** header in `App.tsx`, visible
  only on the chat tab. Toggles a `HistoryPanel` overlay.
- **`src/components/HistoryPanel.tsx`** (new): a slide-in overlay animated in the style of the
  existing tab/hero `Animated` code. Reads `conversations` from `useApp()`.
  - Top: **"+ New chat"** → `newConversation()` + close.
  - List: conversations newest-first; each row shows title + relative time. Tap →
    `openConversation(id)` + close. Swipe or long-press → delete with confirm. Optional rename.
- The landing hero, message list, and input pill are unchanged. The existing in-chat "New" and "+"
  buttons are repointed from `clearChat` to `newConversation()`.

## Error handling

- All storage reads/writes are guarded; a corrupt or missing blob yields an empty conversation and a
  console warning, never a crash (mirrors `loadCustomModels`).
- A failed save does not interrupt the chat; it logs and retries on the next turn.
- Deleting the active conversation resets cleanly to a new thread.

## Testing

- Unit tests for `conversations.ts` CRUD against a mocked AsyncStorage (round-trip, missing/corrupt
  blob, index ordering by `updatedAt`).
- Reducer/action tests for `newConversation` / `openConversation` / `deleteConversation` and the
  lazy-create-on-first-message path in `sendMessage`.
- Manual walk on both iOS and Android: send messages → restart app → history persists; reopen a
  thread; delete a thread; switch models mid-conversation without losing messages.

## Migration

No existing persisted chat data exists, so there is nothing to migrate. New keys are versioned
(`.v1`) for future migrations.

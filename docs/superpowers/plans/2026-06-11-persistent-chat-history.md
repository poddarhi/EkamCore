# Persistent Chat History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chat conversations persist across app restarts on both platforms, with a browsable multi-conversation thread list.

**Architecture:** A new `conversations.ts` service stores a lightweight metadata index plus per-conversation message blobs in AsyncStorage. `AppContext` gains `conversations` + `activeConversationId` state and new actions (`newConversation`, `openConversation`, `deleteConversation`, `renameConversation`); `sendMessage` persists at the end of each turn. A slide-in `HistoryPanel`, opened from a new Chat-header history button, lists threads.

**Tech Stack:** React Native 0.85, React 19, TypeScript (strict), `@react-native-async-storage/async-storage`, Jest.

**Note on testing scope:** The project's only existing automated test renders `<App />`. There is no hook/component-testing harness installed, and adding one is out of scope (YAGNI). So **automated unit tests cover the `conversations.ts` service** (pure + deterministic against the existing AsyncStorage mock). Context/UI behavior is verified by `tsc`, ESLint, the existing render test (must not crash), and a scripted manual walk in Task 5.

---

### Task 1: Conversation type + persistence service (TDD)

**Files:**
- Modify: `src/types.ts` (append `ConversationMeta`)
- Create: `src/services/conversations.ts`
- Test: `__tests__/conversations.test.ts`

- [ ] **Step 1: Add the `ConversationMeta` type**

Append to `src/types.ts` (after the `ChatMessage` interface):

```ts
export interface ConversationMeta {
  id: string;
  /** Auto-derived from the first user message; user-editable. */
  title: string;
  createdAt: number;
  updatedAt: number;
  /** Model most recently used in this thread (for display). */
  modelId: string | null;
  messageCount: number;
}
```

- [ ] **Step 2: Write the failing tests**

Create `__tests__/conversations.test.ts`:

```ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  deleteConversation,
  deriveTitle,
  listConversations,
  loadMessages,
  renameConversation,
  saveConversation,
} from '../src/services/conversations';
import { ChatMessage, ConversationMeta } from '../src/types';

const msg = (role: ChatMessage['role'], content: string): ChatMessage => ({
  id: `${role}-${content}`,
  role,
  content,
});

const meta = (over: Partial<ConversationMeta> = {}): ConversationMeta => ({
  id: 'c1',
  title: 'Hello',
  createdAt: 1000,
  updatedAt: 1000,
  modelId: 'm1',
  messageCount: 2,
  ...over,
});

beforeEach(async () => {
  await AsyncStorage.clear();
});

describe('deriveTitle', () => {
  it('uses the first user message', () => {
    expect(
      deriveTitle([msg('assistant', 'hi'), msg('user', 'Hello there')]),
    ).toBe('Hello there');
  });

  it('truncates long titles to <= 41 chars (40 + ellipsis)', () => {
    expect(deriveTitle([msg('user', 'a'.repeat(60))]).length).toBeLessThanOrEqual(41);
  });

  it('falls back to "New chat" when there is no user message', () => {
    expect(deriveTitle([msg('assistant', 'hi')])).toBe('New chat');
  });
});

describe('conversations CRUD', () => {
  it('round-trips messages and lists metadata', async () => {
    const messages = [msg('user', 'Hello'), msg('assistant', 'Hi!')];
    await saveConversation(meta(), messages);
    expect(await loadMessages('c1')).toEqual([
      { id: 'user-Hello', role: 'user', content: 'Hello' },
      { id: 'assistant-Hi!', role: 'assistant', content: 'Hi!' },
    ]);
    const list = await listConversations();
    expect(list).toHaveLength(1);
    expect(list[0].id).toBe('c1');
  });

  it('orders conversations by updatedAt descending', async () => {
    await saveConversation(meta({ id: 'old', updatedAt: 1000 }), [msg('user', 'a')]);
    await saveConversation(meta({ id: 'new', updatedAt: 2000 }), [msg('user', 'b')]);
    const list = await listConversations();
    expect(list.map(c => c.id)).toEqual(['new', 'old']);
  });

  it('deletes a conversation and its messages', async () => {
    await saveConversation(meta(), [msg('user', 'Hello')]);
    await deleteConversation('c1');
    expect(await listConversations()).toHaveLength(0);
    expect(await loadMessages('c1')).toEqual([]);
  });

  it('renames a conversation', async () => {
    await saveConversation(meta(), [msg('user', 'Hello')]);
    await renameConversation('c1', 'Renamed');
    const list = await listConversations();
    expect(list[0].title).toBe('Renamed');
  });

  it('returns [] for a missing conversation blob', async () => {
    expect(await loadMessages('does-not-exist')).toEqual([]);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `npm test -- conversations`
Expected: FAIL — cannot find module `../src/services/conversations`.

- [ ] **Step 4: Implement the service**

Create `src/services/conversations.ts`:

```ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import { ChatMessage, ConversationMeta } from '../types';

const INDEX_KEY = 'ekamcore.conversations.index.v1';
const blobKey = (id: string) => `ekamcore.conversation.${id}.v1`;

/** Title from the first user message, collapsed and truncated to ~40 chars. */
export function deriveTitle(messages: ChatMessage[]): string {
  const firstUser = messages.find(m => m.role === 'user');
  const raw = (firstUser?.content ?? '').trim().replace(/\s+/g, ' ');
  if (!raw) {
    return 'New chat';
  }
  return raw.length > 40 ? `${raw.slice(0, 40).trimEnd()}…` : raw;
}

export async function listConversations(): Promise<ConversationMeta[]> {
  try {
    const raw = await AsyncStorage.getItem(INDEX_KEY);
    const list = raw ? (JSON.parse(raw) as ConversationMeta[]) : [];
    return list.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

async function writeIndex(list: ConversationMeta[]): Promise<void> {
  await AsyncStorage.setItem(INDEX_KEY, JSON.stringify(list));
}

export async function loadMessages(id: string): Promise<ChatMessage[]> {
  try {
    const raw = await AsyncStorage.getItem(blobKey(id));
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

export async function saveConversation(
  meta: ConversationMeta,
  messages: ChatMessage[],
): Promise<void> {
  // Persist only durable fields; the `streaming` flag is transient.
  const clean = messages.map(m => ({
    id: m.id,
    role: m.role,
    content: m.content,
    ...(m.tokensPerSecond != null ? { tokensPerSecond: m.tokensPerSecond } : {}),
  }));
  await AsyncStorage.setItem(blobKey(meta.id), JSON.stringify(clean));
  const list = await listConversations();
  const next = [meta, ...list.filter(c => c.id !== meta.id)];
  await writeIndex(next.sort((a, b) => b.updatedAt - a.updatedAt));
}

export async function deleteConversation(id: string): Promise<void> {
  await AsyncStorage.removeItem(blobKey(id));
  const list = await listConversations();
  await writeIndex(list.filter(c => c.id !== id));
}

export async function renameConversation(
  id: string,
  title: string,
): Promise<void> {
  const list = await listConversations();
  await writeIndex(list.map(c => (c.id === id ? { ...c, title } : c)));
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm test -- conversations`
Expected: PASS — all 8 tests green.

- [ ] **Step 6: Commit**

```bash
git add src/types.ts src/services/conversations.ts __tests__/conversations.test.ts
git commit -m "feat(chat): add conversation persistence service"
```

---

### Task 2: Add a `history` icon

**Files:**
- Modify: `src/components/Icon.tsx` (the `IconName` union ~line 4-33, and the `switch` in `renderPaths` before `default`)

- [ ] **Step 1: Add `history` to the `IconName` union**

In `src/components/Icon.tsx`, change the last union member:

```ts
  | 'copy'
  | 'sparkles'
  | 'history';
```

- [ ] **Step 2: Add the `history` case**

In `renderPaths`, immediately before `default:`:

```tsx
    case 'history':
      return (
        <>
          <Path {...c} d="M3 3v5h5" />
          <Path {...c} d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
          <Path {...c} d="M12 7v5l4 2" />
        </>
      );
```

- [ ] **Step 3: Type-check**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/components/Icon.tsx
git commit -m "feat(ui): add history icon"
```

---

### Task 3: Wire conversations into AppContext

**Files:**
- Modify: `src/context/AppContext.tsx`
- Modify: `src/screens/ChatScreen.tsx` (repoint New/+ buttons)

- [ ] **Step 1: Update imports in `AppContext.tsx`**

Replace the storage import block and the `types` import:

```ts
import {
  loadCustomModels,
  loadLastModelId,
  loadSystemPrompt,
  saveCustomModels,
  saveLastModelId,
  saveSystemPrompt,
} from '../services/storage';
import {
  deleteConversation as svcDeleteConversation,
  deriveTitle,
  listConversations,
  loadMessages,
  renameConversation as svcRenameConversation,
  saveConversation,
} from '../services/conversations';
import { ChatMessage, ConversationMeta, ModelInfo } from '../types';
```

- [ ] **Step 2: Update the `AppState` interface**

In the `AppState` interface, **remove** `clearChat: () => void;` and **add** these fields (place the data fields near `messages`, the actions near the other actions):

```ts
  conversations: ConversationMeta[];
  activeConversationId: string | null;
```
```ts
  newConversation: () => void;
  openConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
```

- [ ] **Step 3: Add state + a createdAt ref**

After `const [messages, setMessages] = useState<ChatMessage[]>([]);` add:

```ts
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  );
```

After the existing `const handles = useRef<...>({});` add:

```ts
  // Remembers createdAt for conversations created this session before they
  // first land in the `conversations` index.
  const createdAt = useRef<Record<string, number>>({});
```

- [ ] **Step 4: Load the conversation index on startup**

In the startup `useEffect`, extend the `Promise.all` and set state:

```ts
      const [custom, sysPrompt, lastId, convs] = await Promise.all([
        loadCustomModels(),
        loadSystemPrompt(),
        loadLastModelId(),
        listConversations(),
      ]);
      setCustomModels(custom);
      setSystemPromptState(sysPrompt);
      setConversations(convs);
```

- [ ] **Step 5: Stop wiping messages on model load**

In the `load` callback, **delete** the line `setMessages([]);` (so switching models keeps the active conversation).

- [ ] **Step 6: Add the persist helper + conversation actions**

Replace the existing `clearChat` definition:

```ts
  const clearChat = useCallback(() => setMessages([]), []);
```

with:

```ts
  const persistActive = useCallback(
    async (convId: string, msgs: ChatMessage[]) => {
      if (msgs.length === 0) {
        return;
      }
      const existing = conversations.find(c => c.id === convId);
      const meta: ConversationMeta = {
        id: convId,
        // Preserve a previously stored/renamed title; derive on first save.
        title: existing?.title ?? deriveTitle(msgs),
        createdAt: createdAt.current[convId] ?? existing?.createdAt ?? Date.now(),
        updatedAt: Date.now(),
        modelId: loadedModelId,
        messageCount: msgs.length,
      };
      try {
        await saveConversation(meta, msgs);
        setConversations(prev =>
          [meta, ...prev.filter(c => c.id !== convId)].sort(
            (a, b) => b.updatedAt - a.updatedAt,
          ),
        );
      } catch (e) {
        console.warn('[conversations] save failed:', e);
      }
    },
    [conversations, loadedModelId],
  );

  const newConversation = useCallback(() => {
    setActiveConversationId(null);
    setMessages([]);
  }, []);

  const openConversation = useCallback(async (id: string) => {
    const msgs = await loadMessages(id);
    setActiveConversationId(id);
    setMessages(msgs);
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    await svcDeleteConversation(id);
    delete createdAt.current[id];
    setConversations(prev => prev.filter(c => c.id !== id));
    setActiveConversationId(prev => {
      if (prev === id) {
        setMessages([]);
        return null;
      }
      return prev;
    });
  }, []);

  const renameConversation = useCallback(async (id: string, title: string) => {
    await svcRenameConversation(id, title);
    setConversations(prev =>
      prev.map(c => (c.id === id ? { ...c, title } : c)),
    );
  }, []);
```

- [ ] **Step 7: Make `sendMessage` create + persist the conversation**

At the **top** of the `sendMessage` callback body, right after the guard `if (!trimmed || isGenerating || !loadedModelId) { return; }`, add:

```ts
      let convId = activeConversationId;
      if (!convId) {
        convId = uid();
        createdAt.current[convId] = Date.now();
        setActiveConversationId(convId);
      }
```

In the `try` block, after the `setMessages(prev => prev.map(... streaming: false ...))` success update, add the persist call:

```ts
        await persistActive(convId, [
          ...history,
          {
            id: assistantId,
            role: 'assistant',
            content: target,
            tokensPerSecond: result.tokensPerSecond,
          },
        ]);
```

In the `catch` block, after the `setMessages(prev => prev.map(...))` update, add:

```ts
        await persistActive(convId, [
          ...history,
          { id: assistantId, role: 'assistant', content: target },
        ]);
```

Finally, update `sendMessage`'s dependency array to include the new deps:

```ts
    [activeConversationId, isGenerating, loadedModelId, messages, persistActive, systemPrompt],
```

- [ ] **Step 8: Update the context `value` object**

In the `value: AppState = { ... }` object, **remove** `clearChat,` and **add**:

```ts
    conversations,
    activeConversationId,
    newConversation,
    openConversation,
    deleteConversation,
    renameConversation,
```

- [ ] **Step 9: Repoint ChatScreen's New/+ buttons**

In `src/screens/ChatScreen.tsx`:

1. In the `useApp()` destructure, replace `clearChat,` with `newConversation,`.
2. The status-bar "New" button `onPress={clearChat}` → `onPress={newConversation}`.
3. The lead "+" button `onPress={hasMessages ? clearChat : undefined}` → `onPress={hasMessages ? newConversation : undefined}`.

- [ ] **Step 10: Type-check, lint, and run the existing test**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: tsc clean, lint clean, all tests pass (App render + conversations).

- [ ] **Step 11: Commit**

```bash
git add src/context/AppContext.tsx src/screens/ChatScreen.tsx
git commit -m "feat(chat): persist conversations and add thread actions to AppContext"
```

---

### Task 4: History panel + Chat-header button

**Files:**
- Create: `src/components/HistoryPanel.tsx`
- Modify: `App.tsx` (chat header + render the panel)

- [ ] **Step 1: Create `HistoryPanel.tsx`**

Create `src/components/HistoryPanel.tsx`:

```tsx
import React, { useEffect, useMemo, useRef } from 'react';
import {
  Alert,
  Animated,
  Dimensions,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { Icon } from './Icon';

function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(ts).toLocaleDateString();
}

const PANEL_WIDTH = Math.min(330, Dimensions.get('window').width * 0.84);

export function HistoryPanel({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    conversations,
    activeConversationId,
    openConversation,
    deleteConversation,
    newConversation,
  } = useApp();

  const slide = useRef(new Animated.Value(-PANEL_WIDTH)).current;
  const fade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(slide, {
        toValue: visible ? 0 : -PANEL_WIDTH,
        duration: 220,
        useNativeDriver: true,
      }),
      Animated.timing(fade, {
        toValue: visible ? 1 : 0,
        duration: 220,
        useNativeDriver: true,
      }),
    ]).start();
  }, [visible, slide, fade]);

  if (!visible) {
    return null;
  }

  const confirmDelete = (id: string, title: string) => {
    Alert.alert('Delete conversation', `Delete “${title}”?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => deleteConversation(id),
      },
    ]);
  };

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <Animated.View style={[styles.backdrop, { opacity: fade }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
      </Animated.View>

      <Animated.View
        style={[styles.panel, { transform: [{ translateX: slide }] }]}>
        <View style={styles.header}>
          <Text style={styles.heading}>Chats</Text>
          <Pressable onPress={onClose} hitSlop={8} style={styles.iconBtn}>
            <Icon name="close" size={20} color={colors.text} />
          </Pressable>
        </View>

        <Pressable
          style={styles.newBtn}
          onPress={() => {
            newConversation();
            onClose();
          }}>
          <Icon name="plus" size={18} color={colors.onPrimary} />
          <Text style={styles.newBtnText}>New chat</Text>
        </Pressable>

        <FlatList
          data={conversations}
          keyExtractor={c => c.id}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text style={styles.empty}>No conversations yet.</Text>
          }
          renderItem={({ item }) => (
            <Pressable
              style={[
                styles.row,
                item.id === activeConversationId && styles.rowActive,
              ]}
              onPress={() => {
                openConversation(item.id);
                onClose();
              }}
              onLongPress={() => confirmDelete(item.id, item.title)}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={styles.rowMeta}>
                  {relativeTime(item.updatedAt)} • {item.messageCount} msgs
                </Text>
              </View>
              <Pressable
                hitSlop={8}
                onPress={() => confirmDelete(item.id, item.title)}>
                <Icon name="trash" size={17} color={colors.textFaint} />
              </Pressable>
            </Pressable>
          )}
        />
      </Animated.View>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    backdrop: {
      ...StyleSheet.absoluteFillObject,
      backgroundColor: 'rgba(0,0,0,0.4)',
    },
    panel: {
      position: 'absolute',
      top: 0,
      bottom: 0,
      left: 0,
      width: PANEL_WIDTH,
      backgroundColor: colors.surface,
      borderRightWidth: 1,
      borderRightColor: colors.border,
      paddingTop: 56,
      paddingHorizontal: spacing.md,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: spacing.md,
    },
    heading: {
      color: colors.text,
      fontSize: 22,
      fontFamily: fonts.display.bold,
    },
    iconBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.surfaceAlt,
    },
    newBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: colors.primary,
      paddingVertical: spacing.md,
      borderRadius: radius.md,
      marginBottom: spacing.md,
    },
    newBtnText: {
      color: colors.onPrimary,
      fontFamily: fonts.body.bold,
      fontSize: 15,
    },
    listContent: { paddingBottom: spacing.xl },
    empty: {
      color: colors.textFaint,
      fontFamily: fonts.body.regular,
      textAlign: 'center',
      marginTop: spacing.xl,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.md,
      paddingHorizontal: spacing.sm,
      borderRadius: radius.md,
    },
    rowActive: { backgroundColor: colors.surfaceAlt },
    rowTitle: {
      color: colors.text,
      fontSize: 15,
      fontFamily: fonts.body.semibold,
    },
    rowMeta: {
      color: colors.textDim,
      fontSize: 12,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
  });
```

- [ ] **Step 2: Add history-panel state + button to `App.tsx`**

In `App.tsx`, add the import near the other component imports:

```ts
import { HistoryPanel } from './src/components/HistoryPanel';
```

In `Shell`, add state near the other `useState` hooks:

```ts
  const [historyOpen, setHistoryOpen] = useState(false);
```

Replace the **non-tool header branch** (the `: (` ... `<> ... </>` ... `)` block that renders the plain title/subtitle) with a version that adds a history button on the chat tab:

```tsx
        ) : tab === 'chat' ? (
          <View style={styles.headerRow}>
            <Pressable
              onPress={() => setHistoryOpen(true)}
              hitSlop={10}
              style={styles.backBtn}>
              <Icon name="history" size={22} color={colors.text} />
            </Pressable>
            <View style={{ flex: 1 }}>
              <Text style={styles.title} numberOfLines={1}>
                {headerTitle}
              </Text>
              <Text style={styles.subtitle} numberOfLines={1}>
                {subtitle}
              </Text>
            </View>
          </View>
        ) : (
          <>
            <Text style={styles.title}>{headerTitle}</Text>
            <Text style={styles.subtitle}>{subtitle}</Text>
          </>
        )}
```

- [ ] **Step 3: Render the panel as an overlay**

In `Shell`'s returned tree, immediately **before** the closing `</View>` of `styles.root`, add:

```tsx
      <HistoryPanel
        visible={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
```

- [ ] **Step 4: Type-check, lint, test**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: all clean / green.

- [ ] **Step 5: Commit**

```bash
git add src/components/HistoryPanel.tsx App.tsx
git commit -m "feat(chat): add slide-in history panel and header button"
```

---

### Task 5: Manual verification walk

**Files:** none (verification only)

- [ ] **Step 1: Build & launch on iOS**

Run: `npm run ios`
(If the simulator/runtime misbehaves, see the Xcode 26.5 sim-runtime note in project memory.)

- [ ] **Step 2: Walk the happy path (iOS)**

Confirm each:
- Load a model, send 2–3 messages.
- Tap the **history icon** (top-left of the Chat header) → panel slides in, shows the current thread with a title from your first message.
- Tap **"+ New chat"** → returns to the landing hero; send a different message → a second thread appears in history.
- **Kill and relaunch the app** → open history → both conversations are still listed; tap one → its messages reload.
- **Long-press** a row (or tap the trash) → confirm delete → it disappears; deleting the active thread returns to the hero.
- Switch to the **Models** tab, load a *different* model, return to Chat → the active conversation's messages are **still present** (no wipe).

- [ ] **Step 3: Build, launch & repeat on Android**

Run: `npm run android`
Repeat Step 2 on the Android emulator.

- [ ] **Step 4: Final commit (if any doc/notes updates)**

```bash
git add -A
git commit -m "chore(chat): verify persistent history on iOS and Android" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- Data model (`ConversationMeta`) → Task 1 Step 1. ✓
- Storage layout (index + per-conversation blobs, versioned keys) → Task 1 Step 4. ✓
- Persistence timing (end of turn, never mid-token) → Task 3 Step 7 (persist in try/catch after stream finalizes). ✓
- `conversations.ts` service (all 5 functions + `deriveTitle`) → Task 1. ✓
- State (`conversations`, `activeConversationId`) + startup load → Task 3 Steps 3–4. ✓
- Actions (`newConversation`/`openConversation`/`deleteConversation`/`renameConversation`) → Task 3 Step 6. ✓
- Lazy-create on first message → Task 3 Step 7. ✓
- Remove model-load wipe → Task 3 Step 5. ✓
- History button + slide-in panel + new/open/delete UI → Tasks 2 & 4. ✓
- Repoint New/+ buttons → Task 3 Step 9. ✓
- Error handling (guarded reads, save failure logged not thrown) → service try/catch + `persistActive` try/catch. ✓
- Testing (service unit tests + manual walk) → Task 1 + Task 5. ✓
- Migration (none; versioned keys) → covered by `.v1` keys; no migration step needed. ✓

**Note:** `renameConversation` is exposed in context + service and unit-tested, but the panel UI in Task 4 only wires new/open/delete (rename is an optional/cheap extra per the spec). The capability exists; surfacing a rename affordance can be a trivial follow-up and is intentionally not blocking.

**Placeholder scan:** none — every code step contains complete code.

**Type consistency:** `ConversationMeta`, `deriveTitle`, and the five service functions use identical names/signatures across Task 1 (definition), Task 3 (consumption with `svcDeleteConversation`/`svcRenameConversation` aliases to avoid colliding with the context action names), and the tests.

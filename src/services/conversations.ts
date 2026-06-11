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

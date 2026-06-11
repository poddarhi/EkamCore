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
    expect(deriveTitle([msg('user', 'a'.repeat(60))]).length).toBeLessThanOrEqual(
      41,
    );
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
    await saveConversation(meta({ id: 'old', updatedAt: 1000 }), [
      msg('user', 'a'),
    ]);
    await saveConversation(meta({ id: 'new', updatedAt: 2000 }), [
      msg('user', 'b'),
    ]);
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

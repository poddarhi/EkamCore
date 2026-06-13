import {
  estimateTokens,
  pickContextSize,
  windowHistory,
} from '../src/services/llama';
import { ChatMessage } from '../src/types';

const GiB = 1024 * 1024 * 1024;
const m = (role: ChatMessage['role'], content: string): ChatMessage => ({
  id: `${role}-${content}`,
  role,
  content,
});

describe('pickContextSize', () => {
  it('scales the context window with device RAM', () => {
    expect(pickContextSize(3 * GiB)).toBe(2048);
    expect(pickContextSize(4 * GiB)).toBe(4096);
    expect(pickContextSize(6 * GiB)).toBe(6144);
    expect(pickContextSize(8 * GiB)).toBe(8192);
    expect(pickContextSize(16 * GiB)).toBe(8192);
  });
});

describe('estimateTokens', () => {
  it('is ~chars/4 plus per-message overhead and tolerates empty', () => {
    expect(estimateTokens('')).toBe(4);
    expect(estimateTokens('a'.repeat(8))).toBe(2 + 4);
  });
});

describe('windowHistory', () => {
  it('keeps recent turns within budget, dropping oldest whole turns first', () => {
    // Each 1-char message estimates to ceil(1/4)+4 = 5 tokens.
    const history = [
      m('user', '1'),
      m('assistant', '2'),
      m('user', '3'),
      m('assistant', '4'),
    ];
    const kept = windowHistory(history, 10);
    expect(kept.map(x => x.content)).toEqual(['3', '4']);
  });

  it('always keeps at least the most recent message, even if it exceeds budget', () => {
    const kept = windowHistory([m('user', 'a'.repeat(1000))], 1);
    expect(kept).toHaveLength(1);
  });

  it('drops the system role (the caller pins it separately)', () => {
    const kept = windowHistory([m('system', 'sys'), m('user', 'hi')], 100);
    expect(kept.every(x => x.role !== 'system')).toBe(true);
    expect(kept.map(x => x.content)).toEqual(['hi']);
  });

  it('keeps the whole history when it fits', () => {
    const history = [m('user', 'a'), m('assistant', 'b')];
    expect(windowHistory(history, 1000)).toEqual(history);
  });
});

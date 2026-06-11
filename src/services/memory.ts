import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'ekamcore.memory.v1';

export interface MemoryProfile {
  /** Master switch — when off, nothing is injected and nothing is learned. */
  enabled: boolean;
  /** Durable facts/preferences the user has revealed (editable by the user). */
  facts: string[];
  /** One-line description of how the user likes answers (length, tone, format). */
  style: string;
}

export const EMPTY_MEMORY: MemoryProfile = {
  enabled: false,
  facts: [],
  style: '',
};

export async function loadMemory(): Promise<MemoryProfile> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) {
      return EMPTY_MEMORY;
    }
    const p = JSON.parse(raw);
    return {
      enabled: !!p.enabled,
      facts: Array.isArray(p.facts)
        ? p.facts.filter((x: unknown) => typeof x === 'string')
        : [],
      style: typeof p.style === 'string' ? p.style : '',
    };
  } catch {
    return EMPTY_MEMORY;
  }
}

export async function saveMemory(profile: MemoryProfile): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(profile));
  } catch {
    // ignore write errors
  }
}

/**
 * Build the text block injected into the system prompt. Returns '' when
 * personalization is off or there's nothing learned yet.
 */
export function buildMemoryBlock(profile: MemoryProfile): string {
  if (!profile.enabled) {
    return '';
  }
  const facts = profile.facts.map(f => f.trim()).filter(Boolean);
  const style = profile.style.trim();
  if (facts.length === 0 && !style) {
    return '';
  }
  let block = '\n\nWhat you know about the user (use it to personalize your replies):';
  for (const f of facts) {
    block += `\n- ${f}`;
  }
  if (style) {
    block += `\nPreferred answer style: ${style}`;
  }
  return block;
}

// System prompt used when asking the on-device model to summarize the user.
export const LEARN_SYSTEM =
  'You build a concise profile of a user from a chat transcript. ' +
  'Reply with ONLY a JSON object and no other text:\n' +
  '{"facts": ["short durable fact or preference the user revealed about themselves"], ' +
  '"style": "one sentence on how they seem to prefer answers (length, tone, format)"}\n' +
  'Include at most 6 facts. Only include things the USER revealed about themselves or ' +
  'clear preferences — never invent. If unsure, use an empty array/string.';

/** Defensively parse the model's JSON profile output. Never throws. */
export function parseLearnedProfile(text: string): {
  facts: string[];
  style: string;
} {
  try {
    const m = text.match(/\{[\s\S]*\}/);
    if (!m) {
      return { facts: [], style: '' };
    }
    const o = JSON.parse(m[0]);
    const facts = Array.isArray(o.facts)
      ? o.facts
          .filter((x: unknown) => typeof x === 'string' && x.trim())
          .map((x: string) => x.trim())
          .slice(0, 6)
      : [];
    const style = typeof o.style === 'string' ? o.style.trim() : '';
    return { facts, style };
  } catch {
    return { facts: [], style: '' };
  }
}

/** Build a compact transcript from chat messages for the learn step. */
export function buildTranscript(
  messages: Array<{ role: string; content: string }>,
): string {
  return messages
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
    .join('\n')
    .slice(-4000);
}

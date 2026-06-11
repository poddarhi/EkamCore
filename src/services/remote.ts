import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'ekamcore.remoteEndpoints.v1';

// A user's own compute running an OpenAI-compatible or Ollama HTTP server,
// reached over their LAN or a private mesh (e.g. Tailscale).
export interface RemoteEndpoint {
  id: string;
  name: string;
  /** Base URL, e.g. http://100.x.x.x:11434 (Ollama) or http://host:1234/v1 (OpenAI). */
  baseUrl: string;
  kind: 'ollama' | 'openai';
  apiKey?: string;
}

export interface RemoteChatMessage {
  role: string;
  content: string;
}

const trimSlash = (s: string) => s.replace(/\/+$/, '');

export async function loadEndpoints(): Promise<RemoteEndpoint[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as RemoteEndpoint[]) : [];
  } catch {
    return [];
  }
}

export async function saveEndpoints(eps: RemoteEndpoint[]): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(eps));
  } catch {
    // ignore
  }
}

// --- Pure parse helpers (unit-tested) ---

export function parseModelList(kind: RemoteEndpoint['kind'], data: any): string[] {
  if (kind === 'ollama') {
    const models = data?.models;
    return Array.isArray(models)
      ? models.map((m: any) => String(m?.name ?? '')).filter(Boolean)
      : [];
  }
  const arr = data?.data;
  return Array.isArray(arr)
    ? arr.map((m: any) => String(m?.id ?? '')).filter(Boolean)
    : [];
}

export function parseChatContent(kind: RemoteEndpoint['kind'], data: any): string {
  if (kind === 'ollama') {
    return String(data?.message?.content ?? '');
  }
  return String(data?.choices?.[0]?.message?.content ?? '');
}

// --- Network calls (never throw; return [] / throw a friendly Error for chat) ---

function headers(ep: RemoteEndpoint): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ep.apiKey) {
    h.Authorization = `Bearer ${ep.apiKey}`;
  }
  return h;
}

/** List the models available on a remote endpoint. [] on failure. */
export async function listRemoteModels(ep: RemoteEndpoint): Promise<string[]> {
  try {
    const base = trimSlash(ep.baseUrl);
    const url = ep.kind === 'ollama' ? `${base}/api/tags` : `${base}/models`;
    const res = await fetch(url, { headers: headers(ep) });
    if (!res.ok) {
      return [];
    }
    return parseModelList(ep.kind, await res.json());
  } catch {
    return [];
  }
}

/**
 * Run a (non-streaming) chat completion against a remote endpoint and return
 * the assistant text. Throws a friendly Error on failure so the chat UI can
 * surface it.
 */
export async function remoteChat(
  ep: RemoteEndpoint,
  model: string,
  messages: RemoteChatMessage[],
): Promise<string> {
  const base = trimSlash(ep.baseUrl);
  const url =
    ep.kind === 'ollama' ? `${base}/api/chat` : `${base}/chat/completions`;
  const body =
    ep.kind === 'ollama'
      ? { model, messages, stream: false }
      : { model, messages, stream: false };
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: headers(ep),
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(`Couldn't reach ${ep.name}. Check it's online and reachable.`);
  }
  if (!res.ok) {
    throw new Error(`${ep.name} returned an error (${res.status}).`);
  }
  const content = parseChatContent(ep.kind, await res.json());
  if (!content) {
    throw new Error(`${ep.name} returned an empty response.`);
  }
  return content;
}

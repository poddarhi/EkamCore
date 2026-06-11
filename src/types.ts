export type ModelStatus =
  | 'available'
  | 'downloading'
  | 'downloaded'
  | 'error';

export interface ModelInfo {
  /** Stable unique id */
  id: string;
  /** Human readable name shown in the UI */
  name: string;
  /** Short description / size hint */
  description: string;
  /** Approximate download size in bytes (for UI only) */
  sizeBytes: number;
  /** Direct GGUF download URL */
  url: string;
  /** Number of params hint, e.g. "0.5B" */
  params: string;
  /** Quantization label, e.g. "Q4_K_M" */
  quant: string;
  /** True when the user added it manually (e.g. custom HF url) */
  custom?: boolean;
}

export interface DownloadProgress {
  modelId: string;
  receivedBytes: number;
  totalBytes: number;
  /** 0..1 */
  progress: number;
}

export type ChatRole = 'system' | 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** transient flag while the assistant token stream is in flight */
  streaming?: boolean;
  /** tokens-per-second once generation finishes */
  tokensPerSecond?: number;
}

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

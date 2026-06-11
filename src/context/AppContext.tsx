import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { CATALOG } from '../data/models';
import {
  DownloadHandle,
  deleteModel as fsDeleteModel,
  ensureModelsDir,
  isModelDownloaded,
  modelFilePath,
  startDownload,
} from '../services/download';
import {
  generate,
  getLoadedModel,
  loadModel,
  releaseModel,
  stopGeneration,
} from '../services/llama';
import {
  loadCustomModels,
  loadLastModelId,
  loadSystemPrompt,
  saveCustomModels,
  saveLastModelId,
  saveSystemPrompt,
} from '../services/storage';
import { ChatMessage, ModelInfo } from '../types';

interface DownloadState {
  received: number;
  total: number;
}

interface AppState {
  models: ModelInfo[];
  downloadedIds: string[];
  downloads: Record<string, DownloadState>;
  downloadErrors: Record<string, string>;
  loadedModelId: string | null;
  loadingModelId: string | null;
  loadProgress: number;
  messages: ChatMessage[];
  isGenerating: boolean;
  systemPrompt: string;

  download: (model: ModelInfo) => void;
  cancelDownload: (model: ModelInfo) => void;
  removeModel: (model: ModelInfo) => Promise<void>;
  addCustomModel: (name: string, url: string) => Promise<void>;
  load: (model: ModelInfo) => Promise<void>;
  unload: () => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  complete: (opts: CompleteOptions) => Promise<string>;
  stop: () => Promise<void>;
  clearChat: () => void;
  setSystemPrompt: (prompt: string) => void;
}

export interface CompleteOptions {
  system: string;
  prompt: string;
  temperature?: number;
  maxTokens?: number;
  onUpdate?: (text: string) => void;
}

const AppContext = createContext<AppState | null>(null);

const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [customModels, setCustomModels] = useState<ModelInfo[]>([]);
  const [downloadedIds, setDownloadedIds] = useState<string[]>([]);
  const [downloads, setDownloads] = useState<Record<string, DownloadState>>({});
  const [downloadErrors, setDownloadErrors] = useState<
    Record<string, string>
  >({});
  const [loadedModelId, setLoadedModelId] = useState<string | null>(null);
  const [loadingModelId, setLoadingModelId] = useState<string | null>(null);
  const [loadProgress, setLoadProgress] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [systemPrompt, setSystemPromptState] = useState(
    'You are a helpful assistant.',
  );

  const handles = useRef<Record<string, DownloadHandle>>({});

  const models = useMemo(
    () => [...CATALOG, ...customModels],
    [customModels],
  );

  const refreshDownloaded = useCallback(async (list: ModelInfo[]) => {
    const present: string[] = [];
    for (const m of list) {
      if (await isModelDownloaded(m)) {
        present.push(m.id);
      }
    }
    setDownloadedIds(present);
  }, []);

  useEffect(() => {
    (async () => {
      await ensureModelsDir();
      const [custom, sysPrompt, lastId] = await Promise.all([
        loadCustomModels(),
        loadSystemPrompt(),
        loadLastModelId(),
      ]);
      setCustomModels(custom);
      setSystemPromptState(sysPrompt);
      await refreshDownloaded([...CATALOG, ...custom]);
      const existing = getLoadedModel();
      if (existing) {
        setLoadedModelId(existing.modelId);
      } else if (lastId) {
        // Don't auto-load (heavy); just remember last selection visually.
      }
    })();
    return () => {
      releaseModel();
    };
  }, [refreshDownloaded]);

  const clearDownloadState = useCallback((id: string) => {
    delete handles.current[id];
    setDownloads(d => {
      const next = { ...d };
      delete next[id];
      return next;
    });
  }, []);

  const download = useCallback(
    (model: ModelInfo) => {
      if (handles.current[model.id]) {
        return;
      }
      setDownloadErrors(e => {
        const next = { ...e };
        delete next[model.id];
        return next;
      });
      setDownloads(d => ({
        ...d,
        [model.id]: { received: 0, total: model.sizeBytes || 0 },
      }));
      const handle = startDownload(model, (received, total) => {
        setDownloads(d => ({
          ...d,
          [model.id]: { received, total: total || model.sizeBytes || 0 },
        }));
      });
      handles.current[model.id] = handle;
      handle.task
        .then(async () => {
          clearDownloadState(model.id);
          // Re-verify against the filesystem so the UI reflects ground truth.
          const ok = await isModelDownloaded(model);
          if (ok) {
            setDownloadedIds(ids =>
              ids.includes(model.id) ? ids : [...ids, model.id],
            );
          } else {
            setDownloadErrors(e => ({
              ...e,
              [model.id]: 'File missing after download. Please retry.',
            }));
          }
        })
        .catch((err: any) => {
          console.warn(`[download] ${model.id} failed:`, err);
          clearDownloadState(model.id);
          setDownloadErrors(e => ({
            ...e,
            [model.id]: err?.message ?? 'Download failed.',
          }));
        });
    },
    [clearDownloadState],
  );

  const cancelDownload = useCallback((model: ModelInfo) => {
    const handle = handles.current[model.id];
    if (handle) {
      handle.cancel();
      delete handles.current[model.id];
    }
    setDownloads(d => {
      const next = { ...d };
      delete next[model.id];
      return next;
    });
  }, []);

  const removeModel = useCallback(
    async (model: ModelInfo) => {
      if (loadedModelId === model.id) {
        await releaseModel();
        setLoadedModelId(null);
      }
      await fsDeleteModel(model);
      setDownloadedIds(ids => ids.filter(id => id !== model.id));
    },
    [loadedModelId],
  );

  const addCustomModel = useCallback(
    async (name: string, url: string) => {
      const trimmed = url.trim();
      const model: ModelInfo = {
        id: `custom-${uid()}`,
        name: name.trim() || 'Custom model',
        description: 'Added from a custom GGUF URL.',
        params: '—',
        quant: 'GGUF',
        sizeBytes: 0,
        url: trimmed,
        custom: true,
      };
      const next = [...customModels, model];
      setCustomModels(next);
      await saveCustomModels(next);
    },
    [customModels],
  );

  const load = useCallback(
    async (model: ModelInfo) => {
      setLoadingModelId(model.id);
      setLoadProgress(0);
      try {
        await loadModel(model.id, modelFilePath(model), p =>
          setLoadProgress(p),
        );
        setLoadedModelId(model.id);
        await saveLastModelId(model.id);
        setMessages([]);
      } finally {
        setLoadingModelId(null);
      }
    },
    [],
  );

  const unload = useCallback(async () => {
    await releaseModel();
    setLoadedModelId(null);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isGenerating || !loadedModelId) {
        return;
      }
      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        content: trimmed,
      };
      const assistantId = uid();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        streaming: true,
      };

      const history = [...messages, userMsg];
      setMessages([...history, assistantMsg]);
      setIsGenerating(true);

      // Typewriter buffer: tokens stream into `target` as fast as the model
      // produces them, while a timer reveals `shown` characters at a smooth,
      // readable pace — independent of how fast the model actually runs.
      let target = '';
      let shown = 0;
      const revealTimer = setInterval(() => {
        if (shown >= target.length) {
          return;
        }
        const remaining = target.length - shown;
        // Reveal faster when the buffer is large so we never lag too far behind.
        const step = Math.max(2, Math.ceil(remaining / 25));
        shown = Math.min(target.length, shown + step);
        const text = target.slice(0, shown);
        setMessages(prev =>
          prev.map(m => (m.id === assistantId ? { ...m, content: text } : m)),
        );
      }, 18);

      try {
        const result = await generate({
          systemPrompt,
          history,
          onToken: token => {
            target += token;
          },
        });
        target = result.text || target;
        // Let the typewriter finish revealing everything that was generated.
        await new Promise<void>(resolve => {
          const finish = setInterval(() => {
            if (shown >= target.length) {
              clearInterval(finish);
              resolve();
            }
          }, 18);
        });
        clearInterval(revealTimer);
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? {
                  ...m,
                  content: target,
                  streaming: false,
                  tokensPerSecond: result.tokensPerSecond,
                }
              : m,
          ),
        );
      } catch (e: any) {
        clearInterval(revealTimer);
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? {
                  ...m,
                  content:
                    m.content ||
                    `⚠️ Generation failed: ${e?.message ?? 'unknown error'}`,
                  streaming: false,
                }
              : m,
          ),
        );
      } finally {
        setIsGenerating(false);
      }
    },
    [isGenerating, loadedModelId, messages, systemPrompt],
  );

  // One-shot completion used by the AI Tools (email, summarizer, etc.).
  // Streams the accumulated text via onUpdate; shares the generation lock.
  const complete = useCallback(
    async (opts: CompleteOptions): Promise<string> => {
      if (!loadedModelId || isGenerating) {
        return '';
      }
      setIsGenerating(true);
      let acc = '';
      try {
        const result = await generate({
          systemPrompt: opts.system,
          history: [{ id: uid(), role: 'user', content: opts.prompt }],
          temperature: opts.temperature ?? 0.7,
          maxTokens: opts.maxTokens ?? 768,
          onToken: t => {
            acc += t;
            opts.onUpdate?.(acc);
          },
        });
        const final = result.text || acc;
        opts.onUpdate?.(final);
        return final;
      } finally {
        setIsGenerating(false);
      }
    },
    [loadedModelId, isGenerating],
  );

  const stop = useCallback(async () => {
    await stopGeneration();
    setIsGenerating(false);
    setMessages(prev =>
      prev.map(m => (m.streaming ? { ...m, streaming: false } : m)),
    );
  }, []);

  const clearChat = useCallback(() => setMessages([]), []);

  const setSystemPrompt = useCallback((prompt: string) => {
    setSystemPromptState(prompt);
    saveSystemPrompt(prompt).catch(() => {});
  }, []);

  const value: AppState = {
    models,
    downloadedIds,
    downloads,
    downloadErrors,
    loadedModelId,
    loadingModelId,
    loadProgress,
    messages,
    isGenerating,
    systemPrompt,
    download,
    cancelDownload,
    removeModel,
    addCustomModel,
    load,
    unload,
    sendMessage,
    complete,
    stop,
    clearChat,
    setSystemPrompt,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error('useApp must be used within AppProvider');
  }
  return ctx;
}

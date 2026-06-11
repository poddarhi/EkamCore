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
import {
  deleteConversation as svcDeleteConversation,
  deriveTitle,
  listConversations,
  loadMessages,
  renameConversation as svcRenameConversation,
  saveConversation,
} from '../services/conversations';
import { DeviceProfile, getDeviceProfile } from '../services/device';
import {
  loadEndpoints,
  remoteChat,
  RemoteEndpoint,
  saveEndpoints,
} from '../services/remote';
import {
  fetchFeaturedCatalog,
  loadCachedCatalog,
} from '../services/catalog';
import {
  buildMemoryBlock,
  buildTranscript,
  EMPTY_MEMORY,
  LEARN_SYSTEM,
  loadMemory,
  MemoryProfile,
  parseLearnedProfile,
  saveMemory,
} from '../services/memory';
import { ChatMessage, ConversationMeta, ModelInfo } from '../types';

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
  deviceProfile: DeviceProfile | null;
  messages: ChatMessage[];
  conversations: ConversationMeta[];
  activeConversationId: string | null;
  isGenerating: boolean;
  systemPrompt: string;
  memory: MemoryProfile;
  remoteEndpoints: RemoteEndpoint[];
  activeRemote: { endpointId: string; model: string } | null;

  download: (model: ModelInfo) => void;
  cancelDownload: (model: ModelInfo) => void;
  removeModel: (model: ModelInfo) => Promise<void>;
  addCustomModel: (name: string, url: string) => Promise<void>;
  addModel: (model: ModelInfo) => Promise<void>;
  load: (model: ModelInfo) => Promise<void>;
  unload: () => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  /** Re-run the last user message, replacing the assistant reply after it. */
  regenerate: () => Promise<void>;
  complete: (opts: CompleteOptions) => Promise<string>;
  stop: () => Promise<void>;
  newConversation: () => void;
  openConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  setSystemPrompt: (prompt: string) => void;
  setMemoryEnabled: (enabled: boolean) => void;
  updateMemory: (facts: string[], style: string) => void;
  learnFromChats: () => Promise<boolean>;
  clearMemory: () => void;
  addEndpoint: (ep: RemoteEndpoint) => void;
  removeEndpoint: (id: string) => void;
  selectRemoteModel: (endpointId: string, model: string) => void;
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
  // Featured catalog: seeded with the bundled list, replaced by cache/remote.
  const [featured, setFeatured] = useState<ModelInfo[]>(CATALOG);
  const [downloadedIds, setDownloadedIds] = useState<string[]>([]);
  const [downloads, setDownloads] = useState<Record<string, DownloadState>>({});
  const [downloadErrors, setDownloadErrors] = useState<
    Record<string, string>
  >({});
  const [loadedModelId, setLoadedModelId] = useState<string | null>(null);
  const [loadingModelId, setLoadingModelId] = useState<string | null>(null);
  const [loadProgress, setLoadProgress] = useState(0);
  const [deviceProfile, setDeviceProfile] = useState<DeviceProfile | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [systemPrompt, setSystemPromptState] = useState(
    'You are a helpful assistant.',
  );
  const [memory, setMemory] = useState<MemoryProfile>(EMPTY_MEMORY);
  const [remoteEndpoints, setRemoteEndpoints] = useState<RemoteEndpoint[]>([]);
  // When set, chat is routed to a model on the user's own remote compute.
  const [activeRemote, setActiveRemote] = useState<{
    endpointId: string;
    model: string;
  } | null>(null);

  const handles = useRef<Record<string, DownloadHandle>>({});

  // Remembers createdAt for conversations created this session before they
  // first land in the `conversations` index.
  const createdAt = useRef<Record<string, number>>({});

  const models = useMemo(
    () => [...featured, ...customModels],
    [featured, customModels],
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
      const [custom, sysPrompt, lastId, convs] = await Promise.all([
        loadCustomModels(),
        loadSystemPrompt(),
        loadLastModelId(),
        listConversations(),
      ]);
      setCustomModels(custom);
      setSystemPromptState(sysPrompt);
      setConversations(convs);
      loadMemory().then(setMemory);
      loadEndpoints().then(setRemoteEndpoints);
      getDeviceProfile().then(setDeviceProfile);

      // Featured catalog: show cached-or-seed immediately, then refresh from
      // the remote CDN in the background (offline keeps the cache/seed).
      const cached = await loadCachedCatalog();
      const initialFeatured = cached ?? CATALOG;
      setFeatured(initialFeatured);
      await refreshDownloaded([...initialFeatured, ...custom]);
      fetchFeaturedCatalog().then(remote => {
        if (remote) {
          setFeatured(remote);
          refreshDownloaded([...remote, ...custom]);
        }
      });
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

  const addModel = useCallback(async (model: ModelInfo) => {
    setCustomModels(prev => {
      if (prev.some(m => m.id === model.id)) {
        return prev;
      }
      const next = [...prev, model];
      saveCustomModels(next).catch(() => {});
      return next;
    });
  }, []);

  const load = useCallback(
    async (model: ModelInfo) => {
      setLoadingModelId(model.id);
      setLoadProgress(0);
      try {
        await loadModel(model.id, modelFilePath(model), p =>
          setLoadProgress(p),
        );
        setLoadedModelId(model.id);
        setActiveRemote(null);
        await saveLastModelId(model.id);
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

  // Shared send path: `base` is the history the new user turn appends to.
  // sendMessage passes the live message list; regenerate passes a truncated one.
  const runSend = useCallback(
    async (text: string, base: ChatMessage[]) => {
      const trimmed = text.trim();
      if (!trimmed || isGenerating || (!loadedModelId && !activeRemote)) {
        return;
      }
      let convId = activeConversationId;
      if (!convId) {
        convId = uid();
        createdAt.current[convId] = Date.now();
        setActiveConversationId(convId);
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

      const history = [...base, userMsg];
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
        const revealed = target.slice(0, shown);
        setMessages(prev =>
          prev.map(m => (m.id === assistantId ? { ...m, content: revealed } : m)),
        );
      }, 18);

      let tps: number | undefined;
      try {
        if (activeRemote) {
          const ep = remoteEndpoints.find(e => e.id === activeRemote.endpointId);
          if (!ep) {
            throw new Error('That connection is no longer available.');
          }
          const msgs = [
            { role: 'system', content: systemPrompt + buildMemoryBlock(memory) },
            ...history
              .filter(m => m.role !== 'system')
              .map(m => ({ role: m.role, content: m.content })),
          ];
          // Non-streaming; the typewriter below reveals the full reply.
          target = await remoteChat(ep, activeRemote.model, msgs);
        } else {
          const result = await generate({
            systemPrompt: systemPrompt + buildMemoryBlock(memory),
            history,
            onToken: token => {
              target += token;
            },
          });
          target = result.text || target;
          tps = result.tokensPerSecond;
        }
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
                  tokensPerSecond: tps,
                }
              : m,
          ),
        );
        await persistActive(convId, [
          ...history,
          {
            id: assistantId,
            role: 'assistant',
            content: target,
            tokensPerSecond: tps,
          },
        ]);
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
        await persistActive(convId, [
          ...history,
          { id: assistantId, role: 'assistant', content: target },
        ]);
      } finally {
        setIsGenerating(false);
      }
    },
    [
      activeConversationId,
      activeRemote,
      isGenerating,
      loadedModelId,
      memory,
      persistActive,
      remoteEndpoints,
      systemPrompt,
    ],
  );

  const sendMessage = useCallback(
    (text: string) => runSend(text, messages),
    [runSend, messages],
  );

  const regenerate = useCallback(async () => {
    if (isGenerating) {
      return;
    }
    const lastUserIdx = messages.map(m => m.role).lastIndexOf('user');
    if (lastUserIdx < 0) {
      return;
    }
    const lastUser = messages[lastUserIdx];
    const base = messages.slice(0, lastUserIdx);
    setMessages(base);
    await runSend(lastUser.content, base);
  }, [isGenerating, messages, runSend]);

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

  const setSystemPrompt = useCallback((prompt: string) => {
    setSystemPromptState(prompt);
    saveSystemPrompt(prompt).catch(() => {});
  }, []);

  const setMemoryEnabled = useCallback((enabled: boolean) => {
    setMemory(prev => {
      const next = { ...prev, enabled };
      saveMemory(next);
      return next;
    });
  }, []);

  const updateMemory = useCallback((facts: string[], style: string) => {
    setMemory(prev => {
      const next = { ...prev, facts, style };
      saveMemory(next);
      return next;
    });
  }, []);

  const addEndpoint = useCallback((ep: RemoteEndpoint) => {
    setRemoteEndpoints(prev => {
      const next = [...prev.filter(e => e.id !== ep.id), ep];
      saveEndpoints(next);
      return next;
    });
  }, []);

  const removeEndpoint = useCallback((id: string) => {
    setRemoteEndpoints(prev => {
      const next = prev.filter(e => e.id !== id);
      saveEndpoints(next);
      return next;
    });
    setActiveRemote(prev => (prev?.endpointId === id ? null : prev));
  }, []);

  const selectRemoteModel = useCallback(
    (endpointId: string, model: string) => {
      setActiveRemote({ endpointId, model });
    },
    [],
  );

  const clearMemory = useCallback(() => {
    setMemory(prev => {
      const next = { ...prev, facts: [], style: '' };
      saveMemory(next);
      return next;
    });
  }, []);

  // Ask the loaded model to summarize the active chat into facts + style.
  const learnFromChats = useCallback(async (): Promise<boolean> => {
    if (!loadedModelId || isGenerating) {
      return false;
    }
    const transcript = buildTranscript(messages);
    if (!transcript.trim()) {
      return false;
    }
    setIsGenerating(true);
    try {
      const result = await generate({
        systemPrompt: LEARN_SYSTEM,
        history: [{ id: uid(), role: 'user', content: transcript }],
        temperature: 0.2,
        maxTokens: 400,
        onToken: () => {},
      });
      const learned = parseLearnedProfile(result.text || '');
      if (learned.facts.length === 0 && !learned.style) {
        return false;
      }
      setMemory(prev => {
        const facts = Array.from(
          new Set([...prev.facts, ...learned.facts]),
        ).slice(0, 12);
        const next: MemoryProfile = {
          enabled: true,
          facts,
          style: learned.style || prev.style,
        };
        saveMemory(next);
        return next;
      });
      return true;
    } finally {
      setIsGenerating(false);
    }
  }, [loadedModelId, isGenerating, messages]);

  const value: AppState = {
    models,
    downloadedIds,
    downloads,
    downloadErrors,
    loadedModelId,
    loadingModelId,
    loadProgress,
    deviceProfile,
    messages,
    conversations,
    activeConversationId,
    isGenerating,
    systemPrompt,
    memory,
    remoteEndpoints,
    activeRemote,
    download,
    cancelDownload,
    removeModel,
    addCustomModel,
    addModel,
    load,
    unload,
    sendMessage,
    regenerate,
    complete,
    stop,
    newConversation,
    openConversation,
    deleteConversation,
    renameConversation,
    setSystemPrompt,
    setMemoryEnabled,
    updateMemory,
    learnFromChats,
    clearMemory,
    addEndpoint,
    removeEndpoint,
    selectRemoteModel,
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

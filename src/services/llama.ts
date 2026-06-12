import { initLlama, LlamaContext, RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER } from 'llama.rn';
import { Platform } from 'react-native';
import { ChatMessage } from '../types';

export interface LoadedModel {
  context: LlamaContext;
  filePath: string;
  modelId: string;
}

let current: LoadedModel | null = null;

export function getLoadedModel(): LoadedModel | null {
  return current;
}

/**
 * Load a GGUF model file into a llama context. Releases any previously loaded
 * context first so only one model occupies memory at a time.
 */
export async function loadModel(
  modelId: string,
  filePath: string,
  onProgress?: (percent: number) => void,
  mmprojPath?: string,
): Promise<LoadedModel> {
  await releaseModel();

  const context = await initLlama(
    {
      model: filePath,
      // Lazily memory-map the model instead of locking it all into RAM up front.
      // `use_mlock: true` forces the entire GGUF to be paged in before the load
      // returns, which adds many seconds to startup; mmap keeps launch snappy.
      use_mlock: false,
      use_mmap: true,
      n_ctx: 2048,
      // Offload to GPU on iOS (Metal). Keep CPU on Android for broad device support.
      n_gpu_layers: Platform.OS === 'ios' ? 99 : 0,
    },
    p => onProgress?.(p),
  );

  if (mmprojPath) {
    // Enable vision. use_gpu follows the same Metal/CPU split as the base model.
    const ok = await context.initMultimodal({
      path: mmprojPath,
      use_gpu: Platform.OS === 'ios',
    });
    if (!ok) {
      await context.release();
      throw new Error('Failed to enable vision (mmproj incompatible with this model).');
    }
  }

  current = { context, filePath, modelId };
  return current;
}

export async function releaseModel(): Promise<void> {
  if (current) {
    try {
      await current.context.release();
    } catch {
      // ignore release errors
    }
    current = null;
  }
}

export interface GenerateOptions {
  systemPrompt: string;
  history: ChatMessage[];
  temperature?: number;
  maxTokens?: number;
  onToken: (token: string) => void;
  /** Local image path to attach to the latest user turn (vision models). */
  imagePath?: string;
}

export interface GenerateResult {
  text: string;
  tokensPerSecond: number;
}

/**
 * Run a streaming chat completion against the loaded model. The model's own
 * chat template (embedded in the GGUF) is applied via `jinja: true`.
 */
export async function generate(
  options: GenerateOptions,
): Promise<GenerateResult> {
  if (!current) {
    throw new Error('No model is loaded.');
  }
  const { systemPrompt, history, temperature = 0.7, maxTokens = 512, imagePath } =
    options;

  const chatHistory = history.filter(m => m.role !== 'system');
  const messages = [
    { role: 'system', content: systemPrompt },
    ...chatHistory.map((m, i) => {
      // Prepend the media marker to the LAST user turn when an image is attached.
      const isLastUser =
        imagePath != null && m.role === 'user' && i === chatHistory.length - 1;
      return {
        role: m.role,
        content: isLastUser
          ? `${RNLLAMA_MTMD_DEFAULT_MEDIA_MARKER}\n${m.content}`
          : m.content,
      };
    }),
  ];

  const started = Date.now();
  let tokenCount = 0;

  const result = await current.context.completion(
    {
      messages,
      jinja: true,
      n_predict: maxTokens,
      temperature,
      stop: ['<|im_end|>', '<|eot_id|>', '<|end_of_text|>', '</s>'],
      ...(imagePath ? { media_paths: [imagePath] } : {}),
    },
    data => {
      if (data.token) {
        tokenCount += 1;
        options.onToken(data.token);
      }
    },
  );

  const elapsedSec = (Date.now() - started) / 1000;
  const tps =
    result.timings?.predicted_per_second ??
    (elapsedSec > 0 ? tokenCount / elapsedSec : 0);

  return {
    text: result.text ?? '',
    tokensPerSecond: Math.round((tps || 0) * 10) / 10,
  };
}

export async function stopGeneration(): Promise<void> {
  if (current) {
    await current.context.stopCompletion();
  }
}

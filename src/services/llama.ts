import { initLlama, LlamaContext } from 'llama.rn';
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
): Promise<LoadedModel> {
  await releaseModel();

  const context = await initLlama(
    {
      model: filePath,
      use_mlock: true,
      n_ctx: 2048,
      // Offload to GPU on iOS (Metal). Keep CPU on Android for broad device support.
      n_gpu_layers: Platform.OS === 'ios' ? 99 : 0,
    },
    p => onProgress?.(p),
  );

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
  const { systemPrompt, history, temperature = 0.7, maxTokens = 512 } = options;

  const messages = [
    { role: 'system', content: systemPrompt },
    ...history
      .filter(m => m.role !== 'system')
      .map(m => ({ role: m.role, content: m.content })),
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

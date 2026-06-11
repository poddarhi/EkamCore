import { ModelInfo } from '../types';

/**
 * A small curated catalog of GGUF chat models that are tiny enough to run
 * fully on-device. URLs point at direct GGUF files on the Hugging Face hub.
 *
 * Users can also add any custom GGUF URL from the Models screen, so this list
 * is just a convenient starting point.
 */
export const CATALOG: ModelInfo[] = [
  {
    id: 'qwen2.5-0.5b-instruct-q4',
    name: 'Qwen2.5 0.5B Instruct',
    description: 'Tiny & fast. Great first model to test on any phone.',
    params: '0.5B',
    quant: 'Q4_K_M',
    sizeBytes: 398_000_000,
    url: 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf',
  },
  {
    id: 'smollm2-360m-instruct-q8',
    name: 'SmolLM2 360M Instruct',
    description: 'Extremely small footprint, snappy responses.',
    params: '360M',
    quant: 'Q8_0',
    sizeBytes: 386_000_000,
    url: 'https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF/resolve/main/smollm2-360m-instruct-q8_0.gguf',
  },
  {
    id: 'llama-3.2-1b-instruct-q4',
    name: 'Llama 3.2 1B Instruct',
    description: 'Better reasoning, still phone-friendly (~0.8GB).',
    params: '1B',
    quant: 'Q4_K_M',
    sizeBytes: 808_000_000,
    url: 'https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf',
  },
  {
    id: 'qwen2.5-1.5b-instruct-q4',
    name: 'Qwen2.5 1.5B Instruct',
    description: 'Most capable here. Needs a recent device (~1GB).',
    params: '1.5B',
    quant: 'Q4_K_M',
    sizeBytes: 986_000_000,
    url: 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf',
  },
];

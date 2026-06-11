import { parseQuant, pickRecommended } from '../src/services/huggingface';

const q = (quant: string, sizeBytes: number) => ({
  filename: `model-${quant}.gguf`,
  quant,
  sizeBytes,
  url: `https://example.com/model-${quant}.gguf`,
});

describe('parseQuant', () => {
  it('parses standard Q-series quants', () => {
    expect(parseQuant('Llama-3.2-1B-Instruct-Q4_K_M.gguf')).toBe('Q4_K_M');
    expect(parseQuant('qwen2.5-0.5b-instruct-q4_k_m.gguf')).toBe('Q4_K_M');
    expect(parseQuant('model-Q8_0.gguf')).toBe('Q8_0');
  });

  it('parses IQ-series and float quants', () => {
    expect(parseQuant('Llama-3.2-1B-Instruct-IQ4_XS.gguf')).toBe('IQ4_XS');
    expect(parseQuant('model-f16.gguf')).toBe('F16');
  });

  it('falls back to GGUF when no quant token is present', () => {
    expect(parseQuant('some-model.gguf')).toBe('GGUF');
  });
});

describe('pickRecommended', () => {
  it('returns null for an empty list', () => {
    expect(pickRecommended([])).toBeNull();
  });

  it('prefers Q4_K_M when available', () => {
    const list = [q('Q3_K_L', 700), q('Q4_K_M', 800), q('Q8_0', 1300)];
    expect(pickRecommended(list)?.quant).toBe('Q4_K_M');
  });

  it('falls back to the median by size when no preferred quant exists', () => {
    const list = [q('IQ3_M', 600), q('Q5_K_M', 900), q('Q6_K', 1000)];
    // sorted: 600, 900, 1000 → median index 1 → Q5_K_M
    expect(pickRecommended(list)?.quant).toBe('Q5_K_M');
  });
});

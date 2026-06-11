import {
  estimateRequiredBytes,
  fitOrder,
  rateModelFit,
} from '../src/utils/modelFit';
import { ModelInfo } from '../src/types';

const GB = 1024 * 1024 * 1024;

const model = (sizeBytes: number): ModelInfo => ({
  id: 'm',
  name: 'M',
  description: '',
  params: '1B',
  quant: 'Q4_K_M',
  sizeBytes,
  url: 'https://example.com/m.gguf',
});

describe('estimateRequiredBytes', () => {
  it('is weights * 1.25 plus a 350MB runtime floor', () => {
    const floor = 350 * 1024 * 1024;
    expect(estimateRequiredBytes(model(1_000_000_000))).toBe(
      Math.round(1_000_000_000 * 1.25 + floor),
    );
  });
});

describe('rateModelFit', () => {
  it('returns "unknown" when total memory is missing', () => {
    expect(rateModelFit(model(400_000_000), null).tier).toBe('unknown');
    expect(rateModelFit(model(400_000_000), 0).tier).toBe('unknown');
  });

  it('returns "unknown" when the model size is unknown (custom URL)', () => {
    expect(rateModelFit(model(0), 8 * GB).tier).toBe('unknown');
  });

  it('rates a tiny model on a high-RAM device as "great"', () => {
    // 0.5B (~0.4GB) on 8GB → ratio ~0.20
    expect(rateModelFit(model(398_000_000), 8 * GB).tier).toBe('great');
  });

  it('rates a ~1.5B model on a mid 4GB device as "good"', () => {
    // ~1.6GB required vs 2GB usable → ratio ~0.74
    expect(rateModelFit(model(986_000_000), 4 * GB).tier).toBe('good');
  });

  it('rates a ~1.5B model on a 3GB device as "slow"', () => {
    // ~1.6GB required vs 1.5GB usable → ratio ~0.99
    expect(rateModelFit(model(986_000_000), 3 * GB).tier).toBe('slow');
  });

  it('rates a ~1.5B model on a 2GB device as "too-large"', () => {
    // ~1.6GB required vs 1GB usable → ratio ~1.49
    expect(rateModelFit(model(986_000_000), 2 * GB).tier).toBe('too-large');
  });
});

describe('fitOrder', () => {
  it('orders best-fitting tiers first', () => {
    expect(fitOrder('great')).toBeLessThan(fitOrder('good'));
    expect(fitOrder('good')).toBeLessThan(fitOrder('slow'));
    expect(fitOrder('slow')).toBeLessThan(fitOrder('too-large'));
    expect(fitOrder('too-large')).toBeLessThan(fitOrder('unknown'));
  });
});

import { ModelInfo } from '../types';

export type FitTier = 'great' | 'good' | 'slow' | 'too-large' | 'unknown';

export interface FitRating {
  tier: FitTier;
  label: string;
}

// A model's runtime footprint is roughly its weights (≈ the GGUF file size)
// times a small overhead, plus a fixed floor for the KV cache (n_ctx = 2048)
// and runtime buffers.
const WEIGHT_OVERHEAD = 1.25;
const RUNTIME_FLOOR_BYTES = 350 * 1024 * 1024;

// A mobile app can't use all of physical RAM (OS + other apps + jetsam
// headroom), so we budget a conservative fraction of it.
const SAFE_RAM_FRACTION = 0.5;

/** Estimated peak RAM (bytes) needed to load and run a model. */
export function estimateRequiredBytes(model: ModelInfo): number {
  return Math.round(model.sizeBytes * WEIGHT_OVERHEAD + RUNTIME_FLOOR_BYTES);
}

/**
 * Rate how well a model is expected to run on a device with the given total
 * RAM. `totalMemoryBytes` of null/0 (or an unknown size) yields 'unknown'.
 */
export function rateModelFit(
  model: ModelInfo,
  totalMemoryBytes: number | null,
): FitRating {
  if (!totalMemoryBytes || !model.sizeBytes) {
    return { tier: 'unknown', label: 'Performance unknown' };
  }
  const ratio = estimateRequiredBytes(model) / (totalMemoryBytes * SAFE_RAM_FRACTION);
  if (ratio <= 0.5) {
    return { tier: 'great', label: 'Runs great on your device' };
  }
  if (ratio <= 0.8) {
    return { tier: 'good', label: 'Runs well on your device' };
  }
  if (ratio <= 1.0) {
    return { tier: 'slow', label: 'May run slowly' };
  }
  return { tier: 'too-large', label: 'Too large for this device' };
}

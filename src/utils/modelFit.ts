import { ModelInfo } from '../types';

export type FitTier = 'great' | 'good' | 'slow' | 'too-large' | 'unknown';

export interface FitRating {
  tier: FitTier;
  label: string;
}

// Display order: best-fitting first.
const TIER_ORDER: Record<FitTier, number> = {
  great: 0,
  good: 1,
  slow: 2,
  'too-large': 3,
  unknown: 4,
};

/** Sort key for a fit tier (lower = shown higher). */
export function fitOrder(tier: FitTier): number {
  return TIER_ORDER[tier];
}

/** Short section heading for a tier (used to group the model list). */
export function tierHeading(tier: FitTier): string {
  switch (tier) {
    case 'great':
      return 'Runs great on your device';
    case 'good':
      return 'Runs well on your device';
    case 'slow':
      return 'May run slowly';
    case 'too-large':
      return 'Too large for this device';
    default:
      return 'Other models';
  }
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
 * Pick the "best" model from a set for the given device: the one with the
 * strongest fit tier, and within a tier the larger (more capable) one. Used to
 * preselect a sensible default when the user has several models downloaded.
 */
export function pickBestModel<T extends ModelInfo>(
  models: T[],
  totalMemoryBytes: number | null,
): T | null {
  if (models.length === 0) {
    return null;
  }
  return [...models].sort((a, b) => {
    const d =
      fitOrder(rateModelFit(a, totalMemoryBytes).tier) -
      fitOrder(rateModelFit(b, totalMemoryBytes).tier);
    return d !== 0 ? d : b.sizeBytes - a.sizeBytes;
  })[0];
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

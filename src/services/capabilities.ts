import { ModelInfo } from '../types';

/** A model can understand images when its `vision` flag is set. */
export function isVisionModel(model: ModelInfo): boolean {
  return model.vision === true;
}

/**
 * The set of vision-capable models that are fully downloaded. `downloadedIds`
 * is the ground-truth ready list (a vision model only appears there once BOTH
 * its base GGUF and mmproj are present — see download.ts). The attach gate (and
 * the future voice gate) consume this to decide none/one/many.
 */
export function downloadedVisionModels(
  models: ModelInfo[],
  downloadedIds: string[],
): ModelInfo[] {
  return models.filter(m => isVisionModel(m) && downloadedIds.includes(m.id));
}

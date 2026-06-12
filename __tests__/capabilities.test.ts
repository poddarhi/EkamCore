import { ModelInfo } from '../src/types';
import {
  isVisionModel,
  downloadedVisionModels,
} from '../src/services/capabilities';

const model = (over: Partial<ModelInfo> = {}): ModelInfo => ({
  id: 'm1',
  name: 'M1',
  description: '',
  sizeBytes: 1,
  url: 'u',
  params: '1B',
  quant: 'Q4',
  ...over,
});

describe('isVisionModel', () => {
  it('is true only when vision flag set', () => {
    expect(isVisionModel(model({ vision: true }))).toBe(true);
    expect(isVisionModel(model({ vision: false }))).toBe(false);
    expect(isVisionModel(model())).toBe(false);
  });
});

describe('downloadedVisionModels', () => {
  const models = [
    model({ id: 'text1' }),
    model({ id: 'vis1', vision: true }),
    model({ id: 'vis2', vision: true }),
  ];

  it('returns only vision models whose id is downloaded', () => {
    const out = downloadedVisionModels(models, ['text1', 'vis2']);
    expect(out.map(m => m.id)).toEqual(['vis2']);
  });

  it('returns empty when no vision model is downloaded', () => {
    expect(downloadedVisionModels(models, ['text1'])).toEqual([]);
  });

  it('returns all downloaded vision models for the many case', () => {
    const out = downloadedVisionModels(models, ['vis1', 'vis2']);
    expect(out.map(m => m.id)).toEqual(['vis1', 'vis2']);
  });
});

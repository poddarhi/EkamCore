import { ModelInfo } from '../src/types';
import { requiredFilesFor } from '../src/services/download';

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

describe('requiredFilesFor', () => {
  it('text model requires only the base gguf', () => {
    const files = requiredFilesFor(model());
    expect(files).toHaveLength(1);
    expect(files[0]).toMatch(/m1\.gguf$/);
  });

  it('vision model requires base gguf + mmproj', () => {
    const files = requiredFilesFor(model({ vision: true, mmprojUrl: 'mm' }));
    expect(files).toHaveLength(2);
    expect(files[0]).toMatch(/m1\.gguf$/);
    expect(files[1]).toMatch(/m1\.mmproj\.gguf$/);
  });
});

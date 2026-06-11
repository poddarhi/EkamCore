import { validateCatalog } from '../src/services/catalog';

const goodModel = {
  id: 'm1',
  name: 'Model One',
  url: 'https://example.com/m1.gguf',
  params: '1B',
  quant: 'Q4_K_M',
  sizeBytes: 800_000_000,
};

describe('validateCatalog', () => {
  it('returns the models for a well-formed catalog', () => {
    const result = validateCatalog({ version: 1, models: [goodModel] });
    expect(result).toHaveLength(1);
    expect(result?.[0].id).toBe('m1');
  });

  it('drops entries missing required fields but keeps valid ones', () => {
    const result = validateCatalog({
      models: [
        goodModel,
        { id: 'bad', name: 'No URL' }, // missing url/params/quant/sizeBytes
        { ...goodModel, id: 'm2', sizeBytes: 0 }, // non-positive size
      ],
    });
    expect(result?.map(m => m.id)).toEqual(['m1']);
  });

  it('returns null when there are no valid models', () => {
    expect(validateCatalog({ models: [{ id: 'x' }] })).toBeNull();
    expect(validateCatalog({ models: [] })).toBeNull();
  });

  it('returns null for a malformed root', () => {
    expect(validateCatalog(null)).toBeNull();
    expect(validateCatalog('nope')).toBeNull();
    expect(validateCatalog({ nope: true })).toBeNull();
  });
});

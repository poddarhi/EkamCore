import {
  buildMemoryBlock,
  buildTranscript,
  parseLearnedProfile,
} from '../src/services/memory';

describe('buildMemoryBlock', () => {
  it('returns empty when disabled', () => {
    expect(
      buildMemoryBlock({ enabled: false, facts: ['x'], style: 'y' }),
    ).toBe('');
  });

  it('returns empty when enabled but nothing learned', () => {
    expect(buildMemoryBlock({ enabled: true, facts: [], style: '' })).toBe('');
  });

  it('includes facts and style when enabled', () => {
    const block = buildMemoryBlock({
      enabled: true,
      facts: ['Is a doctor', 'Prefers Python'],
      style: 'Likes short, bulleted answers',
    });
    expect(block).toContain('- Is a doctor');
    expect(block).toContain('- Prefers Python');
    expect(block).toContain('Preferred answer style: Likes short, bulleted answers');
  });
});

describe('parseLearnedProfile', () => {
  it('parses a clean JSON object', () => {
    const r = parseLearnedProfile('{"facts": ["a", "b"], "style": "concise"}');
    expect(r.facts).toEqual(['a', 'b']);
    expect(r.style).toBe('concise');
  });

  it('extracts JSON embedded in surrounding prose', () => {
    const r = parseLearnedProfile(
      'Sure! Here is the profile: {"facts": ["likes tea"], "style": "warm"} Hope that helps.',
    );
    expect(r.facts).toEqual(['likes tea']);
    expect(r.style).toBe('warm');
  });

  it('caps facts at 6 and drops non-strings', () => {
    const r = parseLearnedProfile(
      '{"facts": ["1","2","3","4","5","6","7", 8], "style": 9}',
    );
    expect(r.facts).toHaveLength(6);
    expect(r.style).toBe('');
  });

  it('returns empty on invalid input', () => {
    expect(parseLearnedProfile('no json here')).toEqual({ facts: [], style: '' });
    expect(parseLearnedProfile('{broken')).toEqual({ facts: [], style: '' });
  });
});

describe('buildTranscript', () => {
  it('formats user/assistant turns and drops system', () => {
    const t = buildTranscript([
      { role: 'system', content: 'sys' },
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'hello' },
    ]);
    expect(t).toBe('User: hi\nAssistant: hello');
  });
});
